#!/usr/bin/env python3
"""
Otto BGP - SSH Host Key Setup Script (Python Version)

This script collects SSH host keys from all network devices stored in the
Otto BGP database (router_inventory table) for secure host key verification
in production. This is a one-time setup step.

Usage:
    python3 setup_host_keys.py [--output KNOWN_HOSTS]

Or with the toolkit:
    ./otto-bgp setup-host-keys

Environment Variables:
    OTTO_DB_PATH - Path to Otto database (default: /var/lib/otto-bgp/otto.db)
"""

import argparse
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from otto_bgp.collectors.juniper_ssh import JuniperSSHCollector
from otto_bgp.utils.ssh_security import HostKeyManager
from otto_bgp.database.router_mapping import RouterMappingManager


def setup_logging(verbose: bool = False):
    """Configure logging for the setup script"""
    level = logging.DEBUG if verbose else logging.INFO

    # Custom format for setup script
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    logger = logging.getLogger()
    logger.setLevel(level)
    logger.addHandler(handler)

    return logger


def load_devices_from_database() -> list:
    """
    Load devices from the SQL database

    Returns:
        List of dictionaries with 'address' and 'hostname' keys
    """
    logger = logging.getLogger(__name__)

    try:
        router_manager = RouterMappingManager()
        routers = router_manager.get_router_inventory()

        if not routers:
            logger.warning("No routers found in database inventory")
            return []

        devices = []
        for router in routers:
            devices.append({
                'address': router['ip_address'],
                'hostname': router['hostname']
            })

        logger.info(f"Loaded {len(devices)} devices from database")
        return devices

    except Exception as e:
        logger.error(f"Failed to load devices from database: {e}")
        raise


def collect_host_keys_ssh_keyscan(devices: list, known_hosts: str) -> dict:
    """
    Collect host keys using ssh-keyscan (fast, no auth required)

    Args:
        devices: List of device dictionaries with 'address' and 'hostname' keys
        known_hosts: Path to output known_hosts file

    Returns:
        Dictionary with collection statistics
    """
    logger = logging.getLogger(__name__)
    stats = {
        'total': 0,
        'successful': 0,
        'failed': 0,
        'failed_devices': []
    }

    # Validate devices list
    if not devices:
        logger.error("No devices provided")
        return stats

    # Create output directory
    known_hosts_path = Path(known_hosts)
    known_hosts_path.parent.mkdir(parents=True, exist_ok=True)

    # Backup existing file
    if known_hosts_path.exists():
        backup_path = known_hosts_path.with_suffix(
            f'.backup.{datetime.now().strftime("%Y%m%d_%H%M%S")}'
        )
        known_hosts_path.rename(backup_path)
        logger.info(f"Backed up existing known_hosts to {backup_path}")

    # Open known_hosts file for writing
    with open(known_hosts_path, 'w') as known_hosts_file:
        for device in devices:
            address = device.get('address')
            hostname = device.get('hostname', '')

            if not address:
                continue

            stats['total'] += 1
            device_name = f"{hostname} ({address})" if hostname else address

            logger.info(f"Scanning {device_name}...")

            # Use ssh-keyscan to collect host keys
            try:
                # Scan for both ed25519 and rsa keys
                cmd = ['ssh-keyscan', '-t', 'ed25519,rsa', '-T', '5', address]
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=10
                )

                if result.stdout:
                    # Write to known_hosts
                    known_hosts_file.write(result.stdout)

                    # Also scan by hostname if different from address
                    if hostname and hostname != address:
                        cmd_hostname = ['ssh-keyscan', '-t', 'ed25519,rsa', '-T', '5', hostname]
                        result_hostname = subprocess.run(
                            cmd_hostname,
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        if result_hostname.stdout:
                            known_hosts_file.write(result_hostname.stdout)

                    stats['successful'] += 1
                    logger.info(f"  ✓ Successfully collected keys from {device_name}")
                else:
                    stats['failed'] += 1
                    stats['failed_devices'].append(device_name)
                    logger.warning(f"  ✗ No keys collected from {device_name}")

            except subprocess.TimeoutExpired:
                stats['failed'] += 1
                stats['failed_devices'].append(device_name)
                logger.warning(f"  ✗ Timeout scanning {device_name}")
            except Exception as e:
                stats['failed'] += 1
                stats['failed_devices'].append(device_name)
                logger.error(f"  ✗ Error scanning {device_name}: {e}")

    # Set proper permissions
    known_hosts_path.chmod(0o644)

    return stats


def collect_host_keys_paramiko(devices: list, known_hosts: str) -> dict:
    """
    Collect host keys using Paramiko (requires SSH credentials)

    Args:
        devices: List of device dictionaries with 'address' and 'hostname' keys
        known_hosts: Path to output known_hosts file

    Returns:
        Dictionary with collection statistics
    """
    logger = logging.getLogger(__name__)

    # Set setup mode temporarily
    os.environ['BGP_TOOLKIT_SETUP_MODE'] = 'true'

    stats = {
        'total': len(devices),
        'successful': 0,
        'failed': 0,
        'failed_devices': []
    }

    try:
        collector = JuniperSSHCollector(setup_mode=True)

        for device_dict in devices:
            from otto_bgp.models import DeviceInfo

            device = DeviceInfo(
                address=device_dict['address'],
                hostname=device_dict.get('hostname', device_dict['address'])
            )

            result = collector.collect_bgp_data_from_device(device)
            if result.success:
                stats['successful'] += 1
                logger.info(f"  ✓ Collected host key from {device.hostname}")
            else:
                stats['failed'] += 1
                device_name = f"{device.hostname} ({device.address})" if device.hostname else device.address
                stats['failed_devices'].append(device_name)
                logger.warning(f"  ✗ Failed to collect from {device_name}")

    finally:
        # Clear setup mode
        os.environ.pop('BGP_TOOLKIT_SETUP_MODE', None)

    return stats


def verify_host_keys(known_hosts: str):
    """
    Verify and display information about collected host keys

    Args:
        known_hosts: Path to known_hosts file
    """
    logger = logging.getLogger(__name__)

    try:
        manager = HostKeyManager(known_hosts)
        results = manager.verify_host_keys()

        logger.info("\n" + "="*50)
        logger.info("Host Key Verification Report")
        logger.info("="*50)
        logger.info(f"Total unique hosts: {results['total_hosts']}")
        logger.info(f"Total keys collected: {results['total_keys']}")

        if results['key_types']:
            logger.info("\nKey types collected:")
            for key_type, count in results['key_types'].items():
                logger.info(f"  - {key_type}: {count}")

        # Export to JSON for audit
        json_path = Path(known_hosts).with_suffix('.json')
        manager.export_to_json(str(json_path))
        logger.info(f"\nHost key audit report saved to: {json_path}")

    except Exception as e:
        logger.error(f"Failed to verify host keys: {e}")


def main():
    """Main entry point for host key setup"""
    parser = argparse.ArgumentParser(
        description='Collect SSH host keys from network devices in Otto BGP database'
    )

    parser.add_argument(
        '--output',
        default='/var/lib/otto-bgp/ssh-keys/known_hosts',
        help='Path to output known_hosts file (default: /var/lib/otto-bgp/ssh-keys/known_hosts)'
    )

    parser.add_argument(
        '--method',
        choices=['ssh-keyscan', 'paramiko'],
        default='ssh-keyscan',
        help='Method to use for collecting keys (default: ssh-keyscan)'
    )

    parser.add_argument(
        '--verify-only',
        action='store_true',
        help='Only verify existing known_hosts file, do not collect new keys'
    )

    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    # Setup logging
    logger = setup_logging(args.verbose)

    # Header
    print("\n" + "="*50)
    print("Otto BGP - SSH Host Key Setup")
    print("="*50 + "\n")

    # Verify only mode
    if args.verify_only:
        if not Path(args.output).exists():
            logger.error(f"Known hosts file not found: {args.output}")
            sys.exit(1)

        verify_host_keys(args.output)
        return

    # Check database
    db_path_str = os.getenv('OTTO_DB_PATH', '/var/lib/otto-bgp/otto.db')
    db_path = Path(db_path_str)

    if not db_path.exists():
        logger.error(f"Database not found: {db_path}")
        logger.error("Please ensure Otto BGP is installed and the database is initialized")
        sys.exit(1)

    # Load devices from database
    logger.info(f"Loading devices from database: {db_path}")

    try:
        devices = load_devices_from_database()
    except Exception as e:
        logger.error(f"Failed to load devices from database: {e}")
        sys.exit(1)

    if not devices:
        logger.error("No devices found in database inventory")
        logger.error("Please add routers to the inventory before collecting host keys")
        logger.error("Use: otto-bgp discover or add routers manually")
        sys.exit(1)

    # Collect host keys
    logger.info(f"Collecting host keys from {len(devices)} devices")
    logger.info(f"Output will be saved to: {args.output}")
    logger.info(f"Using method: {args.method}\n")

    if args.method == 'ssh-keyscan':
        stats = collect_host_keys_ssh_keyscan(devices, args.output)
    else:
        stats = collect_host_keys_paramiko(devices, args.output)

    # Display summary
    print("\n" + "="*50)
    print("Collection Summary")
    print("="*50)
    print(f"Total devices: {stats['total']}")
    print(f"Successful: {stats['successful']}")
    print(f"Failed: {stats['failed']}")

    if stats['failed_devices']:
        print("\nFailed devices:")
        for device in stats['failed_devices']:
            print(f"  - {device}")

    # Verify collected keys
    if Path(args.output).exists():
        verify_host_keys(args.output)

    # Next steps
    print("\n" + "="*50)
    print("Next Steps")
    print("="*50)
    print("1. Review the collected host keys")
    print("2. Verify fingerprints with your network team")
    print("3. Test connections with strict host key checking")

    if stats['failed'] > 0:
        print("\n⚠️  Warning: Some devices failed. Please investigate and")
        print("   manually add their keys if needed.")

    sys.exit(0 if stats['failed'] == 0 else 1)


if __name__ == '__main__':
    main()
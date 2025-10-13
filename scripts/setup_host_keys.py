#!/usr/bin/env python3
"""
Otto BGP - SSH Host Key Setup Script (Python Version)

This script collects SSH host keys from all network devices for secure
host key verification in production. This is a one-time setup step.

Usage:
    python3 setup_host_keys.py [--devices DEVICES_CSV] [--output KNOWN_HOSTS]
    
Or with the toolkit:
    ./bgp-toolkit setup-host-keys
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


def collect_host_keys_ssh_keyscan(devices_csv: str, known_hosts: str) -> dict:
    """
    Collect host keys using ssh-keyscan (fast, no auth required)
    
    Args:
        devices_csv: Path to devices CSV file
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
    
    # Read devices from CSV
    import pandas as pd
    try:
        df = pd.read_csv(devices_csv)
    except Exception as e:
        logger.error(f"Failed to read devices CSV: {e}")
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
        for _, row in df.iterrows():
            address = row.get('address')
            hostname = row.get('hostname', '')
            
            if not address or address == 'address':  # Skip header
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
        description='Collect SSH host keys from network devices for secure verification'
    )
    
    parser.add_argument(
        '--devices',
        default='/var/lib/otto-bgp/config/devices.csv',
        help='Path to devices CSV file (default: /var/lib/otto-bgp/config/devices.csv)'
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
    
    # Check if devices file exists
    if not Path(args.devices).exists():
        logger.error(f"Devices CSV not found: {args.devices}")
        logger.error("Please create the devices.csv file with format: address,hostname")
        sys.exit(1)
    
    # Collect host keys
    logger.info(f"Collecting host keys from devices in: {args.devices}")
    logger.info(f"Output will be saved to: {args.output}")
    logger.info(f"Using method: {args.method}\n")
    
    if args.method == 'ssh-keyscan':
        stats = collect_host_keys_ssh_keyscan(args.devices, args.output)
    else:
        # Use paramiko method (requires setting up collector in setup mode)
        logger.info("Using Paramiko method (requires SSH credentials)...")
        os.environ['BGP_TOOLKIT_SETUP_MODE'] = 'true'
        
        try:
            collector = JuniperSSHCollector(setup_mode=True)
            devices = collector.load_devices_from_csv(args.devices)
            
            stats = {
                'total': len(devices),
                'successful': 0,
                'failed': 0,
                'failed_devices': []
            }
            
            for device in devices:
                result = collector.collect_bgp_data_from_device(device)
                if result.success:
                    stats['successful'] += 1
                else:
                    stats['failed'] += 1
                    stats['failed_devices'].append(
                        f"{device.hostname} ({device.address})" 
                        if device.hostname else device.address
                    )
        finally:
            # Clear setup mode
            os.environ.pop('BGP_TOOLKIT_SETUP_MODE', None)
    
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
    print("3. Ensure BGP_TOOLKIT_SETUP_MODE is not set in production")
    print("4. Test connections with strict host key checking")
    
    if stats['failed'] > 0:
        print("\n⚠️  Warning: Some devices failed. Please investigate and")
        print("   manually add their keys if needed.")
    
    sys.exit(0 if stats['failed'] == 0 else 1)


if __name__ == '__main__':
    main()

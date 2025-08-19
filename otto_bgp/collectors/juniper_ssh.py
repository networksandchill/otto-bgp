#!/usr/bin/env python3
"""
BGP Peer Data Collection from Juniper Devices

Modern implementation of SSH-based BGP data collection with:
- Proper error handling and connection management
- Environment variable credentials with SSH key support
- In-memory data processing (no temp files)
- Structured data objects for pipeline integration
"""

import paramiko
import pandas as pd
import os
import sys
import logging
import csv
from dataclasses import dataclass
from typing import List, Optional, Dict
from pathlib import Path

# Import secure host key verification
from otto_bgp.utils.ssh_security import get_host_key_policy

# Import v0.3.0 models
from otto_bgp.models import DeviceInfo, RouterProfile


@dataclass
class BGPPeerData:
    """BGP peer data collected from a device"""
    device: DeviceInfo
    bgp_config: str
    success: bool
    error_message: Optional[str] = None


class JuniperSSHCollector:
    """SSH-based BGP data collector for Juniper devices"""
    
    def __init__(self, 
                 ssh_username: Optional[str] = None,
                 ssh_password: Optional[str] = None,
                 ssh_key_path: Optional[str] = None,
                 connection_timeout: int = 30,
                 command_timeout: int = 60,
                 setup_mode: bool = False):
        """
        Initialize SSH collector with credentials and timeouts
        
        Args:
            ssh_username: SSH username (defaults to SSH_USERNAME env var)
            ssh_password: SSH password (defaults to SSH_PASSWORD env var) 
            ssh_key_path: Path to SSH private key (preferred over password)
            connection_timeout: SSH connection timeout in seconds
            command_timeout: Command execution timeout in seconds
            setup_mode: If True, collect host keys on first connection (for initial setup only)
        """
        self.logger = logging.getLogger(__name__)
        
        # Get credentials from environment if not provided
        self.ssh_username = ssh_username or os.getenv('SSH_USERNAME')
        self.ssh_password = ssh_password or os.getenv('SSH_PASSWORD')
        self.ssh_key_path = ssh_key_path or os.getenv('SSH_KEY_PATH')
        
        self.connection_timeout = connection_timeout
        self.command_timeout = command_timeout
        self.setup_mode = setup_mode or (os.getenv('OTTO_BGP_SETUP_MODE', '').lower() == 'true')
        
        # Validate credentials
        if not self.ssh_username:
            raise ValueError("SSH username must be provided via parameter or SSH_USERNAME env var")
        
        if not self.ssh_password and not self.ssh_key_path:
            raise ValueError("Either SSH password (SSH_PASSWORD) or key path (SSH_KEY_PATH) must be provided")
        
        self.logger.info(f"SSH collector initialized for user: {self.ssh_username}")
        if self.ssh_key_path:
            self.logger.info(f"Using SSH key authentication: {self.ssh_key_path}")
        else:
            self.logger.info("Using SSH password authentication")
        
        # Log security mode
        if self.setup_mode:
            self.logger.warning("Running in SETUP MODE - will collect new host keys")
        else:
            self.logger.info("Running in PRODUCTION MODE - strict host key verification enabled")
    
    def load_devices_from_csv(self, csv_path: str) -> List[DeviceInfo]:
        """
        Load device information from CSV file - Enhanced for v0.3.0 router-aware architecture
        
        Supports both formats:
        - v0.2.0: address only (backward compatibility)
        - v0.3.0: address,hostname (enhanced format)
        
        Args:
            csv_path: Path to CSV file with 'address' column and optional 'hostname' column
            
        Returns:
            List of DeviceInfo objects with auto-generated hostnames if needed
        """
        try:
            csv_file = Path(csv_path)
            if not csv_file.exists():
                raise FileNotFoundError(f"Device CSV not found: {csv_path}")
            
            devices = []
            hostnames_seen = set()
            
            # Try with csv module for better control
            with open(csv_file, 'r', newline='') as file:
                reader = csv.DictReader(file)
                
                # Check if hostname column exists
                has_hostname = 'hostname' in reader.fieldnames if reader.fieldnames else False
                
                self.logger.info(f"CSV format detected: {'v0.3.0 (with hostname)' if has_hostname else 'v0.2.0 (address only)'}")
                
                for row_num, row in enumerate(reader, start=2):
                    try:
                        # Use DeviceInfo.from_csv_row which handles auto-generation
                        device = DeviceInfo.from_csv_row(row)
                        
                        # Check for duplicate hostnames
                        if device.hostname in hostnames_seen:
                            self.logger.warning(f"Duplicate hostname '{device.hostname}' in row {row_num}, auto-generating unique name")
                            device.hostname = f"{device.hostname}-{row_num}"
                        
                        hostnames_seen.add(device.hostname)
                        devices.append(device)
                        
                        self.logger.debug(f"Loaded device: {device.hostname} ({device.address})")
                        
                    except Exception as e:
                        self.logger.error(f"Invalid device in CSV row {row_num}: {e}")
                        continue
            
            if not devices:
                raise ValueError(f"No valid devices found in {csv_path}")
            
            self.logger.info(f"Loaded {len(devices)} devices from {csv_path}")
            
            # Log backward compatibility notice if needed
            if not has_hostname:
                self.logger.info("Note: Using auto-generated hostnames for v0.2.0 format CSV. Consider updating to v0.3.0 format with explicit hostnames.")
            
            return devices
            
        except Exception as e:
            self.logger.error(f"Error loading devices from {csv_path}: {e}")
            raise
    
    def _create_ssh_client(self) -> paramiko.SSHClient:
        """Create and configure SSH client with secure host key verification"""
        ssh_client = paramiko.SSHClient()
        
        # Use secure host key policy instead of AutoAddPolicy
        host_key_policy = get_host_key_policy(setup_mode=self.setup_mode)
        ssh_client.set_missing_host_key_policy(host_key_policy)
        
        self.logger.debug(f"SSH client created with {'setup' if self.setup_mode else 'production'} host key policy")
        return ssh_client
    
    def _connect_to_device(self, ssh_client: paramiko.SSHClient, device: DeviceInfo) -> bool:
        """
        Connect to a network device via SSH
        
        Args:
            ssh_client: Paramiko SSH client
            device: Device to connect to
            
        Returns:
            True if connection successful, False otherwise
        """
        try:
            if self.ssh_key_path:
                # Use SSH key authentication
                ssh_client.connect(
                    hostname=device.address,
                    username=self.ssh_username,
                    key_filename=self.ssh_key_path,
                    timeout=self.connection_timeout
                )
            else:
                # Use password authentication
                ssh_client.connect(
                    hostname=device.address,
                    username=self.ssh_username,
                    password=self.ssh_password,
                    timeout=self.connection_timeout
                )
            
            self.logger.debug(f"SSH connection established to {device.address}")
            return True
            
        except paramiko.AuthenticationException as e:
            self.logger.error(f"SSH authentication failed to {device.address}: {e}")
            return False
        except paramiko.SSHException as e:
            self.logger.error(f"SSH protocol error to {device.address}: {e}")
            return False
        except OSError as e:
            self.logger.error(f"Network error connecting to {device.address}: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected SSH error to {device.address}: {e}")
            return False
    
    def collect_bgp_config(self, address: str) -> str:
        """
        Collect full BGP configuration from a device (for discovery)
        
        Args:
            address: Device IP address
            
        Returns:
            BGP configuration text
        """
        device = DeviceInfo(address=address, hostname=f"router-{address.replace('.', '-')}")
        ssh_client = self._create_ssh_client()
        
        try:
            # Connect to device
            if not self._connect_to_device(ssh_client, device):
                raise ConnectionError(f"Failed to connect to {address}")
            
            # Execute command to get full BGP configuration
            command = 'show configuration protocols bgp'
            self.logger.debug(f"Executing command on {address}: {command}")
            
            _, stdout, stderr = ssh_client.exec_command(command, timeout=self.command_timeout)
            
            # Read command output
            bgp_config = stdout.read().decode('utf-8')
            stderr_output = stderr.read().decode('utf-8')
            
            if stderr_output:
                self.logger.warning(f"Command stderr from {address}: {stderr_output}")
            
            self.logger.info(f"Successfully collected BGP configuration from {address}")
            
            return bgp_config
            
        except Exception as e:
            self.logger.error(f"Error collecting BGP config from {address}: {e}")
            raise
        finally:
            ssh_client.close()
    
    def collect_bgp_data_from_device(self, device: DeviceInfo) -> BGPPeerData:
        """
        Collect BGP peer data from a single device
        
        Args:
            device: Device to collect data from
            
        Returns:
            BGPPeerData object with results
        """
        ssh_client = self._create_ssh_client()
        
        try:
            # Connect to device
            if not self._connect_to_device(ssh_client, device):
                return BGPPeerData(
                    device=device,
                    bgp_config="",
                    success=False,
                    error_message="SSH connection failed"
                )
            
            # Execute BGP configuration command
            command = 'show configuration protocols bgp group CUSTOMERS | match peer-as'
            self.logger.debug(f"Executing command on {device.address}: {command}")
            
            _, stdout, stderr = ssh_client.exec_command(command, timeout=self.command_timeout)
            
            # Read command output
            bgp_config = stdout.read().decode('utf-8')
            stderr_output = stderr.read().decode('utf-8')
            
            if stderr_output:
                self.logger.warning(f"Command stderr from {device.address}: {stderr_output}")
            
            self.logger.info(f"Successfully collected BGP data from {device.address}")
            
            return BGPPeerData(
                device=device,
                bgp_config=bgp_config,
                success=True
            )
            
        except paramiko.SSHException as e:
            self.logger.error(f"SSH error collecting BGP data from {device.address}: {e}")
            return BGPPeerData(
                device=device,
                bgp_config="",
                success=False,
                error_message=f"SSH error: {e}"
            )
        except OSError as e:
            self.logger.error(f"Network error collecting BGP data from {device.address}: {e}")
            return BGPPeerData(
                device=device,
                bgp_config="",
                success=False,
                error_message=f"Network error: {e}"
            )
        except Exception as e:
            self.logger.error(f"Unexpected error collecting BGP data from {device.address}: {e}")
            return BGPPeerData(
                device=device,
                bgp_config="",
                success=False,
                error_message=str(e)
            )
        
        finally:
            # Always close SSH connection
            try:
                ssh_client.close()
                self.logger.debug(f"SSH connection closed to {device.address}")
            except (paramiko.SSHException, OSError) as e:
                self.logger.debug(f"SSH cleanup warning for {device.address}: {e}")
    
    def collect_bgp_data_from_csv(self, csv_path: str) -> List[BGPPeerData]:
        """
        Collect BGP data from all devices in CSV file
        
        Args:
            csv_path: Path to CSV file with device addresses
            
        Returns:
            List of BGPPeerData objects
        """
        devices = self.load_devices_from_csv(csv_path)
        results = []
        
        self.logger.info(f"Starting BGP data collection from {len(devices)} devices")
        
        for i, device in enumerate(devices, 1):
            self.logger.info(f"Processing {device.address} ({i}/{len(devices)})")
            
            result = self.collect_bgp_data_from_device(device)
            results.append(result)
            
            if not result.success:
                self.logger.warning(f"Failed to collect data from {device.address}: {result.error_message}")
        
        successful_count = sum(1 for r in results if r.success)
        self.logger.info(f"BGP data collection complete: {successful_count}/{len(devices)} devices successful")
        
        return results
    
    def write_legacy_output_files(self, bgp_data: List[BGPPeerData], 
                                output_dir: str = ".") -> Dict[str, str]:
        """
        Write output in legacy format for compatibility
        
        Args:
            bgp_data: List of BGP data collected from devices
            output_dir: Directory to write output files
            
        Returns:
            Dictionary mapping file type to file path
        """
        output_dir = Path(output_dir)
        
        # Legacy file paths
        bgp_txt_path = output_dir / "bgp.txt"
        bgp_juniper_path = output_dir / "bgp-juniper.txt"
        
        # Clear existing files
        bgp_txt_path.write_text("")
        bgp_juniper_path.write_text("")
        
        # Write data in legacy format
        for data in bgp_data:
            if data.success and data.bgp_config:
                # Write to bgp-juniper.txt (with device address header)
                with open(bgp_juniper_path, "a") as f:
                    f.write(f"{data.device.address}\n")
                    f.write(f"{data.bgp_config}\n")
                
                # Write to bgp.txt (BGP config only)
                with open(bgp_txt_path, "ab") as f:
                    f.write(data.bgp_config.encode('utf-8'))
        
        self.logger.info(f"Legacy output files written: {bgp_txt_path}, {bgp_juniper_path}")
        
        return {
            "bgp_txt": str(bgp_txt_path),
            "bgp_juniper": str(bgp_juniper_path)
        }


def remove_double_returns(text: str) -> str:
    """
    Remove double returns from text (utility function from legacy script)
    
    Args:
        text: Input text
        
    Returns:
        Text with double newlines removed
    """
    while '\n\n' in text:
        text = text.replace('\n\n', '\n')
    return text


def extract_substring_lines(text: str, start_index: int, end_index: int) -> str:
    """
    Extract substring from each line (utility function from legacy script)
    
    Args:
        text: Input text
        start_index: Starting index of substring (inclusive)
        end_index: Ending index of substring (exclusive)
        
    Returns:
        Processed text with substrings extracted from each line
    """
    lines = text.split('\n')
    processed_lines = []
    
    for line in lines:
        if len(line) > start_index:
            substring = line[start_index:end_index]
            processed_lines.append(substring)
    
    return '\n'.join(processed_lines)
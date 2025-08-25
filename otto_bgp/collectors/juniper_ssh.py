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
import logging
import csv
from dataclasses import dataclass
from typing import List, Optional, Dict
from pathlib import Path
from contextlib import contextmanager

# Import secure host key verification
from otto_bgp.utils.ssh_security import get_host_key_policy

# Import models
from otto_bgp.models import DeviceInfo, RouterProfile

# Import parallel execution utilities
from otto_bgp.utils.parallel import ParallelExecutor


@dataclass
class BGPPeerData:
    """BGP peer data collected from a device"""
    device: DeviceInfo
    bgp_config: str
    success: bool
    error_message: Optional[str] = None


class SSHConnectionManager:
    """Context manager for SSH connections with resource leak prevention"""
    
    def __init__(self, collector: 'JuniperSSHCollector', device: DeviceInfo):
        self.collector = collector
        self.device = device
        self.ssh_client = None
        self.connected = False
    
    def __enter__(self):
        try:
            self.ssh_client = self.collector._create_ssh_client()
            self.connected = self.collector._connect_to_device(self.ssh_client, self.device)
            if not self.connected:
                self.ssh_client.close()
                raise ConnectionError(f"Failed to connect to {self.device.address}")
            return self.ssh_client
        except Exception as e:
            if self.ssh_client is not None:
                try:
                    self.ssh_client.close()
                except Exception:
                    pass
            raise e
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.ssh_client is not None:
            try:
                self.ssh_client.close()
                self.collector.logger.debug(f"SSH connection closed to {self.device.address}")
            except (paramiko.SSHException, OSError) as e:
                self.collector.logger.debug(f"SSH cleanup warning for {self.device.address}: {e}")


class JuniperSSHCollector:
    """SSH-based BGP data collector for Juniper devices"""
    
    def __init__(self, 
                 ssh_username: Optional[str] = None,
                 ssh_password: Optional[str] = None,
                 ssh_key_path: Optional[str] = None,
                 connection_timeout: int = 30,
                 command_timeout: int = 60,
                 setup_mode: bool = False,
                 max_workers: Optional[int] = None):
        """
        Initialize SSH collector with credentials and timeouts
        
        Args:
            ssh_username: SSH username (defaults to SSH_USERNAME env var)
            ssh_password: SSH password (defaults to SSH_PASSWORD env var) 
            ssh_key_path: Path to SSH private key (preferred over password)
            connection_timeout: SSH connection timeout in seconds
            command_timeout: Command execution timeout in seconds
            setup_mode: If True, collect host keys on first connection (for initial setup only)
            max_workers: Maximum parallel workers (defaults to OTTO_BGP_SSH_MAX_WORKERS env var or 5)
        """
        self.logger = logging.getLogger(__name__)
        
        # Get credentials from environment if not provided
        self.ssh_username = ssh_username or os.getenv('SSH_USERNAME')
        self.ssh_password = ssh_password or os.getenv('SSH_PASSWORD')
        self.ssh_key_path = ssh_key_path or os.getenv('SSH_KEY_PATH')
        
        self.connection_timeout = connection_timeout
        self.command_timeout = command_timeout
        self.setup_mode = setup_mode or (os.getenv('OTTO_BGP_SETUP_MODE', '').lower() == 'true')
        
        # Configure parallel execution
        if max_workers is None:
            # Get from environment or use default of 5
            try:
                max_workers = int(os.getenv('OTTO_BGP_SSH_MAX_WORKERS', '5'))
            except ValueError:
                max_workers = 5
        
        self.max_workers = max(1, max_workers)  # Ensure at least 1 worker
        
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
        
        # Log parallel configuration
        self.logger.info(f"Parallel collection configured: max_workers={self.max_workers}")
        
        # Log security mode
        if self.setup_mode:
            self.logger.warning("Running in SETUP MODE - will collect new host keys")
        else:
            self.logger.info("Running in PRODUCTION MODE - strict host key verification enabled")
    
    def load_devices_from_csv(self, csv_path: str) -> List[DeviceInfo]:
        """
        Load device information from CSV file - Enhanced for router-aware architecture
        
        Supports both formats:
        - Legacy format: address only
        - Enhanced format: address,hostname
        
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
                
                # Validate required CSV headers
                required_headers = {'address', 'hostname'}
                if not required_headers.issubset(set(reader.fieldnames or [])):
                    raise ValueError(f"CSV must contain required columns: {required_headers}. Found: {reader.fieldnames}")
                
                self.logger.info("CSV format validated: enhanced format with hostname")
                
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
        
        with SSHConnectionManager(self, device) as ssh_client:
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
    
    def collect_bgp_data_from_device(self, device: DeviceInfo) -> BGPPeerData:
        """
        Collect BGP peer data from a single device
        
        Args:
            device: Device to collect data from
            
        Returns:
            BGPPeerData object with results
        """
        try:
            with SSHConnectionManager(self, device) as ssh_client:
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
                
        except ConnectionError as e:
            self.logger.error(f"Connection error to {device.address}: {e}")
            return BGPPeerData(
                device=device,
                bgp_config="",
                success=False,
                error_message="SSH connection failed"
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
    
    def collect_bgp_data_from_csv(self, csv_path: str, 
                                  use_parallel: bool = True) -> List[BGPPeerData]:
        """
        Collect BGP data from all devices in CSV file
        
        Args:
            csv_path: Path to CSV file with device addresses
            use_parallel: Use parallel collection (default: True for performance)
            
        Returns:
            List of BGPPeerData objects
        """
        devices = self.load_devices_from_csv(csv_path)
        
        if use_parallel and len(devices) > 1:
            # Use parallel collection for multiple devices
            self.logger.info(f"Using parallel collection for {len(devices)} devices")
            return self.collect_from_devices(devices)
        else:
            # Use sequential collection (single device or parallel disabled)
            if not use_parallel:
                self.logger.info(f"Using sequential collection (parallel disabled)")
            else:
                self.logger.info(f"Using sequential collection (single device)")
            
            results = []
            
            for i, device in enumerate(devices, 1):
                self.logger.info(f"Processing {device.address} ({i}/{len(devices)})")
                
                result = self.collect_bgp_data_from_device(device)
                results.append(result)
                
                if not result.success:
                    self.logger.warning(f"Failed to collect data from {device.address}: {result.error_message}")
            
            successful_count = sum(1 for r in results if r.success)
            self.logger.info(f"BGP data collection complete: {successful_count}/{len(devices)} devices successful")
            
            return results
    
    def collect_from_devices(self, devices: List[DeviceInfo], 
                           show_progress: bool = True) -> List[BGPPeerData]:
        """
        Collect BGP data from multiple devices in parallel
        
        This method maintains all security features of single-device collection
        while executing in parallel for improved performance.
        
        Args:
            devices: List of DeviceInfo objects to collect from
            show_progress: Display progress indicators
            
        Returns:
            List of BGPPeerData objects with results from all devices
        """
        if not devices:
            self.logger.warning("No devices provided for collection")
            return []
        
        # Auto-scale worker count based on device count
        optimal_workers = min(self.max_workers, len(devices))
        
        self.logger.info(f"Starting parallel BGP data collection from {len(devices)} devices using {optimal_workers} workers")
        
        # Create parallel executor with proper resource management
        with ParallelExecutor(
            max_workers=optimal_workers, 
            show_progress=show_progress
        ) as executor:
            # Execute parallel collection
            parallel_results = executor.execute_batch(
                items=devices,
                task_func=self.collect_bgp_data_from_device,
                task_name="Collecting BGP data"
            )
        
        # Extract BGPPeerData results from ParallelResult objects
        bgp_results = []
        successful_count = 0
        failed_devices = []
        
        for parallel_result in parallel_results:
            if parallel_result.success and parallel_result.result:
                bgp_data = parallel_result.result
                bgp_results.append(bgp_data)
                
                if bgp_data.success:
                    successful_count += 1
                else:
                    failed_devices.append(bgp_data.device.hostname)
            else:
                # Handle case where the parallel execution itself failed
                device = parallel_result.item
                bgp_results.append(BGPPeerData(
                    device=device,
                    bgp_config="",
                    success=False,
                    error_message=parallel_result.error or "Parallel execution failed"
                ))
                failed_devices.append(device.hostname)
        
        # Log comprehensive results
        total_devices = len(devices)
        self.logger.info(f"Parallel collection completed: {successful_count}/{total_devices} devices successful")
        
        if failed_devices:
            self.logger.warning(f"Failed devices: {', '.join(failed_devices[:5])}" + 
                              (f" (and {len(failed_devices) - 5} more)" if len(failed_devices) > 5 else ""))
        
        # Calculate and log performance metrics
        if show_progress and parallel_results:
            total_duration = sum(result.duration for result in parallel_results)
            avg_duration = total_duration / len(parallel_results)
            estimated_sequential = avg_duration * len(devices)
            actual_duration = max(result.duration for result in parallel_results)
            speedup = estimated_sequential / actual_duration if actual_duration > 0 else 1.0
            
            self.logger.info(f"Performance: estimated sequential={estimated_sequential:.1f}s, "
                           f"actual parallel={actual_duration:.1f}s, speedup={speedup:.1f}x")
        
        return bgp_results
    
    def write_outputs(self, bgp_data: List[BGPPeerData], 
                     output_dir: Optional[str] = None) -> List[str]:
        """Write BGP data to output files (non-legacy format)"""
        if not output_dir:
            output_dir = Path("bgp-data")
        else:
            output_dir = Path(output_dir)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        output_files = []
        
        for data in bgp_data:
            if data.success and data.bgp_config:
                # Write per-router file
                output_file = output_dir / f"{data.device.hostname}_bgp.txt"
                output_file.write_text(data.bgp_config)
                output_files.append(str(output_file))
                self.logger.info(f"Wrote BGP data for {data.device.hostname} to {output_file}")
        
        # Write combined file
        combined_file = output_dir / "all_routers_bgp.txt"
        combined_content = "\n".join([
            f"# Router: {data.device.hostname}\n{data.bgp_config}"
            for data in bgp_data if data.success and data.bgp_config
        ])
        combined_file.write_text(combined_content)
        output_files.append(str(combined_file))
        
        self.logger.info(f"Output files written: {output_files}")
        return output_files
    


# Removed unused helper functions
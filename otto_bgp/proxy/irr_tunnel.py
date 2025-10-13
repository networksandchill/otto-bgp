"""
IRR Proxy Tunnel Manager

Manages SSH tunnels for accessing Internet Routing Registry (IRR) services
from restricted network environments.

SECURITY: This module handles SSH connections and must follow strict security practices:
- Host key verification REQUIRED
- Process cleanup mandatory
- Resource monitoring essential
"""

import atexit
import logging
import signal
import socket
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple, Union

# Import resource management
from otto_bgp.utils.subprocess_manager import ManagedProcess


class TunnelState(Enum):
    """Tunnel connection states"""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    FAILED = "failed"
    MONITORING = "monitoring"


@dataclass
class ProxyConfig:
    """Configuration for IRR proxy tunnels"""

    enabled: bool = False
    method: str = "ssh_tunnel"
    jump_host: str = ""
    jump_user: str = ""
    ssh_key_file: Optional[str] = None
    known_hosts_file: Optional[str] = None
    connection_timeout: int = 10
    health_check_interval: int = 30
    max_retries: int = 3
    tunnels: List[Dict[str, Union[str, int]]] = None

    def __post_init__(self):
        if self.tunnels is None:
            self.tunnels = []


@dataclass
class TunnelStatus:
    """Status information for a proxy tunnel"""

    name: str
    state: TunnelState
    local_port: int
    remote_host: str
    remote_port: int
    process_id: Optional[int] = None
    established_at: Optional[float] = None
    last_check: Optional[float] = None
    error_message: Optional[str] = None
    retry_count: int = 0


class IRRProxyManager:
    """
    Manages SSH tunnels for IRR access in restricted environments

    Provides secure, monitored SSH tunnels to IRR services with:
    - Host key verification
    - Process lifecycle management
    - Health monitoring and auto-recovery
    - Resource cleanup
    """

    def __init__(self, config: ProxyConfig, logger: Optional[logging.Logger] = None):
        """
        Initialize proxy manager

        Args:
            config: Proxy configuration
            logger: Optional logger instance
        """
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
        self.tunnels: Dict[str, TunnelStatus] = {}
        self.processes: Dict[str, subprocess.Popen] = {}
        self.allocated_ports: set = set()

        # Register cleanup on exit
        atexit.register(self.cleanup_all_tunnels)

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def setup_tunnel(self, tunnel_config: Dict[str, Union[str, int]]) -> TunnelStatus:
        """
        Setup an SSH tunnel to an IRR service with enhanced resource management

        Args:
            tunnel_config: Configuration for specific tunnel

        Returns:
            TunnelStatus object with setup results
        """
        tunnel_name = tunnel_config.get("name", "default")
        remote_host = tunnel_config["remote_host"]
        remote_port = tunnel_config["remote_port"]
        local_port = tunnel_config.get("local_port")

        self.logger.info(
            f"Setting up IRR tunnel: {tunnel_name} -> {remote_host}:{remote_port}"
        )

        # Allocate local port if not specified
        if not local_port:
            local_port = self._allocate_port()

        # Validate port availability
        if not self._is_port_available(local_port):
            error_msg = f"Port {local_port} already in use"
            self.logger.error(error_msg)
            return TunnelStatus(
                name=tunnel_name,
                state=TunnelState.FAILED,
                local_port=local_port,
                remote_host=remote_host,
                remote_port=remote_port,
                error_message=error_msg,
            )

        # Create tunnel status object
        tunnel_status = TunnelStatus(
            name=tunnel_name,
            state=TunnelState.CONNECTING,
            local_port=local_port,
            remote_host=remote_host,
            remote_port=remote_port,
        )

        try:
            # Build SSH command
            ssh_cmd = self._build_ssh_command(local_port, remote_host, remote_port)

            # Use managed process for better resource control
            with ManagedProcess(
                command=ssh_cmd,
                timeout=None,  # Long-running process
                capture_output=True,
            ) as managed:
                process = managed.process

                # Wait for tunnel to establish
                if self._wait_for_tunnel(
                    local_port, timeout=self.config.connection_timeout
                ):
                    tunnel_status.state = TunnelState.CONNECTED
                    tunnel_status.process_id = process.pid
                    tunnel_status.established_at = time.time()
                    tunnel_status.last_check = time.time()

                    # Register tunnel and process - must detach from context manager
                    # for long-running tunnels
                    managed._cleanup_done = True  # Prevent automatic cleanup
                    self.tunnels[tunnel_name] = tunnel_status
                    self.processes[tunnel_name] = process
                    self.allocated_ports.add(local_port)

                    self.logger.info(
                        f"Tunnel {tunnel_name} established successfully on port {local_port}"
                    )

                else:
                    tunnel_status.state = TunnelState.FAILED
                    tunnel_status.error_message = (
                        "Failed to establish tunnel within timeout"
                    )
                    self.logger.error(f"Tunnel {tunnel_name} failed to establish")
                    # Process will be cleaned up by context manager

        except Exception as e:
            tunnel_status.state = TunnelState.FAILED
            tunnel_status.error_message = str(e)
            self.logger.error(f"Error setting up tunnel {tunnel_name}: {e}")

        return tunnel_status

    def test_tunnel_connectivity(self, tunnel_name: str) -> bool:
        """
        Test connectivity through a specific tunnel

        Args:
            tunnel_name: Name of tunnel to test

        Returns:
            True if tunnel is working, False otherwise
        """
        if tunnel_name not in self.tunnels:
            self.logger.warning(f"Tunnel {tunnel_name} not found for connectivity test")
            return False

        tunnel = self.tunnels[tunnel_name]

        try:
            # Test port connectivity
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex(("127.0.0.1", tunnel.local_port))
            sock.close()

            if result == 0:
                tunnel.last_check = time.time()
                tunnel.state = TunnelState.CONNECTED
                self.logger.debug(f"Tunnel {tunnel_name} connectivity test passed")
                return True
            else:
                tunnel.state = TunnelState.FAILED
                tunnel.error_message = f"Port {tunnel.local_port} not responding"
                self.logger.warning(f"Tunnel {tunnel_name} connectivity test failed")
                return False

        except Exception as e:
            tunnel.state = TunnelState.FAILED
            tunnel.error_message = str(e)
            self.logger.error(f"Error testing tunnel {tunnel_name}: {e}")
            return False

    def wrap_bgpq4_command(
        self, original_cmd: List[str], irr_server: str = None
    ) -> List[str]:
        """
        Modify bgpq4 command to use local tunnel endpoints

        Args:
            original_cmd: Original bgpq4 command
            irr_server: Optional specific IRR server to use

        Returns:
            Modified command using tunnel endpoints
        """
        if not self.config.enabled or not self.tunnels:
            return original_cmd

        # Find appropriate tunnel
        tunnel = None
        if irr_server:
            # Look for tunnel matching specific server
            for t in self.tunnels.values():
                if irr_server in t.remote_host:
                    tunnel = t
                    break
        else:
            # Use first available tunnel
            for t in self.tunnels.values():
                if t.state == TunnelState.CONNECTED:
                    tunnel = t
                    break

        if not tunnel:
            self.logger.warning("No suitable tunnel found, using original command")
            return original_cmd

        # Modify command to use local tunnel endpoint
        modified_cmd = original_cmd.copy()

        # Add server specification to point to local tunnel
        # bgpq4 -h localhost -p 43001 ...
        if "-h" not in modified_cmd:
            modified_cmd.extend(["-h", "127.0.0.1"])
            modified_cmd.extend(["-p", str(tunnel.local_port)])

        self.logger.debug(
            f"Modified bgpq4 command to use tunnel {tunnel.name} on port {tunnel.local_port}"
        )

        return modified_cmd

    def establish_all_tunnels(self) -> bool:
        """Establish all configured tunnels; return True if ≥1 CONNECTED."""
        if not (self.config and self.config.enabled and self.config.tunnels):
            return False
        connected = 0
        for tcfg in self.config.tunnels:
            status = self.setup_tunnel(tcfg)
            if status.state == TunnelState.CONNECTED:
                connected += 1
        return connected > 0

    def get_tunnel_mapping(self) -> Dict[str, Tuple[str, int]]:
        """Return CONNECTED tunnels as {name: ("127.0.0.1", port)}."""
        mapping: Dict[str, Tuple[str, int]] = {}
        for name, status in self.tunnels.items():
            if status.state == TunnelState.CONNECTED:
                mapping[name] = ("127.0.0.1", status.local_port)
        return mapping

    def monitor_tunnels(self) -> Dict[str, TunnelStatus]:
        """
        Monitor all active tunnels and restart failed ones

        Returns:
            Dictionary of tunnel statuses
        """
        self.logger.debug("Monitoring tunnel health")

        for tunnel_name, tunnel in self.tunnels.items():
            # Check process health
            if tunnel_name in self.processes:
                process = self.processes[tunnel_name]

                if process.poll() is not None:
                    # Process has terminated
                    tunnel.state = TunnelState.FAILED
                    tunnel.error_message = (
                        f"SSH process terminated with code {process.returncode}"
                    )
                    self.logger.warning(f"Tunnel {tunnel_name} process terminated")

                    # Attempt restart if within retry limit
                    if tunnel.retry_count < self.config.max_retries:
                        self._restart_tunnel(tunnel_name)

                elif self.test_tunnel_connectivity(tunnel_name):
                    tunnel.state = TunnelState.CONNECTED
                    tunnel.error_message = None

        return self.tunnels.copy()

    def cleanup_tunnel(self, tunnel_name: str) -> bool:
        """
        Clean up a specific tunnel with enhanced resource management

        Args:
            tunnel_name: Name of tunnel to cleanup

        Returns:
            True if cleanup successful
        """
        success = True

        if tunnel_name in self.processes:
            try:
                process = self.processes[tunnel_name]

                # Use managed termination for better resource control
                if process.poll() is None:  # Process still running
                    self.logger.info(
                        f"Terminating tunnel {tunnel_name} process {process.pid}"
                    )

                    # Try graceful termination first
                    process.terminate()

                    # Wait for graceful termination with timeout
                    try:
                        process.wait(timeout=5)
                        self.logger.debug(
                            f"Tunnel {tunnel_name} process terminated gracefully"
                        )
                    except subprocess.TimeoutExpired:
                        # Force kill if graceful termination fails
                        self.logger.warning(
                            f"Force killing unresponsive tunnel {tunnel_name} process {process.pid}"
                        )
                        process.kill()

                        # Ensure process is fully cleaned up
                        try:
                            process.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            self.logger.error(
                                f"Failed to kill process {process.pid} - may be zombie"
                            )
                            success = False

                del self.processes[tunnel_name]
                self.logger.info(f"Cleaned up tunnel {tunnel_name} process")

            except Exception as e:
                self.logger.error(
                    f"Error cleaning up tunnel {tunnel_name} process: {e}"
                )
                success = False

        # Clean up tunnel state
        if tunnel_name in self.tunnels:
            tunnel = self.tunnels[tunnel_name]
            self.allocated_ports.discard(tunnel.local_port)
            del self.tunnels[tunnel_name]
            self.logger.debug(f"Cleaned up tunnel {tunnel_name} state")

        return success

    def cleanup_all_tunnels(self):
        """Clean up all tunnels and processes with comprehensive resource management"""
        if not self.tunnels and not self.processes:
            return

        self.logger.info(f"Cleaning up {len(self.tunnels)} proxy tunnels")

        tunnel_names = list(self.tunnels.keys())

        # First pass: graceful termination
        for tunnel_name in tunnel_names:
            if tunnel_name in self.processes:
                process = self.processes[tunnel_name]
                if process.poll() is None:
                    try:
                        self.logger.debug(
                            f"Sending SIGTERM to tunnel {tunnel_name} process {process.pid}"
                        )
                        process.terminate()
                    except Exception as e:
                        self.logger.error(
                            f"Error terminating tunnel {tunnel_name}: {e}"
                        )

        # Wait for graceful termination
        time.sleep(2)

        # Second pass: cleanup and force kill if needed
        for tunnel_name in tunnel_names:
            try:
                self.cleanup_tunnel(tunnel_name)
            except Exception as e:
                self.logger.error(f"Error during tunnel cleanup {tunnel_name}: {e}")

        # Ensure all resources are cleared
        self.allocated_ports.clear()
        self.processes.clear()
        self.tunnels.clear()

        self.logger.info("All proxy tunnels cleaned up")

    def get_tunnel_status(self, tunnel_name: str) -> Optional[TunnelStatus]:
        """
        Get status of a specific tunnel

        Args:
            tunnel_name: Name of tunnel

        Returns:
            TunnelStatus or None if not found
        """
        return self.tunnels.get(tunnel_name)

    def list_tunnels(self) -> Dict[str, TunnelStatus]:
        """
        List all tunnels and their statuses

        Returns:
            Dictionary of tunnel statuses
        """
        return self.tunnels.copy()

    def _build_ssh_command(
        self, local_port: int, remote_host: str, remote_port: int
    ) -> List[str]:
        """Build SSH tunnel command with security options"""
        cmd = [
            "ssh",
            "-N",  # No remote command
            "-T",  # No TTY
            "-o",
            "StrictHostKeyChecking=yes",  # Require host key verification
            "-o",
            "BatchMode=yes",  # No interactive prompts
            "-o",
            f"ConnectTimeout={self.config.connection_timeout}",
            "-o",
            "ServerAliveInterval=30",
            "-o",
            "ServerAliveCountMax=3",
            "-L",
            f"{local_port}:{remote_host}:{remote_port}",
        ]

        # Add known hosts file if specified
        if self.config.known_hosts_file:
            cmd.extend(["-o", f"UserKnownHostsFile={self.config.known_hosts_file}"])

        # Add SSH key if specified
        if self.config.ssh_key_file:
            cmd.extend(["-i", self.config.ssh_key_file])

        # Add user and host
        cmd.append(f"{self.config.jump_user}@{self.config.jump_host}")

        return cmd

    def _wait_for_tunnel(self, local_port: int, timeout: int = 10) -> bool:
        """Wait for tunnel to become available"""
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(("127.0.0.1", local_port))
                sock.close()

                if result == 0:
                    return True

            except Exception:
                pass

            time.sleep(0.5)

        return False

    def _is_port_available(self, port: int) -> bool:
        """Check if a port is available for binding"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(("127.0.0.1", port))
            sock.close()
            return True
        except OSError:
            return False

    def _allocate_port(self, start_port: int = 43001, max_port: int = 43100) -> int:
        """Allocate an available port for tunnel"""
        for port in range(start_port, max_port + 1):
            if port not in self.allocated_ports and self._is_port_available(port):
                return port

        raise RuntimeError(f"No available ports in range {start_port}-{max_port}")

    def _restart_tunnel(self, tunnel_name: str):
        """Restart a failed tunnel"""
        if tunnel_name not in self.tunnels:
            return

        tunnel = self.tunnels[tunnel_name]
        tunnel.retry_count += 1

        self.logger.info(
            f"Restarting tunnel {tunnel_name} (attempt {tunnel.retry_count})"
        )

        # Clean up old tunnel
        self.cleanup_tunnel(tunnel_name)

        # Recreate tunnel configuration
        tunnel_config = {
            "name": tunnel_name,
            "local_port": tunnel.local_port,
            "remote_host": tunnel.remote_host,
            "remote_port": tunnel.remote_port,
        }

        # Setup new tunnel
        new_status = self.setup_tunnel(tunnel_config)
        new_status.retry_count = tunnel.retry_count

    def _signal_handler(self, signum, frame):
        """Handle termination signals"""
        self.logger.info(f"Received signal {signum}, cleaning up tunnels")
        self.cleanup_all_tunnels()

# otto_bgp.proxy Module - Developer Guide

## Overview

The `proxy` module provides **IRR proxy capabilities** for networks with restricted internet access. It enables bgpq4 policy generation through SSH tunnels when direct IRR database access is blocked by firewalls or network policies.

**Security Status**: Production-ready with secure tunnel management and automatic cleanup

## Architecture Role

```
Restricted Network Environment:
Otto BGP → [PROXY] → Jump Host → Internet → IRR Databases
    │         ↑          ↑           ↑         ↑
    │         │          │           │         │
 bgpq4    SSH Tunnel  Gateway    Firewall   whois.radb.net
queries   Management   Server     Rules     rr.ntt.net
```

**Key Responsibilities**:
- Establish secure SSH tunnels to gateway servers
- Manage port forwarding for IRR database access
- Provide transparent bgpq4 proxy functionality
- Handle tunnel lifecycle and automatic cleanup
- Monitor tunnel health and implement reconnection logic

## Core Components

### 1. IRRTunnelManager (`irr_tunnel.py`)
**Purpose**: Secure SSH tunnel management for IRR database access

**Key Features**:
- Multi-tunnel support for IRR database redundancy
- Automatic tunnel health monitoring and reconnection
- Secure SSH key-based authentication
- Process cleanup and signal handling
- Configuration-driven tunnel setup

**Security Architecture**:
```python
class IRRTunnelManager:
    """Secure SSH tunnel manager for IRR access"""
    
    def __init__(self, jump_host: str, jump_user: str, ssh_key_path: str):
        self.jump_host = jump_host
        self.jump_user = jump_user
        self.ssh_key_path = Path(ssh_key_path)
        
        # Validate SSH key exists and has proper permissions
        self._validate_ssh_key()
        
        # Active tunnel tracking
        self.active_tunnels: Dict[str, TunnelProcess] = {}
        
        # Signal handlers for cleanup
        signal.signal(signal.SIGTERM, self._cleanup_signal_handler)
        signal.signal(signal.SIGINT, self._cleanup_signal_handler)
```

## Design Choices

### SSH Tunnel-Based Architecture
**Choice**: Use SSH local port forwarding for IRR access
**Rationale**:
- Leverages existing SSH infrastructure
- Encrypted tunnel ensures data security
- Automatic authentication via SSH keys
- Minimal network configuration required
- Standard protocol with wide support

### Multi-Tunnel Support
**Choice**: Support multiple simultaneous tunnels for different IRR servers
**Rationale**:
- Redundancy and failover capability
- Load distribution across IRR sources
- Minimize single points of failure
- Support for specialized IRR databases

### Process Management
**Choice**: Subprocess-based tunnel management with signal handling
**Rationale**:
- Clean separation from main Otto BGP process
- Automatic cleanup on process termination
- Resource isolation and monitoring
- Standard Unix process management

### Configuration-Driven Setup
**Choice**: External configuration for tunnel parameters
**Rationale**:
- Environment-specific customization
- No hard-coded network details
- Easy deployment across environments
- Security credential separation

## SSH Tunnel Implementation

### Tunnel Configuration
```python
@dataclass
class TunnelConfig:
    """Configuration for individual IRR tunnel"""
    name: str                    # Identifier (e.g., "radb", "ntt")
    local_port: int             # Local port for tunnel
    remote_host: str            # IRR server hostname
    remote_port: int = 43       # Standard whois port
    
    def __post_init__(self):
        """Validate tunnel configuration"""
        if not (1024 <= self.local_port <= 65535):
            raise ValueError(f"Invalid local port {self.local_port} (must be 1024-65535)")
        
        if not self.remote_host:
            raise ValueError("Remote host cannot be empty")
        
        if not (1 <= self.remote_port <= 65535):
            raise ValueError(f"Invalid remote port {self.remote_port}")

@dataclass
class ProxyConfig:
    """Complete proxy configuration"""
    enabled: bool = False
    jump_host: str = ""
    jump_user: str = ""
    ssh_key_path: str = ""
    tunnels: List[TunnelConfig] = field(default_factory=list)
    
    def validate(self) -> List[str]:
        """Validate proxy configuration"""
        errors = []
        
        if self.enabled:
            if not self.jump_host:
                errors.append("Jump host required when proxy enabled")
            
            if not self.jump_user:
                errors.append("Jump user required when proxy enabled")
            
            if not self.ssh_key_path:
                errors.append("SSH key path required when proxy enabled")
            
            if not self.tunnels:
                errors.append("At least one tunnel required when proxy enabled")
        
        return errors
```

### Tunnel Establishment
```python
def establish_tunnel(self, config: TunnelConfig) -> TunnelProcess:
    """Establish SSH tunnel with error handling"""
    
    logger.info(f"Establishing tunnel {config.name} - "
               f"localhost:{config.local_port} -> {config.remote_host}:{config.remote_port}")
    
    # Check if local port is available
    if not self._is_port_available(config.local_port):
        raise TunnelError(f"Local port {config.local_port} already in use")
    
    # Build SSH command
    ssh_command = [
        'ssh',
        '-N',  # Don't execute remote command
        '-L', f'{config.local_port}:{config.remote_host}:{config.remote_port}',
        '-i', str(self.ssh_key_path),
        '-o', 'StrictHostKeyChecking=yes',
        '-o', 'UserKnownHostsFile=/var/lib/otto-bgp/ssh-keys/known_hosts',
        '-o', 'ExitOnForwardFailure=yes',
        '-o', 'ServerAliveInterval=60',
        '-o', 'ServerAliveCountMax=3',
        f'{self.jump_user}@{self.jump_host}'
    ]
    
    try:
        # Start SSH tunnel process
        process = subprocess.Popen(
            ssh_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid  # Create new process group for cleanup
        )
        
        # Wait for tunnel to establish
        time.sleep(2)  # Give tunnel time to initialize
        
        # Check if process is still running
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise TunnelError(f"Tunnel {config.name} failed to establish: {stderr.decode()}")
        
        # Verify tunnel connectivity
        if not self._test_tunnel_connectivity(config.local_port):
            process.terminate()
            raise TunnelError(f"Tunnel {config.name} connectivity test failed")
        
        tunnel_process = TunnelProcess(
            config=config,
            process=process,
            established_at=datetime.now(),
            pid=process.pid
        )
        
        self.active_tunnels[config.name] = tunnel_process
        logger.info(f"Tunnel {config.name} established successfully (PID: {process.pid})")
        
        return tunnel_process
        
    except Exception as e:
        logger.error(f"Failed to establish tunnel {config.name}: {e}")
        raise TunnelError(f"Tunnel establishment failed: {e}") from e

def _test_tunnel_connectivity(self, local_port: int) -> bool:
    """Test tunnel connectivity"""
    try:
        with socket.create_connection(('localhost', local_port), timeout=5):
            return True
    except (socket.error, socket.timeout):
        return False

def _is_port_available(self, port: int) -> bool:
    """Check if local port is available"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(('localhost', port))
            return True
    except socket.error:
        return False
```

### Tunnel Health Monitoring
```python
def monitor_tunnel_health(self) -> Dict[str, bool]:
    """Monitor health of all active tunnels"""
    
    health_status = {}
    
    for name, tunnel in self.active_tunnels.items():
        try:
            # Check if process is still running
            if tunnel.process.poll() is not None:
                logger.warning(f"Tunnel {name} process terminated")
                health_status[name] = False
                continue
            
            # Test connectivity
            if self._test_tunnel_connectivity(tunnel.config.local_port):
                health_status[name] = True
            else:
                logger.warning(f"Tunnel {name} connectivity test failed")
                health_status[name] = False
                
        except Exception as e:
            logger.error(f"Health check failed for tunnel {name}: {e}")
            health_status[name] = False
    
    return health_status

def auto_reconnect_failed_tunnels(self):
    """Automatically reconnect failed tunnels"""
    
    health_status = self.monitor_tunnel_health()
    
    for name, is_healthy in health_status.items():
        if not is_healthy:
            try:
                logger.info(f"Attempting to reconnect tunnel {name}")
                
                # Clean up failed tunnel
                self.cleanup_tunnel(name)
                
                # Re-establish tunnel
                tunnel = self.active_tunnels.get(name)
                if tunnel:
                    self.establish_tunnel(tunnel.config)
                    
            except Exception as e:
                logger.error(f"Failed to reconnect tunnel {name}: {e}")
```

## Security Considerations

### SSH Key Management
```python
def _validate_ssh_key(self):
    """Validate SSH key exists and has proper permissions"""
    
    if not self.ssh_key_path.exists():
        raise TunnelError(f"SSH key not found: {self.ssh_key_path}")
    
    if not self.ssh_key_path.is_file():
        raise TunnelError(f"SSH key path is not a file: {self.ssh_key_path}")
    
    # Check permissions (should be 600)
    stat_info = self.ssh_key_path.stat()
    if stat_info.st_mode & 0o077:
        logger.warning(f"SSH key {self.ssh_key_path} has overly permissive permissions")
        # Attempt to fix permissions
        try:
            self.ssh_key_path.chmod(0o600)
            logger.info(f"Fixed SSH key permissions: {self.ssh_key_path}")
        except PermissionError:
            raise TunnelError(f"Cannot fix SSH key permissions: {self.ssh_key_path}")
```

### Process Security
```python
def _cleanup_signal_handler(self, signum, frame):
    """Handle signals for clean tunnel shutdown"""
    logger.info(f"Received signal {signum}, cleaning up tunnels")
    self.cleanup_all_tunnels()
    sys.exit(0)

def cleanup_tunnel(self, tunnel_name: str):
    """Clean up specific tunnel with process group termination"""
    
    tunnel = self.active_tunnels.get(tunnel_name)
    if not tunnel:
        return
    
    try:
        # Terminate entire process group
        os.killpg(os.getpgid(tunnel.process.pid), signal.SIGTERM)
        
        # Wait for graceful termination
        try:
            tunnel.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            # Force kill if necessary
            os.killpg(os.getpgid(tunnel.process.pid), signal.SIGKILL)
            tunnel.process.wait()
        
        logger.info(f"Tunnel {tunnel_name} cleaned up successfully")
        
    except (ProcessLookupError, OSError) as e:
        logger.warning(f"Process cleanup warning for tunnel {tunnel_name}: {e}")
    
    finally:
        # Remove from active tunnels
        del self.active_tunnels[tunnel_name]
```

### Network Security
- **Encrypted tunnels**: All data transmitted through SSH encryption
- **Key-based authentication**: No password authentication
- **Host key verification**: Strict checking of jump host identity
- **Port binding security**: Local-only binding for tunnel ports

## bgpq4 Integration

### Proxy-Aware bgpq4 Execution
```python
class ProxyAwareBGPq4Wrapper:
    """bgpq4 wrapper with proxy support"""
    
    def __init__(self, proxy_manager: IRRTunnelManager = None):
        self.proxy_manager = proxy_manager
        self.tunnel_mapping = self._build_tunnel_mapping()
    
    def _build_tunnel_mapping(self) -> Dict[str, int]:
        """Build mapping of IRR servers to local tunnel ports"""
        if not self.proxy_manager:
            return {}
        
        mapping = {}
        for tunnel in self.proxy_manager.active_tunnels.values():
            mapping[tunnel.config.remote_host] = tunnel.config.local_port
        
        return mapping
    
    def generate_policy_with_proxy(self, as_number: int, policy_name: str) -> PolicyResult:
        """Generate policy using proxy tunnels"""
        
        if not self.proxy_manager or not self.tunnel_mapping:
            # Fall back to direct connection
            return self.generate_policy_direct(as_number, policy_name)
        
        # Try each available tunnel
        for irr_server, local_port in self.tunnel_mapping.items():
            try:
                logger.debug(f"Attempting policy generation via {irr_server} (port {local_port})")
                
                # Build bgpq4 command with local port
                command = [
                    'bgpq4',
                    '-h', f'localhost:{local_port}',  # Use tunnel
                    '-Jl',
                    policy_name,
                    f'AS{as_number}'
                ]
                
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=45
                )
                
                if result.returncode == 0:
                    return PolicyResult(
                        as_number=as_number,
                        policy_name=policy_name,
                        content=result.stdout,
                        success=True,
                        irr_server=irr_server
                    )
                else:
                    logger.warning(f"bgpq4 failed via {irr_server}: {result.stderr}")
                    
            except subprocess.TimeoutExpired:
                logger.warning(f"bgpq4 timeout via {irr_server}")
            except Exception as e:
                logger.error(f"bgpq4 error via {irr_server}: {e}")
        
        # All tunnels failed
        raise BGPq4ProxyError("Policy generation failed via all proxy tunnels")
```

## Integration Points

### CLI Interface
```bash
# Configure proxy via environment variables
export OTTO_BGP_PROXY_ENABLED=true
export OTTO_BGP_PROXY_JUMP_HOST=gateway.example.com
export OTTO_BGP_PROXY_JUMP_USER=admin
export OTTO_BGP_PROXY_SSH_KEY=/var/lib/otto-bgp/ssh-keys/proxy-key

# Test proxy connectivity
./otto-bgp test-proxy --test-bgpq4

# Generate policies through proxy
./otto-bgp policy as_list.txt --output-dir policies
```

### Configuration Integration
```json
{
  "irr_proxy": {
    "enabled": true,
    "jump_host": "gateway.example.com",
    "jump_user": "admin",
    "ssh_key_file": "/var/lib/otto-bgp/ssh-keys/proxy-key",
    "tunnels": [
      {
        "name": "radb",
        "local_port": 43001,
        "remote_host": "whois.radb.net",
        "remote_port": 43
      },
      {
        "name": "ntt",
        "local_port": 43002,
        "remote_host": "rr.ntt.net",
        "remote_port": 43
      }
    ]
  }
}
```

### Pipeline Integration
```python
def setup_proxy_if_needed(config: Dict) -> Optional[IRRTunnelManager]:
    """Setup proxy manager if proxy is configured"""
    
    proxy_config = config.get('irr_proxy', {})
    
    if not proxy_config.get('enabled', False):
        return None
    
    # Validate configuration
    errors = ProxyConfig(**proxy_config).validate()
    if errors:
        raise ConfigurationError(f"Proxy configuration errors: {errors}")
    
    # Initialize tunnel manager
    manager = IRRTunnelManager(
        jump_host=proxy_config['jump_host'],
        jump_user=proxy_config['jump_user'],
        ssh_key_path=proxy_config['ssh_key_file']
    )
    
    # Establish tunnels
    for tunnel_config in proxy_config['tunnels']:
        config_obj = TunnelConfig(**tunnel_config)
        manager.establish_tunnel(config_obj)
    
    return manager
```

## Error Handling

### Tunnel-Specific Errors
```python
class TunnelError(Exception):
    """Base exception for tunnel-related errors"""
    pass

class TunnelEstablishmentError(TunnelError):
    """Failed to establish tunnel"""
    pass

class TunnelConnectivityError(TunnelError):
    """Tunnel connectivity test failed"""
    pass

class BGPq4ProxyError(Exception):
    """bgpq4 execution failed through proxy"""
    pass
```

### Resilient Operation
```python
def resilient_tunnel_operation(self, operation: Callable, max_retries: int = 3) -> Any:
    """Execute operation with tunnel resilience"""
    
    for attempt in range(max_retries):
        try:
            return operation()
            
        except (TunnelConnectivityError, BGPq4ProxyError) as e:
            logger.warning(f"Tunnel operation failed (attempt {attempt + 1}/{max_retries}): {e}")
            
            if attempt < max_retries - 1:
                # Attempt to reconnect failed tunnels
                self.auto_reconnect_failed_tunnels()
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                raise e
```

## Best Practices

### Tunnel Management
- Always implement signal handlers for clean shutdown
- Monitor tunnel health regularly
- Use process groups for proper cleanup
- Implement automatic reconnection logic

### Security
- Use key-based SSH authentication only
- Verify SSH host keys for jump servers
- Set appropriate file permissions on SSH keys
- Bind tunnel ports to localhost only

### Performance
- Use multiple tunnels for redundancy
- Monitor tunnel latency and performance
- Implement connection pooling where possible
- Cache tunnel connectivity status

### Operational
- Log all tunnel operations for troubleshooting
- Provide clear error messages for configuration issues
- Document tunnel requirements and dependencies
- Test proxy functionality in isolation
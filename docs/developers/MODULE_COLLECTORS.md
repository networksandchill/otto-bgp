# otto_bgp.collectors Module - Developer Guide

## Overview

The `collectors` module provides **secure SSH-based data collection** from Juniper network devices. This is a **security-critical module** that handles network authentication, device access, and BGP configuration retrieval.

**Status**: Production-ready with strict security controls

## Architecture Role

```
BGP Pipeline Flow:
[COLLECTORS] → Processing → Policy Generation → Application

Key Responsibilities:
- Secure SSH connectivity to network devices
- BGP configuration data extraction
- Device inventory management
- Connection pooling and parallel processing
```

## Core Components

### 1. JuniperSSHCollector (`juniper_ssh.py`)
**Purpose**: Main SSH collection interface for Juniper devices

**Key Features**:
- Paramiko-based SSH connections with security controls
- Parallel device collection with thread safety
- Retry logic with exponential backoff
- Comprehensive error handling and logging

**Security Architecture**:
```python
# Strict host key verification (NEVER AutoAddPolicy)
ssh_client = paramiko.SSHClient()
host_key_policy = get_host_key_policy(setup_mode=False)  # Production mode
ssh_client.set_missing_host_key_policy(host_key_policy)

# Key-based authentication only
ssh_client.connect(
    hostname=device.address,
    username=self.ssh_username,
    key_filename=self.ssh_key_path,
    look_for_keys=False,    # Don't auto-discover
    allow_agent=False,      # Don't use SSH agent
    password=None           # Never use passwords
)
```

## Security Architecture

### SSH Security Requirements
**CRITICAL**: This module implements strict security controls to prevent unauthorized access and man-in-the-middle attacks.

#### Host Key Verification
```python
# SECURE PATTERN - Always verify host keys
def _create_ssh_client(self) -> paramiko.SSHClient:
    ssh_client = paramiko.SSHClient()
    
    # Use secure host key policy (NEVER AutoAddPolicy in production)
    host_key_policy = get_host_key_policy(setup_mode=self.setup_mode)
    ssh_client.set_missing_host_key_policy(host_key_policy)
    
    return ssh_client

# ANTI-PATTERN - Never do this in production
ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # INSECURE
```

#### Authentication Security
- **Key-based authentication only** - no password authentication
- **No SSH agent usage** - explicit key file specification
- **No automatic key discovery** - prevent accidental key usage
- **Connection timeouts** - prevent hanging connections

### Command Execution Security
```python
# Whitelist approach for allowed commands
ALLOWED_COMMANDS = [
    'show bgp neighbor',
    'show route protocol bgp',
    'show configuration protocols bgp'
]

# Execute with validation and timeouts
def _execute_bgp_commands(self, ssh_client, device):
    for command in ALLOWED_COMMANDS:
        stdin, stdout, stderr = ssh_client.exec_command(
            command,
            timeout=self.command_timeout
        )
        # Process output with error handling
```

## Code Structure

### Class Hierarchy
```
JuniperSSHCollector
├── ConnectionManager (SSH session handling)
├── CommandExecutor (BGP command execution)
├── ErrorHandler (retry logic, error classification)
└── ResultAggregator (data collection results)

DeviceInfo (Data Model)
├── AddressValidator (IP/hostname validation)
├── CSVLoader (device inventory parsing)
└── ProfileConverter (to RouterProfile)
```

### Data Flow
```python
# 1. Load device inventory
devices = collector.load_devices_from_csv("devices.csv")

# 2. Parallel collection with error handling
results = collector.collect_from_devices_parallel(
    devices=devices,
    max_workers=5  # Configurable parallelism
)

# 3. Process results
for result in results:
    if result.success:
        # Process BGP data
        router_profile = device.to_router_profile()
        router_profile.bgp_config = result.bgp_data
    else:
        # Handle collection failure
        log_collection_error(result)
```

## Design Choices

### Paramiko for SSH
**Choice**: Use Paramiko library for SSH connections
**Rationale**:
- Pure Python implementation (no system dependencies)
- Fine-grained control over SSH parameters
- Extensive security configuration options
- Thread-safe for parallel operations

### Parallel Collection
**Choice**: ThreadPoolExecutor for concurrent device access
**Rationale**:
- I/O-bound operations benefit from concurrency
- Thread safety with connection isolation
- Configurable worker pool size
- Graceful error handling per thread

### CSV Device Inventory
**Choice**: CSV format for device lists with validation
**Rationale**:
- Simple, widely supported format
- Easy integration with existing tools
- Version control friendly
- Extensible with additional fields

### Connection Isolation
**Choice**: New SSH connection per device/operation
**Rationale**:
- Prevents connection state issues
- Thread safety in parallel execution
- Clean error isolation
- Simplified resource management

## Security Considerations

### Network Security
- **SSH host key verification** - prevents MITM attacks
- **Known hosts file management** - centralized key storage
- **Connection encryption** - all data encrypted in transit
- **No credential exposure** - no passwords or keys in logs

### Access Control
- **Read-only operations only** - no configuration changes
- **Limited command set** - whitelist approach
- **Minimal user permissions** - dedicated BGP read-only user
- **Connection timeouts** - prevent resource exhaustion

### Error Handling Security
- **No credential leakage** - sanitized error messages
- **Connection cleanup** - proper resource disposal
- **Retry limits** - prevent brute force scenarios
- **Audit logging** - security event tracking

## Device Management

### DeviceInfo Model
```python
@dataclass
class DeviceInfo:
    address: str      # IP address or hostname
    hostname: str     # Unique device identifier
    username: Optional[str] = None
    password: Optional[str] = None
    port: int = 22
    
    def __post_init__(self):
        # Validate address format
        self._validate_address()
    
    def to_router_profile(self) -> RouterProfile:
        # Convert to router profile for pipeline
        return RouterProfile(hostname=self.hostname, ip_address=self.address)
```

### CSV Format Support
```csv
address,hostname,role,region
192.168.1.1,edge-router-01,edge,us-east
192.168.1.2,core-router-01,core,us-east
10.0.1.1,border-router-01,border,us-west
```

**Required Fields**: `address`, `hostname`
**Optional Fields**: `role`, `region`, `port`, `username`

## Error Handling Patterns

### Network Error Recovery
```python
def collect_with_retry(self, device: DeviceInfo, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            result = self.collect_from_device(device)
            if result.success:
                return result
            
            # Exponential backoff for retryable errors
            if self._should_retry(result.error_message):
                wait_time = min(2 ** attempt, 10)
                time.sleep(wait_time)
            else:
                break  # Don't retry auth/permission errors
                
        except Exception as e:
            if attempt == max_retries - 1:
                return failure_result(e)
```

### Error Classification
```python
def _should_retry(self, error_message: str) -> bool:
    """Determine if error is retryable"""
    non_retryable_patterns = [
        'authentication failed',
        'permission denied', 
        'host key verification failed',
        'unknown host'
    ]
    
    error_lower = error_message.lower()
    return not any(pattern in error_lower for pattern in non_retryable_patterns)
```

### Timeout Management
- **Connection timeout**: 30 seconds (configurable)
- **Command timeout**: 60 seconds (configurable)
- **Overall operation timeout**: 5 minutes per device
- **Thread timeout**: 10 minutes for parallel operations

## Integration Points

### CLI Interface
```bash
# Collect from device list
./otto-bgp collect devices.csv --output-dir ./bgp-data

# Parallel collection with custom settings
./otto-bgp collect devices.csv --timeout 45 --command-timeout 120 --max-workers 8

# Test connectivity
./otto-bgp collect devices.csv --test-connectivity
```

### Python API
```python
from otto_bgp.collectors import JuniperSSHCollector

collector = JuniperSSHCollector(
    ssh_username="bgp-read",
    ssh_key_path="/var/lib/otto-bgp/ssh-keys/otto-bgp",
    connection_timeout=30,
    command_timeout=60
)

# Single device collection
result = collector.collect_from_device(device)

# Parallel collection
results = collector.collect_from_devices_parallel(devices)
```

### Pipeline Integration
- **Input**: CSV device inventory
- **Output**: RouterProfile objects with BGP configurations
- **Error Handling**: Detailed collection results with failure reasons
- **Logging**: Comprehensive operation logging for monitoring

## Performance Optimization

### Parallel Processing
```python
# Configurable worker pool
with ThreadPoolExecutor(max_workers=max_workers) as executor:
    future_to_device = {
        executor.submit(self.collect_with_retry, device): device
        for device in devices
    }
    
    # Process results as they complete
    for future in as_completed(future_to_device):
        result = future.result()
        results.append(result)
```

### Connection Management
- **Connection isolation** - separate connections per thread
- **Resource cleanup** - guaranteed connection closure
- **Memory management** - streaming data processing
- **Progress tracking** - real-time collection status

### Caching Considerations
- **No persistent caching** - always collect fresh data
- **Session caching within operation** - reuse for multiple commands
- **Result buffering** - efficient memory usage
- **Temporary file handling** - secure cleanup

## Development Guidelines

### Testing Strategy
```python
# Mock SSH for unit tests
@patch('paramiko.SSHClient')
def test_device_collection(mock_ssh):
    collector = JuniperSSHCollector(...)
    result = collector.collect_from_device(test_device)
    assert result.success

# Integration tests with real devices
def test_real_device_collection():
    # Requires test lab environment
    collector = JuniperSSHCollector(...)
    result = collector.collect_from_device(lab_device)
    assert "bgp" in result.bgp_data.lower()
```

### Security Testing
- **Host key validation** - test strict verification
- **Authentication failure handling** - invalid credentials
- **Command injection prevention** - malicious device names
- **Connection timeout behavior** - network failures

### Logging Standards
```python
# Structured logging for operations
logger.info("Device collection started", extra={
    'device': device.hostname,
    'address': device.address,
    'operation_id': operation_id
})

# Security events
logger.warning("Authentication failed", extra={
    'device': device.hostname,
    'error': 'key_auth_failed',
    'attempt': attempt_number
})

# Performance metrics
logger.info("Collection completed", extra={
    'device': device.hostname,
    'duration_ms': duration,
    'commands_executed': command_count,
    'bytes_collected': data_size
})
```

## Production Deployment

### SSH Key Management
```bash
# Generate dedicated key for BGP collection
ssh-keygen -t ed25519 -f /var/lib/otto-bgp/ssh-keys/otto-bgp -N ""

# Deploy to network devices (Juniper example)
set system login user bgp-read authentication ssh-ed25519 "ssh-ed25519 AAAAC3Nz..."
```

### Host Key Collection
```bash
# Collect host keys securely (one-time setup)
./scripts/setup-host-keys.sh devices.csv /var/lib/otto-bgp/ssh-keys/known_hosts

# Verify collected keys
ssh-keygen -l -f /var/lib/otto-bgp/ssh-keys/known_hosts
```

### Configuration Example
```python
# Production configuration
collector = JuniperSSHCollector(
    ssh_username="bgp-read",
    ssh_key_path="/var/lib/otto-bgp/ssh-keys/otto-bgp",
    connection_timeout=30,
    command_timeout=60,
    setup_mode=False,  # CRITICAL: Never True in production
    max_workers=5      # Conservative for production
)
```

## Dependencies

### Required
- `paramiko` (SSH client library)
- `cryptography` (SSH key handling)

### Optional
- `concurrent.futures` (parallel processing - Python 3.2+)

## Best Practices

### Security
- Always use key-based authentication
- Verify host keys in production
- Use minimal user permissions on devices
- Never log credentials or sensitive data
- Implement proper connection cleanup

### Performance
- Use appropriate worker pool sizes (5-10 for typical networks)
- Implement retry logic with backoff
- Monitor connection timeouts
- Track collection metrics

### Reliability
- Handle partial failures gracefully
- Provide detailed error reporting
- Implement comprehensive logging
- Test with realistic network conditions
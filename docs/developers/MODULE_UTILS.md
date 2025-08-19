# otto_bgp.utils Module - Developer Guide

## Overview

The `utils` module provides **foundational utilities and services** that support all other Otto BGP modules. It includes configuration management, logging, security utilities, caching, and directory management with a focus on security, reliability, and operational excellence.

**Design Philosophy**: Secure, reusable utilities with consistent interfaces and comprehensive error handling

## Architecture Role

```
Otto BGP Foundation Layer:
[ALL MODULES] ──────────────> utils (Configuration, Logging, Security)
     │                           ↑
     │                           │
Collectors ──> SSH Security ─────┘
Generators ──> Input Validation ──┘  
Pipeline ───> Directory Management ┘
Appliers ───> Configuration ────────┘
```

**Key Responsibilities**:
- Centralized configuration management
- Structured logging and audit trails
- SSH security and host key verification
- Directory and file management
- Caching and performance optimization
- Parallel processing utilities

## Core Components

### 1. Configuration Management (`config.py`)
**Purpose**: Centralized, validated configuration management with autonomous mode support

**Key Features (v0.3.2)**:
- JSON and environment variable configuration
- Schema validation with dataclass models
- Autonomous mode and installation mode configuration
- Email notification settings for NETCONF events
- Safety override configuration
- Backward compatibility with production_mode
- Runtime configuration updates with helper methods

#### Configuration Data Models (v0.3.2)

```python
@dataclass
class InstallationModeConfig:
    """Installation mode configuration"""
    type: str = "user"  # user, system
    service_user: str = "otto-bgp"
    systemd_enabled: bool = False
    optimization_level: str = "basic"  # basic, enhanced

@dataclass
class EmailNotificationConfig:
    """Email notification configuration for NETCONF events"""
    enabled: bool = True
    smtp_server: str = "smtp.company.com"
    smtp_port: int = 587
    smtp_use_tls: bool = True
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    from_address: str = "otto-bgp@company.com"
    to_addresses: List[str] = field(default_factory=lambda: ["network-engineers@company.com"])
    cc_addresses: List[str] = field(default_factory=list)
    subject_prefix: str = "[Otto BGP Autonomous]"
    send_on_success: bool = True
    send_on_failure: bool = True

@dataclass
class SafetyOverridesConfig:
    """Safety override configuration for autonomous mode"""
    max_session_loss_percent: float = 5.0
    max_route_loss_percent: float = 10.0
    monitoring_duration_seconds: int = 300

@dataclass
class NotificationConfig:
    """Notification configuration"""
    email: EmailNotificationConfig = field(default_factory=EmailNotificationConfig)
    webhook_url: Optional[str] = None
    alert_on_manual: bool = True
    success_notifications: bool = True

@dataclass
class AutonomousModeConfig:
    """Autonomous mode configuration"""
    enabled: bool = False  # Conservative default
    auto_apply_threshold: int = 100  # Informational only
    require_confirmation: bool = True
    safety_overrides: SafetyOverridesConfig = field(default_factory=SafetyOverridesConfig)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)

@dataclass
class BGPToolkitConfig:
    """Complete Otto BGP configuration"""
    environment: str = "user"
    installation_mode: InstallationModeConfig = field(default_factory=InstallationModeConfig)
    autonomous_mode: AutonomousModeConfig = field(default_factory=AutonomousModeConfig)
    # ... other existing config sections
```

#### Enhanced ConfigManager (v0.3.2)

```python
class ConfigManager:
    """Enhanced configuration management with autonomous mode support"""
    
    def __init__(self, config_file: Optional[Path] = None):
        self.config_file = config_file or self._find_config_file()
        self.config_data = {}
        self.env_overrides = {}
        
        self.load_configuration()
    
    def get_config(self) -> BGPToolkitConfig:
        """Get validated configuration as dataclass"""
        return self._config
    
    def update_autonomous_config(self, updates: Dict) -> None:
        """Update autonomous mode configuration"""
        current = asdict(self._config.autonomous_mode)
        current.update(updates)
        
        # Validate and update
        self._config.autonomous_mode = AutonomousModeConfig(**current)
        self._save_config()
    
    def update_email_config(self, updates: Dict) -> None:
        """Update email notification configuration"""
        current = asdict(self._config.autonomous_mode.notifications.email)
        current.update(updates)
        
        # Validate and update
        self._config.autonomous_mode.notifications.email = EmailNotificationConfig(**current)
        self._save_config()
    
    def validate_config(self) -> None:
        """Enhanced configuration validation"""
        # Validate autonomous mode compatibility
        if (self._config.autonomous_mode.enabled and 
            self._config.installation_mode.type != "system"):
            logger.warning("Autonomous mode recommended with system installation")
        
        # Validate threshold
        threshold = self._config.autonomous_mode.auto_apply_threshold
        if threshold > 1000:
            logger.warning(f"High auto_apply_threshold: {threshold} (informational only)")
        
        # Validate email configuration if autonomous mode enabled
        if self._config.autonomous_mode.enabled:
            email_config = self._config.autonomous_mode.notifications.email
            if email_config.enabled and not email_config.smtp_server:
                raise ConfigurationError("SMTP server required for autonomous email notifications")
```

#### Configuration Schema Validation

```python
INSTALLATION_MODE_SCHEMA = {
    "type": {"type": "string", "enum": ["user", "system"]},
    "service_user": {"type": "string", "default": "otto-bgp"},
    "systemd_enabled": {"type": "boolean", "default": False},
    "optimization_level": {"type": "string", "enum": ["basic", "enhanced"], "default": "basic"}
}

AUTONOMOUS_MODE_SCHEMA = {
    "enabled": {"type": "boolean", "default": False},
    "auto_apply_threshold": {"type": "integer", "minimum": 1, "default": 100},
    "require_confirmation": {"type": "boolean", "default": True},
    "safety_overrides": {
        "type": "object",
        "properties": {
            "max_session_loss_percent": {"type": "number", "minimum": 0, "maximum": 100},
            "max_route_loss_percent": {"type": "number", "minimum": 0, "maximum": 100},
            "monitoring_duration_seconds": {"type": "integer", "minimum": 60}
        }
    },
    "notifications": {
        "type": "object",
        "properties": {
            "email": {
                "type": "object",
                "properties": {
                    "enabled": {"type": "boolean", "default": True},
                    "smtp_server": {"type": "string"},
                    "smtp_port": {"type": "integer", "default": 587},
                    "smtp_use_tls": {"type": "boolean", "default": True},
                    "from_address": {"type": "string"},
                    "to_addresses": {"type": "array", "items": {"type": "string"}},
                    "subject_prefix": {"type": "string", "default": "[Otto BGP Autonomous]"}
                }
            }
        }
    }
}
```

### 2. Logging System (`logging.py`)
**Purpose**: Structured logging with security and operational focus

**Key Features**:
- Structured JSON logging for machine processing
- Security event logging with audit trails
- Performance metrics integration
- Multi-destination logging (files, syslog, journald)
- Log rotation and retention management

```python
class StructuredLogger:
    """Security-focused structured logging"""
    
    def __init__(self, name: str, level: str = "INFO"):
        self.logger = logging.getLogger(name)
        self.setup_handlers(level)
    
    def security_event(self, event_type: str, details: Dict):
        """Log security events with structured format"""
        self.logger.warning("SECURITY_EVENT", extra={
            'event_type': event_type,
            'timestamp': datetime.now().isoformat(),
            'details': details,
            'severity': 'high'
        })
```

### 3. SSH Security (`ssh_security.py`)
**Purpose**: SSH host key verification and security controls

**Key Features**:
- Strict host key verification policies
- Known hosts file management
- SSH key permission validation
- Security mode enforcement
- Audit logging for SSH events

```python
def get_host_key_policy(setup_mode: bool = False) -> paramiko.MissingHostKeyPolicy:
    """Get appropriate host key policy based on mode"""
    
    if setup_mode:
        # ONLY for initial setup - collect and verify keys
        return SetupModeHostKeyPolicy()
    else:
        # Production mode - strict verification only
        return StrictHostKeyPolicy()

class StrictHostKeyPolicy(paramiko.MissingHostKeyPolicy):
    """Strict host key verification - reject unknown hosts"""
    
    def missing_host_key(self, client, hostname, key):
        """Reject connection to unknown hosts"""
        key_type = key.get_name()
        fingerprint = key.get_fingerprint().hex()
        
        logger.error(f"Host key verification failed for {hostname}")
        logger.error(f"Unknown {key_type} key: {fingerprint}")
        
        raise paramiko.SSHException(f"Host key verification failed for {hostname}")
```

### 4. Directory Management (`directories.py`)
**Purpose**: Secure file and directory operations

**Key Features**:
- Atomic file operations with rollback
- Directory structure validation
- Permission management
- Temporary file handling with cleanup
- Cross-platform path handling

```python
class DirectoryManager:
    """Secure directory and file operations"""
    
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir).resolve()
        self.ensure_base_directory()
    
    def create_secure_directory(self, subdir: str, mode: int = 0o755) -> Path:
        """Create directory with proper permissions"""
        target_dir = self.base_dir / subdir
        
        # Validate path is within base directory
        if not self._is_safe_path(target_dir):
            raise SecurityError(f"Path traversal attempt: {subdir}")
        
        target_dir.mkdir(parents=True, exist_ok=True, mode=mode)
        return target_dir
```

### 5. Caching System (`cache.py`)
**Purpose**: Performance optimization through intelligent caching

**Key Features**:
- TTL-based cache expiration
- Memory-efficient storage
- Thread-safe operations
- Cache statistics and monitoring
- Configurable eviction policies

```python
class TTLCache:
    """Thread-safe TTL cache with monitoring"""
    
    def __init__(self, max_size: int = 1000, default_ttl: int = 3600):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache = {}
        self._lock = threading.RLock()
        self._stats = CacheStats()
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache with TTL check"""
        with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                if entry.is_expired():
                    del self._cache[key]
                    self._stats.misses += 1
                    return None
                else:
                    self._stats.hits += 1
                    return entry.value
            
            self._stats.misses += 1
            return None
```

### 6. Parallel Processing (`parallel.py`)
**Purpose**: Safe parallel execution utilities

**Key Features**:
- Configurable worker pools
- Error isolation and aggregation
- Progress tracking
- Resource monitoring
- Graceful shutdown handling

```python
class ParallelExecutor:
    """Safe parallel execution with monitoring"""
    
    def __init__(self, max_workers: int = 5):
        self.max_workers = max_workers
        self.execution_stats = ExecutionStats()
    
    def execute_parallel(self, tasks: List[Callable], timeout: int = 300) -> List[Result]:
        """Execute tasks in parallel with error handling"""
        results = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_task = {
                executor.submit(task): i for i, task in enumerate(tasks)
            }
            
            # Collect results with timeout
            for future in as_completed(future_to_task, timeout=timeout):
                task_index = future_to_task[future]
                try:
                    result = future.result()
                    results.append(Result(index=task_index, success=True, data=result))
                except Exception as e:
                    results.append(Result(index=task_index, success=False, error=str(e)))
        
        return results
```

## Security Architecture

### Configuration Security
```python
def validate_configuration_security(config: Dict) -> List[str]:
    """Validate configuration for security issues"""
    issues = []
    
    # Check for insecure settings
    if config.get('ssh', {}).get('strict_host_key_checking') == 'no':
        issues.append("SSH strict host key checking disabled - security risk")
    
    # Check for credential exposure
    for key, value in config.items():
        if isinstance(value, str) and ('password' in key.lower() or 'secret' in key.lower()):
            if value and not value.startswith('${'):  # Not env var reference
                issues.append(f"Credential '{key}' stored in plaintext")
    
    # Check file permissions
    ssh_key_path = config.get('ssh', {}).get('key_path')
    if ssh_key_path:
        key_file = Path(ssh_key_path)
        if key_file.exists():
            stat_info = key_file.stat()
            if stat_info.st_mode & 0o077:
                issues.append(f"SSH key {ssh_key_path} has overly permissive permissions")
    
    return issues
```

### Logging Security
```python
def sanitize_log_data(data: Dict) -> Dict:
    """Remove sensitive information from log data"""
    sanitized = {}
    
    sensitive_keys = {'password', 'secret', 'key', 'token', 'credential'}
    
    for key, value in data.items():
        if any(sensitive in key.lower() for sensitive in sensitive_keys):
            sanitized[key] = '[REDACTED]'
        elif isinstance(value, dict):
            sanitized[key] = sanitize_log_data(value)
        else:
            sanitized[key] = value
    
    return sanitized

def log_security_event(event_type: str, details: Dict):
    """Log security events with proper formatting"""
    sanitized_details = sanitize_log_data(details)
    
    security_logger.warning("SECURITY_EVENT", extra={
        'event_type': event_type,
        'timestamp': datetime.now().isoformat(),
        'details': sanitized_details,
        'severity': 'high',
        'module': 'otto_bgp'
    })
```

### File System Security
```python
def validate_file_path(path: Path, base_dir: Path) -> bool:
    """Validate file path to prevent directory traversal"""
    try:
        # Resolve to absolute path
        resolved_path = path.resolve()
        resolved_base = base_dir.resolve()
        
        # Check if path is within base directory
        try:
            resolved_path.relative_to(resolved_base)
            return True
        except ValueError:
            return False
            
    except (OSError, ValueError):
        return False

def secure_file_write(file_path: Path, content: str, mode: int = 0o644):
    """Write file with atomic operation and proper permissions"""
    
    # Validate path
    if not validate_file_path(file_path, BASE_DIR):
        raise SecurityError(f"Invalid file path: {file_path}")
    
    # Create temporary file
    temp_file = file_path.with_suffix(f"{file_path.suffix}.tmp.{os.getpid()}")
    
    try:
        # Write to temporary file
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # Set proper permissions
        temp_file.chmod(mode)
        
        # Atomic move to final location
        temp_file.replace(file_path)
        
    except Exception as e:
        # Clean up temporary file on error
        if temp_file.exists():
            temp_file.unlink()
        raise e
```

## Design Choices

### Centralized Configuration
**Choice**: Single configuration manager with multiple sources
**Rationale**:
- Consistent configuration access across modules
- Environment-specific overrides support
- Validation at single point
- Audit trail for configuration changes

### Structured Logging
**Choice**: JSON-based structured logging with security focus
**Rationale**:
- Machine-readable logs for automation
- Security event tracking and analysis
- Performance metrics integration
- Compliance and audit requirements

### Security-First Design
**Choice**: Security controls built into utility functions
**Rationale**:
- Prevent security issues at the foundation level
- Consistent security patterns across modules
- Audit trail for security-relevant operations
- Simplified security compliance

### Thread-Safe Utilities
**Choice**: Thread safety for all shared utilities
**Rationale**:
- Support for parallel processing
- Prevent race conditions in concurrent operations
- Consistent behavior across execution modes
- Future-proof for performance scaling

## Integration Points

### Configuration Usage
```python
# Throughout Otto BGP modules
from otto_bgp.utils.config import get_config_manager

config = get_config_manager()

# SSH configuration
ssh_username = config.get('ssh.username', 'bgp-read')
ssh_key_path = config.get('ssh.key_path', '/var/lib/otto-bgp/ssh-keys/otto-bgp')

# Logging configuration
log_level = config.get('logging.level', 'INFO')
log_file = config.get('logging.file', '/var/log/otto-bgp/otto-bgp.log')
```

### Logging Usage
```python
# Security-aware logging in modules
from otto_bgp.utils.logging import get_logger

logger = get_logger(__name__)

# Standard logging
logger.info("Starting BGP policy generation", extra={
    'as_count': len(as_numbers),
    'router': router_hostname
})

# Security event logging
logger.security_event('ssh_authentication_failure', {
    'hostname': device.hostname,
    'username': ssh_username,
    'ip_address': device.address
})
```

### Directory Management
```python
# Secure file operations
from otto_bgp.utils.directories import get_directory_manager

dir_mgr = get_directory_manager()

# Create secure output directory
output_dir = dir_mgr.create_secure_directory('policies/routers')

# Atomic file write
dir_mgr.secure_write_file(output_dir / 'policy.txt', policy_content)
```

## Error Handling

### Configuration Errors
```python
class ConfigurationError(Exception):
    """Configuration validation or loading error"""
    pass

class SecurityConfigurationError(ConfigurationError):
    """Security-related configuration error"""
    pass

def handle_configuration_error(error: ConfigurationError):
    """Handle configuration errors gracefully"""
    logger.error(f"Configuration error: {error}")
    
    # Log security issues
    if isinstance(error, SecurityConfigurationError):
        logger.security_event('configuration_security_violation', {
            'error': str(error),
            'config_file': str(config_file)
        })
    
    # Provide helpful error messages
    if "ssh" in str(error).lower():
        logger.info("Check SSH configuration in config file or environment variables")
    
    sys.exit(1)
```

### File System Errors
```python
def handle_file_operation_error(error: OSError, operation: str, file_path: Path):
    """Handle file system errors with security logging"""
    
    if error.errno == errno.EACCES:
        logger.error(f"Permission denied: {operation} {file_path}")
        logger.security_event('file_permission_denied', {
            'operation': operation,
            'file_path': str(file_path),
            'user': getpass.getuser()
        })
    elif error.errno == errno.ENOENT:
        logger.error(f"File not found: {file_path}")
    else:
        logger.error(f"File operation failed: {operation} {file_path}: {error}")
    
    raise error
```

## Performance Optimization

### Caching Strategy
```python
# AS number validation caching
@lru_cache(maxsize=10000)
def cached_as_validation(as_number: int) -> bool:
    """Cache AS number validation results"""
    return validate_as_number_range(as_number)

# Configuration caching
class CachedConfigManager(ConfigManager):
    """Configuration manager with caching"""
    
    def __init__(self):
        super().__init__()
        self._cache = TTLCache(max_size=1000, default_ttl=300)
    
    def get(self, key: str, default=None):
        """Get configuration value with caching"""
        cached_value = self._cache.get(key)
        if cached_value is not None:
            return cached_value
        
        value = super().get(key, default)
        self._cache.set(key, value)
        return value
```

### Resource Management
```python
class ResourceMonitor:
    """Monitor resource usage during operations"""
    
    def __init__(self):
        self.start_memory = self._get_memory_usage()
        self.peak_memory = self.start_memory
        self.start_time = time.time()
    
    def update_peak_memory(self):
        """Update peak memory usage"""
        current_memory = self._get_memory_usage()
        self.peak_memory = max(self.peak_memory, current_memory)
    
    def get_resource_summary(self) -> Dict:
        """Get resource usage summary"""
        return {
            'memory_mb': {
                'start': self.start_memory,
                'peak': self.peak_memory,
                'increase': self.peak_memory - self.start_memory
            },
            'execution_time_seconds': time.time() - self.start_time
        }
```

## Development Guidelines

### Utility Design Principles
- **Single Responsibility**: Each utility module has a clear, focused purpose
- **Security First**: Security controls built into all utilities
- **Thread Safety**: All utilities safe for concurrent use
- **Error Transparency**: Clear error messages with context
- **Performance Aware**: Efficient implementations with monitoring

### Testing Strategies
```python
# Configuration testing
def test_config_validation():
    """Test configuration validation"""
    config = {
        'ssh': {'strict_host_key_checking': 'no'}  # Insecure setting
    }
    
    issues = validate_configuration_security(config)
    assert any('strict host key checking' in issue for issue in issues)

# Security testing
def test_path_traversal_prevention():
    """Test directory traversal prevention"""
    base_dir = Path('/var/lib/otto-bgp')
    malicious_path = Path('../../../etc/passwd')
    
    assert not validate_file_path(malicious_path, base_dir)

# Performance testing
def test_cache_performance():
    """Test cache performance under load"""
    cache = TTLCache(max_size=1000)
    
    # Measure cache hit rates
    for i in range(10000):
        cache.set(f"key_{i % 100}", f"value_{i}")
    
    hit_rate = cache.stats.hit_rate
    assert hit_rate > 0.8  # Expect good hit rate
```

## Best Practices

### Security
- Always validate file paths to prevent traversal attacks
- Sanitize sensitive data before logging
- Use secure defaults for all configuration options
- Implement comprehensive audit logging

### Performance
- Use caching for expensive operations
- Monitor resource usage during execution
- Implement efficient data structures
- Profile performance-critical paths

### Reliability
- Implement atomic file operations
- Provide clear error messages with context
- Use thread-safe utilities for concurrent operations
- Implement graceful degradation for non-critical failures

### Maintainability
- Use consistent interfaces across utilities
- Document security considerations clearly
- Implement comprehensive testing
# otto_bgp.models Module - Developer Guide

## Overview

The `models` module defines **core data structures** for Otto BGP's router-aware architecture. It provides the foundational data models that maintain router identity, BGP configuration data, and pipeline results throughout the entire processing workflow.

**Design Philosophy**: Immutable, validated data structures with clear serialization patterns

## Architecture Role

```
Data Flow Through Models:
DeviceInfo → RouterProfile → PipelineResult

Cross-Module Usage:
- Collectors: Create and populate RouterProfile objects
- Discovery: Enhance RouterProfile with BGP group mappings
- Processors: Extract AS numbers into RouterProfile
- Generators: Read RouterProfile for policy generation
- Pipeline: Orchestrate data flow through models
```

## Core Data Models

### 1. RouterProfile
**Purpose**: Complete BGP profile for each router in the network

**Key Features**:
- Central data structure for router identity
- BGP configuration storage and AS number tracking
- Metadata management with automatic defaults
- Serialization support for persistence
- Validation and data integrity

```python
@dataclass
class RouterProfile:
    hostname: str                          # Unique router identifier
    ip_address: str                        # Management IP address
    bgp_config: str = ""                  # Raw BGP configuration
    discovered_as_numbers: Set[int] = field(default_factory=set)
    bgp_groups: Dict[str, List[int]] = field(default_factory=dict)
    metadata: Dict = field(default_factory=dict)
```

### 2. DeviceInfo
**Purpose**: Enhanced device information for router discovery and connection

**Key Features**:
- CSV-compatible device representation
- Router profile conversion capability
- Backward compatibility with legacy formats
- Input validation and hostname auto-generation

```python
@dataclass
class DeviceInfo:
    address: str                          # IP address or hostname
    hostname: str                         # Required in v0.3.2
    username: Optional[str] = None
    password: Optional[str] = None
    port: int = 22
    role: Optional[str] = None           # edge, core, transit
    region: Optional[str] = None         # us-east, eu-west, etc.
```

### 3. PipelineResult
**Purpose**: Comprehensive result container for pipeline execution

**Key Features**:
- Collection of all router profiles
- Success/failure tracking with detailed errors
- Statistical summary generation
- Router lookup capabilities

```python
@dataclass
class PipelineResult:
    router_profiles: List[RouterProfile]
    success: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    statistics: Dict = field(default_factory=dict)
```

## Design Choices

### Dataclasses with Post-Init Validation
**Choice**: Use Python dataclasses with `__post_init__` methods
**Rationale**:
- Clear, declarative data structure definitions
- Automatic equality, hashing, and string representation
- Built-in field defaults and type hints
- Post-initialization validation hooks

### Set for AS Numbers
**Choice**: Use `Set[int]` for discovered AS numbers
**Rationale**:
- Automatic deduplication of AS numbers
- Efficient membership testing
- Clear semantic meaning (unique collection)
- JSON serialization support via conversion

### Metadata Dictionary Pattern
**Choice**: Generic metadata dict with automatic defaults
**Rationale**:
- Extensible without schema changes
- Version compatibility across updates
- Platform-specific information storage
- Timestamp and audit trail support

### Immutable Data Principles
**Choice**: Favor immutable operations where possible
**Rationale**:
- Thread safety for parallel processing
- Predictable data flow through pipeline
- Easier debugging and testing
- Clear ownership semantics

## Data Model Details

### RouterProfile Implementation

#### Initialization and Validation
```python
def __post_init__(self):
    """Initialize metadata with default values if not provided"""
    if 'collected_at' not in self.metadata:
        self.metadata['collected_at'] = datetime.now().isoformat()
    if 'platform' not in self.metadata:
        self.metadata['platform'] = 'junos'  # Default to Juniper
```

#### AS Number Management
```python
def add_as_number(self, as_number: int) -> None:
    """Add a discovered AS number with validation"""
    if 0 <= as_number <= 4294967295:  # Valid 32-bit AS number range
        self.discovered_as_numbers.add(as_number)
    else:
        raise ValueError(f"AS number {as_number} outside valid range")

def add_bgp_group(self, group_name: str, as_numbers: List[int]) -> None:
    """Add or update a BGP group with its associated AS numbers"""
    # Validate group name
    if not re.match(r'^[a-zA-Z0-9_-]+$', group_name):
        raise ValueError(f"Invalid BGP group name: {group_name}")
    
    # Validate AS numbers
    validated_as = []
    for as_num in as_numbers:
        if 0 <= as_num <= 4294967295:
            validated_as.append(as_num)
        else:
            logger.warning(f"Skipping invalid AS number {as_num} in group {group_name}")
    
    self.bgp_groups[group_name] = validated_as
```

#### Serialization Support
```python
def to_dict(self) -> dict:
    """Convert RouterProfile to dictionary for JSON serialization"""
    return {
        'hostname': self.hostname,
        'ip_address': self.ip_address,
        'discovered_as_numbers': sorted(list(self.discovered_as_numbers)),
        'bgp_groups': self.bgp_groups,
        'metadata': self.metadata,
        'config_length': len(self.bgp_config)  # Security: don't include full config
    }

@classmethod
def from_dict(cls, data: dict) -> 'RouterProfile':
    """Create RouterProfile from dictionary"""
    return cls(
        hostname=data['hostname'],
        ip_address=data['ip_address'],
        bgp_config="",  # Config not included in serialization for security
        discovered_as_numbers=set(data.get('discovered_as_numbers', [])),
        bgp_groups=data.get('bgp_groups', {}),
        metadata=data.get('metadata', {})
    )
```

### DeviceInfo Implementation

#### CSV Integration
```python
@classmethod
def from_csv_row(cls, row: dict) -> 'DeviceInfo':
    """Create DeviceInfo from CSV row with validation"""
    # Required fields validation
    if 'address' not in row or not row['address'].strip():
        raise ValueError("CSV row missing required 'address' field")
    
    return cls(
        address=row['address'].strip(),
        hostname=row.get('hostname', '').strip(),  # Will auto-generate if empty
        username=row.get('username'),
        password=row.get('password'),
        port=int(row.get('port', 22)),
        role=row.get('role'),
        region=row.get('region')
    )

def __post_init__(self):
    """Validate and auto-generate hostname for backward compatibility"""
    if not self.hostname:
        # Auto-generate hostname from IP for backward compatibility
        self.hostname = f"router-{self.address.replace('.', '-')}"
    
    # Validate hostname format
    if not re.match(r'^[a-zA-Z0-9.-]+$', self.hostname):
        raise ValueError(f"Invalid hostname format: {self.hostname}")
```

#### Router Profile Conversion
```python
def to_router_profile(self) -> RouterProfile:
    """Convert DeviceInfo to RouterProfile"""
    return RouterProfile(
        hostname=self.hostname,
        ip_address=self.address,
        metadata={
            'port': self.port,
            'role': self.role,
            'region': self.region,
            'source': 'device_info'
        }
    )
```

### PipelineResult Implementation

#### Statistics Generation
```python
def __post_init__(self):
    """Calculate statistics after initialization"""
    if not self.statistics:
        self.statistics = {
            'total_routers': len(self.router_profiles),
            'total_as_numbers': len(self.get_all_as_numbers()),
            'total_bgp_groups': sum(len(p.bgp_groups) for p in self.router_profiles),
            'execution_time': None  # Set by pipeline
        }

def get_all_as_numbers(self) -> Set[int]:
    """Get all unique AS numbers across all routers"""
    all_as = set()
    for profile in self.router_profiles:
        all_as.update(profile.discovered_as_numbers)
    return all_as
```

#### Router Lookup and Summary
```python
def get_router_by_hostname(self, hostname: str) -> Optional[RouterProfile]:
    """Find a router profile by hostname"""
    for profile in self.router_profiles:
        if profile.hostname == hostname:
            return profile
    return None

def to_summary(self) -> str:
    """Generate a summary string of the pipeline result"""
    lines = [
        f"Pipeline {'succeeded' if self.success else 'failed'}",
        f"Routers processed: {self.statistics['total_routers']}",
        f"AS numbers discovered: {self.statistics['total_as_numbers']}",
        f"BGP groups found: {self.statistics['total_bgp_groups']}"
    ]
    
    if self.errors:
        lines.append(f"Errors: {len(self.errors)}")
        for error in self.errors[:3]:  # Show first 3 errors
            lines.append(f"  - {error}")
    
    return "\n".join(lines)
```

## Security Considerations

### Data Validation
```python
# AS number range validation
def validate_as_number_range(as_number: int) -> bool:
    """Validate AS number is within RFC-compliant range"""
    return 0 <= as_number <= 4294967295

# Hostname sanitization
def sanitize_hostname(hostname: str) -> str:
    """Sanitize hostname to prevent injection attacks"""
    # Allow only alphanumeric, dots, hyphens
    sanitized = re.sub(r'[^a-zA-Z0-9.-]', '', hostname)
    if not sanitized:
        raise ValueError("Hostname contains no valid characters")
    return sanitized
```

### Configuration Data Security
- **BGP config exclusion**: Full configurations not included in serialization
- **Credential sanitization**: No passwords or keys in metadata
- **Size limits**: Configuration data size validation
- **Content filtering**: Remove binary or suspicious content

### Input Validation
- **CSV injection prevention**: Sanitize all CSV input fields
- **Path traversal prevention**: Validate file paths and hostnames
- **Type validation**: Ensure data types match schema expectations
- **Range validation**: Validate numeric fields within expected ranges

## Integration Patterns

### With Collectors Module
```python
# Collectors create and populate RouterProfile
def collect_router_data(device: DeviceInfo) -> RouterProfile:
    """Convert device info to router profile with BGP data"""
    profile = device.to_router_profile()
    
    # Collect BGP configuration
    bgp_config = ssh_collector.collect_bgp_config(device.address)
    profile.bgp_config = bgp_config
    
    # Update metadata
    profile.metadata.update({
        'collected_at': datetime.now().isoformat(),
        'collection_method': 'ssh',
        'config_size': len(bgp_config)
    })
    
    return profile
```

### With Discovery Module
```python
# Discovery enhances RouterProfile with AS mappings
def enhance_with_discovery(profile: RouterProfile) -> RouterProfile:
    """Add BGP group and AS number discovery results"""
    
    # Parse BGP configuration
    parser = BGPConfigParser()
    bgp_groups = parser.parse_bgp_groups(profile.bgp_config)
    
    # Extract AS numbers
    all_as_numbers = set()
    group_mappings = {}
    
    for group in bgp_groups:
        as_numbers = parser.extract_as_numbers(group.config)
        all_as_numbers.update(as_numbers)
        group_mappings[group.name] = list(as_numbers)
    
    # Update profile
    profile.discovered_as_numbers = all_as_numbers
    profile.bgp_groups = group_mappings
    
    return profile
```

### With Pipeline Module
```python
# Pipeline orchestrates data flow through models
def execute_pipeline(devices: List[DeviceInfo]) -> PipelineResult:
    """Execute complete pipeline using data models"""
    
    router_profiles = []
    errors = []
    
    for device in devices:
        try:
            # Convert to router profile
            profile = device.to_router_profile()
            
            # Collect BGP data
            profile = collector.collect_router_data(profile)
            
            # Enhance with discovery
            profile = discovery.enhance_with_discovery(profile)
            
            router_profiles.append(profile)
            
        except Exception as e:
            errors.append(f"Failed to process {device.hostname}: {e}")
    
    # Create result
    return PipelineResult(
        router_profiles=router_profiles,
        success=len(errors) == 0,
        errors=errors
    )
```

## Development Guidelines

### Model Evolution
```python
# Backward compatibility for model changes
@classmethod
def from_dict_v1(cls, data: dict) -> 'RouterProfile':
    """Handle legacy format for backward compatibility"""
    # Convert old format to new format
    if 'device_name' in data:
        data['hostname'] = data.pop('device_name')
    
    if 'management_ip' in data:
        data['ip_address'] = data.pop('management_ip')
    
    return cls.from_dict(data)
```

### Usage Examples
```python
# Factory functions for example data
def create_example_router_profile(hostname: str = "edge-router") -> RouterProfile:
    """Create RouterProfile for examples"""
    return RouterProfile(
        hostname=hostname,
        ip_address="192.168.1.1",
        discovered_as_numbers={13335, 15169},
        bgp_groups={"CUSTOMERS": [64512], "TRANSIT": [13335]},
        metadata={"platform": "junos", "role": "production"}
    )

def create_example_device_info(address: str = "192.168.1.1") -> DeviceInfo:
    """Create DeviceInfo for examples"""
    return DeviceInfo(
        address=address,
        hostname=f"router-{address.replace('.', '-')}",
        role="edge"
    )
```

### Validation Usage
```python
def validate_as_number_usage():
    """Demonstrate AS number validation"""
    profile = RouterProfile(hostname="edge-router", ip_address="1.1.1.1")
    
    # Valid AS numbers
    profile.add_as_number(13335)
    profile.add_as_number(64512)
    assert 13335 in profile.discovered_as_numbers
    assert 64512 in profile.discovered_as_numbers
    
    # Invalid AS numbers will raise ValueError
    try:
        profile.add_as_number(-1)
    except ValueError as e:
        print(f"Invalid AS number rejected: {e}")
    
    try:
        profile.add_as_number(4294967296)  # Beyond 32-bit range
    except ValueError as e:
        print(f"AS number out of range: {e}")

def validate_hostname_usage():
    """Demonstrate hostname validation"""
    # Valid hostname
    device = DeviceInfo(address="1.1.1.1", hostname="valid-router")
    assert device.hostname == "valid-router"
    
    # Invalid hostname handling
    try:
        DeviceInfo(address="1.1.1.1", hostname="invalid; hostname")
    except ValueError as e:
        print(f"Invalid hostname rejected: {e}")
```

## Best Practices

### Data Integrity
- Always validate data at model boundaries
- Use type hints for all fields
- Implement comprehensive `__post_init__` validation
- Provide clear error messages for validation failures

### Performance
- Use appropriate data structures (sets for unique collections)
- Avoid unnecessary data copying
- Implement efficient lookup methods
- Consider memory usage for large router fleets

### Serialization
- Exclude sensitive data from serialization
- Maintain backward compatibility for schema changes
- Use standard formats (JSON, YAML) for interoperability
- Document serialization format changes

### Security
- Validate all external data before model creation
- Sanitize hostnames and identifiers
- Never store credentials in model data
- Implement size limits for configuration data

## v0.3.2 Data Models

### ApplicationResult
**Purpose**: Track policy application results with autonomous mode support

```python
@dataclass
class ApplicationResult:
    """Result of policy application stage"""
    router: str                                    # Target router hostname
    success: bool                                  # Application success status
    autonomous: bool = False                       # Whether applied autonomously
    policies_applied: int = 0                      # Number of policies applied
    commit_id: Optional[str] = None               # NETCONF commit identifier
    error_message: Optional[str] = None           # Error details if failed
    rollback_attempted: bool = False              # Whether rollback was attempted
    email_notifications_sent: int = 0            # Number of emails sent
    risk_level: str = "unknown"                  # Safety risk assessment
    manual_approval_required: bool = False       # Whether manual approval needed
    timestamp: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        """Validate application result data"""
        if self.policies_applied < 0:
            raise ValueError("policies_applied cannot be negative")
        
        if self.email_notifications_sent < 0:
            raise ValueError("email_notifications_sent cannot be negative")
        
        if self.risk_level not in ["low", "medium", "high", "unknown"]:
            raise ValueError(f"Invalid risk_level: {self.risk_level}")
```

#### ApplicationResult Usage Patterns

```python
# Successful autonomous application
result = ApplicationResult(
    router="edge-router1.company.com",
    success=True,
    autonomous=True,
    policies_applied=3,
    commit_id="20250817-143015-001",
    email_notifications_sent=5,
    risk_level="low"
)

# Failed application with rollback
result = ApplicationResult(
    router="core-router2.company.com",
    success=False,
    autonomous=True,
    error_message="Configuration conflict detected",
    rollback_attempted=True,
    email_notifications_sent=2,
    risk_level="medium"
)

# Manual approval required
result = ApplicationResult(
    router="transit-router1.company.com",
    success=False,
    autonomous=False,
    manual_approval_required=True,
    risk_level="high"
)
```

### Enhanced PipelineContext (v0.3.2)
**Purpose**: Extended pipeline context with autonomous mode support

```python
@dataclass
class PipelineContext:
    """Enhanced pipeline context with autonomous mode support"""
    
    # Core pipeline data
    devices: List[DeviceInfo] = field(default_factory=list)
    router_profiles: List[RouterProfile] = field(default_factory=list)
    policy_results: List[PolicyResult] = field(default_factory=list)
    
    # v0.3.2 autonomous mode extensions
    application_results: List[ApplicationResult] = field(default_factory=list)
    autonomous_config: Dict = field(default_factory=dict)
    safety_manager: Optional['UnifiedSafetyManager'] = None
    email_notifications_sent: int = 0
    
    # Enhanced metadata
    config: Dict = field(default_factory=dict)
    current_stage: str = "initialized"
    stage_timings: Dict[str, float] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    
    def get_autonomous_summary(self) -> Dict[str, Any]:
        """Generate autonomous operation summary"""
        if not self.application_results:
            return {"autonomous_operations": 0}
        
        total = len(self.application_results)
        autonomous = len([r for r in self.application_results if r.autonomous])
        successful = len([r for r in self.application_results if r.success])
        manual_required = len([r for r in self.application_results if r.manual_approval_required])
        
        return {
            "autonomous_operations": autonomous,
            "total_operations": total,
            "success_rate": successful / total if total > 0 else 0,
            "manual_approval_required": manual_required,
            "email_notifications_sent": self.email_notifications_sent
        }
```

### NotificationEvent (v0.3.2)
**Purpose**: NETCONF event tracking for email notifications

```python
@dataclass
class NotificationEvent:
    """NETCONF event for email notification"""
    event_type: str                               # connect, preview, commit, rollback, disconnect
    hostname: str                                 # Target router
    success: bool                                 # Event success status
    timestamp: datetime = field(default_factory=datetime.now)
    details: Dict[str, Any] = field(default_factory=dict)
    notification_sent: bool = False
    email_addresses: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Validate notification event"""
        valid_events = ["connect", "preview", "commit", "rollback", "disconnect"]
        if self.event_type not in valid_events:
            raise ValueError(f"Invalid event_type: {self.event_type}, must be one of {valid_events}")
        
        if not self.hostname:
            raise ValueError("hostname is required")
    
    def to_email_subject(self, prefix: str = "[Otto BGP Autonomous]") -> str:
        """Generate email subject line"""
        status = "SUCCESS" if self.success else "FAILED"
        return f"{prefix} {self.event_type.upper()} - {status}"
    
    def to_email_body(self) -> str:
        """Generate email body content"""
        status = "SUCCESS" if self.success else "FAILED"
        
        body = f"""NETCONF Event Notification
==========================
Event Type: {self.event_type.upper()}
Status: {status}
Router: {self.hostname}
Timestamp: {self.timestamp.isoformat()}"""
        
        if self.details:
            body += f"\n\nDetails:\n"
            for key, value in self.details.items():
                body += f"{key}: {value}\n"
        
        return body
```

### ConfigurationChange (v0.3.2)
**Purpose**: Track configuration changes for audit trails

```python
@dataclass
class ConfigurationChange:
    """Configuration change tracking"""
    router: str                                   # Target router
    change_type: str                             # add, modify, delete
    policy_name: str                             # Affected policy
    as_number: int                               # Related AS number
    diff: str                                    # Configuration diff
    commit_id: Optional[str] = None              # NETCONF commit ID
    timestamp: datetime = field(default_factory=datetime.now)
    applied_by: str = "autonomous"               # autonomous, manual, system
    risk_level: str = "unknown"                 # Safety assessment
    
    def __post_init__(self):
        """Validate configuration change"""
        valid_types = ["add", "modify", "delete"]
        if self.change_type not in valid_types:
            raise ValueError(f"Invalid change_type: {self.change_type}")
        
        if not (0 <= self.as_number <= 4294967295):
            raise ValueError(f"Invalid AS number: {self.as_number}")
    
    def to_audit_record(self) -> Dict[str, Any]:
        """Convert to audit record format"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "router": self.router,
            "change_type": self.change_type,
            "policy_name": self.policy_name,
            "as_number": self.as_number,
            "applied_by": self.applied_by,
            "risk_level": self.risk_level,
            "commit_id": self.commit_id
        }
```

## v0.3.2 Best Practices

### Autonomous Mode Data Handling

1. **Always track application results**: Use ApplicationResult for all policy applications
2. **Maintain audit trails**: Record all NETCONF events with NotificationEvent
3. **Risk assessment integration**: Include risk_level in all change tracking
4. **Email notification tracking**: Monitor notification delivery success

### Error Handling Enhancements

```python
# Comprehensive error tracking in ApplicationResult
try:
    result = apply_policies_autonomous(policies)
except Exception as e:
    result = ApplicationResult(
        router=hostname,
        success=False,
        autonomous=True,
        error_message=str(e),
        rollback_attempted=True,
        risk_level="high"
    )
```

### Performance Considerations

- **Batch notifications**: Group multiple events for efficient email delivery
- **Async logging**: Use asynchronous logging for high-frequency events
- **Memory management**: Clean up large diff content after processing
- **Connection pooling**: Reuse SMTP connections for multiple notifications
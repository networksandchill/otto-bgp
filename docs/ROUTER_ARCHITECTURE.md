# Otto BGP v0.3.2 Router-Aware Architecture

## Overview

Otto BGP v0.3.2 introduces a router-aware architecture that transforms BGP policy management from a simple AS-centric approach to a sophisticated router-specific policy generation system with autonomous operation capabilities. This document details the architectural components and their interactions.

## Core Architecture Components

### 1. Router Identity Foundation

The router identity system provides unique identification and profile management for each router in the network.

#### RouterProfile Model
```python
@dataclass
class RouterProfile:
    hostname: str           # Unique router identifier
    address: str            # Management IP address
    model: Optional[str]    # Hardware model (e.g., MX960, MX480)
    version: Optional[str]  # OS version
    role: Optional[str]     # Network role (edge, core, transit)
    location: Optional[str] # Physical/logical location
    bgp_config: Optional[Dict] = None  # Raw BGP configuration
```

#### DeviceInfo Model
```python
@dataclass
class DeviceInfo:
    hostname: str
    address: str
    username: Optional[str] = None
    password: Optional[str] = None
    port: int = 22
```

### 2. Discovery Engine

The discovery engine automatically inspects routers to understand their BGP configurations and relationships.

#### RouterInspector
- Parses BGP configuration from routers
- Identifies BGP groups and their AS numbers
- Maps AS numbers to specific BGP groups
- Tracks export/import policies

#### Key Methods:
- `inspect_router(profile: RouterProfile) -> DiscoveryResult`
- `parse_bgp_groups(config: str) -> List[BGPGroup]`
- `extract_as_numbers(group_config: str) -> Set[int]`

### 3. Policy Generation Engine

Generates router-specific BGP policies based on discovered configurations.

#### Router-Specific Generation
- Policies generated per router based on its BGP groups
- AS numbers associated with specific groups
- Customized policy names per router context

#### BGPq4Wrapper Enhancements
- Proxy support for restricted networks
- Router context tracking in generation results
- Performance optimizations for batch generation

### 4. Policy Application System

Automated policy deployment to routers via NETCONF/PyEZ.

#### JuniperPolicyApplier
- NETCONF-based configuration management
- Atomic policy updates with rollback capability
- Confirmation-based commits for safety

#### Safety Features:
- Policy validation before application
- BGP session impact analysis
- Automatic rollback on errors
- Dry-run capability

### 5. IRR Proxy Support

Enables policy generation in restricted network environments.

#### IRRProxyManager
- SSH tunnel management for IRR access
- Automatic tunnel health monitoring
- Transparent BGPq4 command wrapping
- Multi-tunnel support for redundancy

## Data Flow Architecture

```
1. Discovery Phase:
   CSV Input → DeviceInfo → JuniperSSHCollector → RouterProfile
                                     ↓
                            RouterInspector → DiscoveryResult
                                     ↓
                            YAMLGenerator → Router Mappings

2. Policy Generation Phase:
   Router Mappings → ASNumberExtractor → AS Numbers
                            ↓
                    BGPq4Wrapper → Policy Generation
                            ↓
                    DirectoryManager → Router-Specific Policies

3. Application Phase:
   Router Policies → PolicyAdapter → JuniperPolicyApplier
                            ↓
                    UnifiedSafetyManager → Validation
                            ↓
                    NETCONF → Router Configuration
```

## Directory Structure

```
policies/
├── discovered/
│   ├── router_mappings.yaml      # AS-to-router mappings
│   ├── router_inventory.yaml     # Router profiles
│   └── history/                  # Historical mappings
├── routers/
│   ├── router1/
│   │   ├── AS12345_policy.txt    # Router-specific policies
│   │   ├── AS67890_policy.txt
│   │   └── metadata.json         # Generation metadata
│   └── router2/
│       ├── AS11111_policy.txt
│       └── metadata.json
└── reports/
    ├── discovery_diff.txt        # Change reports
    └── application_log.txt       # Deployment logs
```

## Router Discovery Process

### 1. BGP Configuration Collection
```python
# Collect raw BGP configuration
bgp_config = collector.collect_bgp_config(device.address)
```

### 2. Configuration Parsing
```python
# Parse BGP groups and AS numbers
result = inspector.inspect_router(profile)
# Result contains:
# - bgp_groups: List of BGP group configurations
# - as_numbers: Set of discovered AS numbers
# - group_as_mapping: Group-to-AS associations
```

### 3. Mapping Generation
```python
# Generate YAML mappings
mappings = yaml_gen.generate_mappings(profiles)
# Creates:
# - Router-to-AS mappings
# - AS-to-router reverse mappings
# - BGP group inventories
```

## Policy Generation Process

### 1. Router-Specific AS Lists
```python
# Get AS numbers for specific router
router_as_numbers = mappings['routers'][hostname]['discovered_as_numbers']
```

### 2. Batch Generation with Context
```python
# Generate policies with router context
for router in routers:
    policies = bgpq4.generate_policies_batch(
        router.as_numbers,
        router_context=router.hostname
    )
```

### 3. Router-Specific Storage
```python
# Store in router-specific directory
dir_mgr.save_router_policies(router.hostname, policies)
```

## Policy Application Process

### 1. Policy Loading
```python
# Load router-specific policies
policies = applier.load_router_policies(f"policies/routers/{hostname}")
```

### 2. Safety Validation
```python
# Validate before application
safety_result = safety.validate_policies_before_apply(policies)
if not safety_result.safe_to_proceed:
    abort_application()
```

### 3. NETCONF Application
```python
# Apply with confirmation
result = applier.apply_with_confirmation(
    policies=policies,
    confirm_timeout=120,
    comment="Otto BGP policy update"
)
```

## Security Architecture

### Host Key Verification
- Strict SSH host key checking
- Known hosts file management
- Setup mode for initial key collection

### Command Injection Prevention
- AS number validation (0-4294967295)
- Policy name sanitization
- No shell command construction

### Process Management
- Signal handlers for cleanup
- Automatic tunnel termination
- Resource leak prevention

## Performance Optimizations

### Parallel Processing
- Concurrent router discovery
- Parallel policy generation
- Batch BGPq4 execution

### Caching Strategy
- Discovery result caching
- Policy generation caching
- Connection pooling

### Progress Tracking
- Real-time status updates
- Progress indicators
- Completion estimates

## Error Handling

### Graceful Degradation
- Continue on partial failures
- Collect all errors for reporting
- Maintain partial results

### Rollback Capabilities
- Configuration rollback on error
- State restoration
- Audit trail maintenance

## Monitoring and Reporting

### Discovery Reports
- Changes detected between runs
- New AS numbers discovered
- Removed or modified groups

### Application Reports
- Policies applied successfully
- Failed applications
- Rollback events

### Performance Metrics
- Discovery duration per router
- Policy generation time
- Application success rate

## Future Enhancements

### Planned Features
- Multi-vendor support (Cisco, Arista)
- REST API for integration
- Web UI for management
- Historical configuration tracking
- Automated rollback triggers

### Scalability Improvements
- Distributed processing
- Database backend
- Event-driven updates
- Real-time synchronization
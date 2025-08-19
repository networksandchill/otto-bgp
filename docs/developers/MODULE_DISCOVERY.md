# otto_bgp.discovery Module - Developer Guide

## Overview

The `discovery` module provides **automatic BGP configuration analysis** and **router relationship mapping**. It transforms raw BGP configurations into structured router profiles and AS number mappings, enabling Otto BGP's router-aware architecture.

**Core Principle**: "Zero YAML maintenance" - all discovery files are READ-ONLY and auto-generated.

## Architecture Role

```
BGP Pipeline Flow:
Collection → [DISCOVERY] → Processing → Policy Generation → Application

Key Responsibilities:
- Parse BGP configurations from collected router data
- Extract AS numbers and BGP group relationships
- Generate router-to-AS mappings
- Maintain historical discovery data with change tracking
```

## Core Components

### 1. RouterInspector (`inspector.py`)
**Purpose**: Main discovery orchestrator and BGP configuration analysis

**Key Features**:
- Coordinates BGP configuration parsing
- Manages router profile creation
- Tracks discovery results and metadata
- Integrates with collectors and processors

**Design Pattern**: Facade pattern providing unified discovery interface

### 2. BGPConfigParser (`parser.py`)
**Purpose**: Specialized Juniper BGP configuration parser

**Key Features**:
- Parses Juniper BGP group configurations
- Extracts AS numbers from peer configurations
- Identifies import/export policy assignments
- Handles nested BGP group hierarchies

**Parser Architecture**:
```python
class BGPConfigParser:
    def parse_bgp_groups(self, config: str) -> List[BGPGroup]
    def extract_as_numbers(self, group_config: str) -> Set[int]
    def find_policy_assignments(self, config: str) -> Dict[str, List[str]]
```

### 3. YAMLGenerator (`yaml_generator.py`)
**Purpose**: Auto-maintained YAML mapping generation with history

**Key Features**:
- Generates router-to-AS mappings
- Maintains discovery history for change tracking
- Creates structured output for policy generation
- Preserves historical mappings for audit trails

**Output Structure**:
```yaml
# auto-generated - DO NOT EDIT
routers:
  edge-router-01:
    discovered_as_numbers: [13335, 15169, 7922]
    bgp_groups:
      CUSTOMERS: [64512, 64513]
      TRANSIT: [13335, 15169]
as_to_routers:
  13335: [edge-router-01, core-router-01]
  15169: [edge-router-01]
metadata:
  generated_at: "2024-01-15T10:30:00Z"
  otto_version: "0.3.2"
```

## Security Architecture

### Configuration Parsing Security
```python
# Safe parsing patterns
def parse_bgp_config(self, config: str) -> ParseResult:
    # Validate input size
    if len(config) > MAX_CONFIG_SIZE:
        raise ValueError("Configuration too large")
    
    # Sanitize input
    clean_config = self._sanitize_config(config)
    
    # Parse with timeout
    with timeout(PARSE_TIMEOUT):
        return self._parse_config(clean_config)

def _sanitize_config(self, config: str) -> str:
    # Remove potentially dangerous content
    # Strip binary data, normalize line endings
    return re.sub(r'[^\x20-\x7E\n\r\t]', '', config)
```

### Data Validation
- **AS number range validation** (0-4294967295)
- **Router hostname sanitization** (alphanumeric, dash, dot only)
- **BGP group name validation** (standard naming conventions)
- **Configuration size limits** (prevent DoS attacks)

## Code Structure

### Class Hierarchy
```
RouterInspector
├── ConfigValidator (input validation)
├── ParserOrchestrator (parsing coordination)
├── ResultAggregator (discovery result compilation)
└── MetadataGenerator (discovery metadata)

BGPConfigParser
├── GroupExtractor (BGP group identification)
├── ASNumberExtractor (AS number parsing)
├── PolicyMapper (policy assignment tracking)
└── HierarchyResolver (nested group handling)

YAMLGenerator
├── MappingBuilder (router-AS relationship building)
├── HistoryManager (change tracking)
├── FileManager (YAML file operations)
└── DiffGenerator (change reporting)
```

### Data Flow
```python
# 1. Router configuration analysis
for profile in router_profiles:
    # Parse BGP configuration
    bgp_groups = parser.parse_bgp_groups(profile.bgp_config)
    
    # Extract AS numbers
    as_numbers = set()
    for group in bgp_groups:
        as_numbers.update(parser.extract_as_numbers(group.config))
    
    # Update router profile
    profile.discovered_as_numbers = as_numbers
    profile.bgp_groups = {g.name: g.as_numbers for g in bgp_groups}

# 2. Generate mappings
mappings = yaml_generator.generate_mappings(router_profiles)

# 3. Save with history
yaml_generator.save_with_history(mappings, output_dir)
```

## Design Choices

### Parser-First Architecture
**Choice**: Dedicated BGP configuration parser before AS extraction
**Rationale**:
- Preserves BGP group context information
- Enables router-aware policy generation
- Supports complex BGP hierarchy parsing
- Maintains relationship mappings

### Auto-Generated YAML Files
**Choice**: Machine-generated mapping files with history
**Rationale**:
- Eliminates manual YAML maintenance
- Prevents configuration drift
- Enables automated change tracking
- Supports reproducible builds

### Read-Only Discovery Files
**Choice**: All discovery output files are read-only
**Rationale**:
- Prevents accidental manual modifications
- Ensures consistency with source data
- Enables safe regeneration
- Simplifies troubleshooting

### Historical Change Tracking
**Choice**: Maintain discovery history with diffs
**Rationale**:
- Audit trail for network changes
- Change detection for monitoring
- Rollback capability for discovery
- Operational troubleshooting support

## BGP Configuration Parsing

### Juniper BGP Group Structure
```junos
protocols {
    bgp {
        group CUSTOMERS {
            type external;
            neighbor 192.168.1.1 {
                peer-as 64512;
            }
            neighbor 192.168.1.2 {
                peer-as 64513;
            }
        }
        group TRANSIT {
            type external;
            import TRANSIT-IN;
            export TRANSIT-OUT;
            neighbor 10.0.1.1 {
                peer-as 13335;
            }
        }
    }
}
```

### Parsing Strategy
```python
class BGPConfigParser:
    def parse_bgp_groups(self, config: str) -> List[BGPGroup]:
        """Parse BGP groups and their configurations"""
        groups = []
        
        # Find all BGP group definitions
        group_pattern = r'group\s+(\S+)\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}'
        
        for match in re.finditer(group_pattern, config, re.MULTILINE | re.DOTALL):
            group_name = match.group(1)
            group_config = match.group(2)
            
            # Extract AS numbers from neighbors
            as_numbers = self.extract_as_numbers(group_config)
            
            # Parse policy assignments
            policies = self.extract_policies(group_config)
            
            groups.append(BGPGroup(
                name=group_name,
                as_numbers=list(as_numbers),
                import_policies=policies.get('import', []),
                export_policies=policies.get('export', [])
            ))
        
        return groups
```

### AS Number Extraction
```python
def extract_as_numbers(self, config: str) -> Set[int]:
    """Extract AS numbers with validation"""
    as_numbers = set()
    
    # Match peer-as statements
    peer_as_pattern = r'peer-as\s+(\d+)'
    
    for match in re.finditer(peer_as_pattern, config):
        as_str = match.group(1)
        
        try:
            as_number = int(as_str)
            
            # Validate AS number range (32-bit)
            if 0 <= as_number <= 4294967295:
                as_numbers.add(as_number)
            else:
                logger.warning(f"Invalid AS number {as_number} - out of range")
                
        except ValueError:
            logger.warning(f"Invalid AS number format: {as_str}")
    
    return as_numbers
```

## YAML Generation and History

### Mapping Structure
```python
def generate_mappings(self, router_profiles: List[RouterProfile]) -> Dict:
    """Generate complete router-AS mappings"""
    mappings = {
        'routers': {},
        'as_to_routers': defaultdict(list),
        'bgp_groups': {},
        'metadata': {
            'generated_at': datetime.now().isoformat(),
            'otto_version': __version__,
            'router_count': len(router_profiles),
            'total_as_numbers': 0
        }
    }
    
    # Build router mappings
    for profile in router_profiles:
        mappings['routers'][profile.hostname] = {
            'ip_address': profile.ip_address,
            'discovered_as_numbers': sorted(list(profile.discovered_as_numbers)),
            'bgp_groups': profile.bgp_groups,
            'metadata': profile.metadata
        }
        
        # Build reverse AS-to-router mappings
        for as_number in profile.discovered_as_numbers:
            mappings['as_to_routers'][as_number].append(profile.hostname)
    
    # Update metadata
    all_as = set()
    for router_data in mappings['routers'].values():
        all_as.update(router_data['discovered_as_numbers'])
    mappings['metadata']['total_as_numbers'] = len(all_as)
    
    return mappings
```

### History Management
```python
def save_with_history(self, mappings: Dict, output_dir: Path):
    """Save mappings with historical tracking"""
    
    # Create output directory structure
    discovery_dir = output_dir / "discovered"
    history_dir = discovery_dir / "history"
    
    discovery_dir.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(exist_ok=True)
    
    # Current mapping files
    current_file = discovery_dir / "router_mappings.yaml"
    
    # Check for changes
    if current_file.exists():
        with open(current_file, 'r') as f:
            previous_mappings = yaml.safe_load(f)
        
        # Generate diff
        diff = self.generate_diff(previous_mappings, mappings)
        
        if diff['has_changes']:
            # Archive previous version
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            archive_file = history_dir / f"router_mappings_{timestamp}.yaml"
            shutil.copy2(current_file, archive_file)
            
            # Save diff report
            diff_file = history_dir / f"changes_{timestamp}.yaml"
            with open(diff_file, 'w') as f:
                yaml.dump(diff, f, default_flow_style=False)
            
            logger.info(f"Discovery changes detected - archived to {archive_file}")
    
    # Save current mappings
    with open(current_file, 'w') as f:
        f.write("# Auto-generated by Otto BGP Discovery Engine\n")
        f.write("# DO NOT EDIT - This file is automatically maintained\n\n")
        yaml.dump(mappings, f, default_flow_style=False, sort_keys=True)
```

## Integration Points

### CLI Interface
```bash
# Discover routers and generate mappings
./otto-bgp discover devices.csv --output-dir policies

# Show changes from previous discovery
./otto-bgp discover devices.csv --show-diff

# List discovered resources
./otto-bgp list routers --output-dir policies
./otto-bgp list as --output-dir policies
./otto-bgp list groups --output-dir policies
```

### Python API
```python
from otto_bgp.discovery import RouterInspector, YAMLGenerator

inspector = RouterInspector()
yaml_gen = YAMLGenerator(output_dir=Path("policies"))

# Analyze router profiles
for profile in router_profiles:
    discovery_result = inspector.inspect_router(profile)
    profile.discovered_as_numbers = discovery_result.as_numbers
    profile.bgp_groups = discovery_result.bgp_groups

# Generate and save mappings
mappings = yaml_gen.generate_mappings(router_profiles)
yaml_gen.save_with_history(mappings, output_dir)
```

### Pipeline Integration
- **Input**: RouterProfile objects with BGP configurations
- **Output**: Updated RouterProfile objects with discovery data
- **Side Effects**: Generated YAML mapping files
- **Change Detection**: Diff reports for operational monitoring

## Error Handling

### Parsing Errors
```python
def parse_with_error_recovery(self, config: str) -> ParseResult:
    """Parse configuration with graceful error handling"""
    result = ParseResult()
    
    try:
        # Attempt full parsing
        result.bgp_groups = self.parse_bgp_groups(config)
        result.success = True
        
    except ConfigurationParseError as e:
        # Partial parsing on syntax errors
        logger.warning(f"Configuration parse error: {e}")
        
        # Attempt AS extraction only
        try:
            result.as_numbers = self.extract_as_numbers_fallback(config)
            result.partial_success = True
            result.warnings.append(f"Partial parsing only: {e}")
            
        except Exception as fallback_error:
            result.success = False
            result.errors.append(f"Complete parse failure: {fallback_error}")
    
    return result
```

### File Operation Errors
- **Permission errors**: Fallback to read-only mode
- **Disk space errors**: Cleanup old history files
- **YAML format errors**: Validate before writing
- **Concurrent access**: File locking for multi-process safety

## Performance Optimization

### Parser Performance
```python
# Compiled regex patterns for performance
BGP_GROUP_PATTERN = re.compile(
    r'group\s+(\S+)\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}',
    re.MULTILINE | re.DOTALL
)

PEER_AS_PATTERN = re.compile(r'peer-as\s+(\d+)')

# Efficient parsing with pre-compiled patterns
def parse_bgp_groups_optimized(self, config: str) -> List[BGPGroup]:
    groups = []
    for match in self.BGP_GROUP_PATTERN.finditer(config):
        # Process match efficiently
        pass
    return groups
```

### Memory Management
- **Streaming parsing** for large configurations
- **Lazy loading** of historical data
- **Garbage collection** of temporary objects
- **Memory monitoring** for large router fleets

## Development Guidelines

### Testing Strategy
```python
# Unit tests with synthetic BGP configurations
def test_bgp_group_parsing():
    config = """
    group CUSTOMERS {
        neighbor 192.168.1.1 {
            peer-as 64512;
        }
    }
    """
    parser = BGPConfigParser()
    groups = parser.parse_bgp_groups(config)
    assert len(groups) == 1
    assert groups[0].name == "CUSTOMERS"
    assert 64512 in groups[0].as_numbers

# Integration tests with real configurations
def test_router_discovery_integration():
    inspector = RouterInspector()
    profile = RouterProfile(hostname="test", ip_address="1.1.1.1")
    profile.bgp_config = load_test_config("real_bgp_config.txt")
    
    result = inspector.inspect_router(profile)
    assert result.success
    assert len(result.as_numbers) > 0
```

### Documentation Standards
- **Parser method documentation** with BGP config examples
- **AS number validation** edge cases and limits
- **YAML structure documentation** with schema definitions
- **Change detection examples** for operational procedures

## Best Practices

### Configuration Parsing
- Validate AS number ranges before processing
- Handle malformed BGP configurations gracefully
- Log parsing warnings for operational awareness
- Use timeout controls for large configurations

### File Management
- Never manually edit discovery files
- Maintain reasonable history file retention
- Monitor disk usage for history directories
- Use atomic file operations for consistency

### Performance
- Profile parsing performance with large configurations
- Monitor memory usage during discovery
- Optimize regex patterns for common cases
- Cache compiled patterns across operations
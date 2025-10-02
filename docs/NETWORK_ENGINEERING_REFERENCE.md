# Network Engineering Reference - Otto BGP v0.3.2

## Overview

Otto BGP is an autonomous BGP policy generator that orchestrates transit traffic optimization. It collects BGP configuration data from Juniper routers via SSH, extracts AS numbers, validates them through RPKI, and generates prefix-list policies using bgpq4. The system includes comprehensive safety mechanisms and can apply policies via NETCONF with rollback capabilities.

## Juniper Router Configuration Requirements

### NETCONF Service Configuration

```junos
# Enable NETCONF over SSH on port 830
set system services netconf ssh

# Optional: Configure custom port
set system services netconf ssh port 830

# Enable configuration archival for rollback capability
set system archival configuration transfer-on-commit
set system archival configuration archive-sites "/var/tmp/config-archive"
```

### BGP User Account Configuration

Create a restricted user account for BGP policy management:

```junos
# Define BGP policy admin class with minimal required permissions
set system login class bgp-policy-admin permissions configure
set system login class bgp-policy-admin permissions view-configuration

# Allow specific configuration sections
set system login class bgp-policy-admin allow-configuration "policy-options prefix-list AS[0-9]+"
set system login class bgp-policy-admin allow-configuration "protocols bgp group .* import"

# Deny dangerous configuration sections
set system login class bgp-policy-admin deny-configuration "policy-options prefix-list (?!AS[0-9]+)"
set system login class bgp-policy-admin deny-configuration "protocols bgp group .* (?!import)"
set system login class bgp-policy-admin deny-configuration "system"
set system login class bgp-policy-admin deny-configuration "interfaces"
set system login class bgp-policy-admin deny-configuration "routing-options"

# Allow specific operational commands
set system login class bgp-policy-admin allow-commands "(show|commit|load|rollback|commit confirmed)"

# Create the user account
set system login user otto-bgp class bgp-policy-admin
set system login user otto-bgp authentication ssh-ed25519 "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExample..."

commit comment "Otto BGP user account setup"
```

### BGP Configuration Structure

Otto BGP expects standard Juniper BGP configuration syntax:

```junos
protocols {
    bgp {
        group transit-providers {
            type external;
            neighbor 203.0.113.1 {
                peer-as 13335;
                import [ reject-bogons accept-from-as13335 ];
                export [ default-route customer-routes ];
            }
        }
        group customers {
            type external;
            neighbor 203.0.113.100 {
                peer-as 65001;
                import [ accept-customer-routes ];
                export [ full-table ];
            }
        }
    }
}

policy-options {
    prefix-list AS13335 {
        1.1.1.0/24;
        1.0.0.0/24;
        /* bgpq4-generated prefixes */
    }
}
```

## SSH Host Key Security

### Router SSH Configuration Requirements

Otto BGP requires strict SSH host key verification to prevent man-in-the-middle attacks. Network engineers are responsible for router-side configuration and understanding scenarios that trigger SSH key regeneration.

#### SSH User Account Setup

Configure the Otto BGP user account on each router as shown in the BGP User Account Configuration section. The SSH public key will be provided by system administrators.

#### Router Console Verification

When system administrators report host key changes, verify the new fingerprint using router console commands:

```bash
# Display router's SSH host key
admin@router> file show /etc/ssh/ssh_host_ed25519_key.pub

# View recent system changes
admin@router> show system commit

# Check system uptime (should align with maintenance windows)  
admin@router> show system uptime

# Verify router model and software version
admin@router> show version | match Model
admin@router> show version | match Junos
```

#### Common Host Key Change Scenarios

Network engineers should be aware these scenarios regenerate router SSH host keys:

**Firmware/Software Operations:**
- JunOS upgrades and downgrades
- Software image changes or reinstallation
- Factory reset or complete reconfiguration

**Hardware Operations:**
- Routing engine replacement or upgrade
- Control plane hardware changes
- Full device replacement

**Security Operations:**
- Scheduled SSH key rotation policies
- Security incident response procedures
- Cryptographic key updates

#### Network Team Response Process

When Otto BGP reports host key verification failures:

1. **Verify Maintenance History**: Check if planned maintenance occurred on the affected device
2. **Confirm Device Identity**: Use router console commands to verify device details match inventory records
3. **Document New Fingerprint**: Record the new SSH key fingerprint in network documentation
4. **Coordinate with System Administrators**: Provide verified fingerprint information to system administrators for backend updates

**Critical Security Note**: If host key changes occur without corresponding maintenance activities, immediately investigate for potential security incidents before approving key updates.

### Host Key Fingerprint Verification

Network engineers should maintain documentation of expected SSH key fingerprints for all managed devices. When system administrators report fingerprint mismatches:

```bash
# Router console commands to verify current keys
admin@router> file show /etc/ssh/ssh_host_ed25519_key.pub
admin@router> file show /etc/ssh/ssh_host_rsa_key.pub
```

Compare the output with your network team's device records. Each device should have unique, documented fingerprints that match the router's actual keys.

**For backend SSH key management, file operations, and system troubleshooting procedures, see the System Administrator Guide.**

## NETCONF Protocol Requirements

### Connection Parameters

```python
# PyEZ Device parameters (actual implementation from juniper_netconf.py)
device_params = {
    'host': hostname,
    'port': port,            # default 830
    'gather_facts': True,
    'auto_probe': timeout    # connection timeout in seconds
}
# Note: username and password are optional - uses SSH config if not provided
# Otto BGP prefers SSH key-based authentication over passwords
```

### PyEZ Library Requirements

Otto BGP requires these Python libraries for NETCONF operations:

- junos-eznc (PyEZ): Juniper NETCONF automation library
- paramiko: SSH protocol implementation
- ncclient: NETCONF client protocol (dependency of PyEZ)
- lxml: XML parsing (dependency of PyEZ)
- jxmlease: XML handling (dependency of PyEZ)

**Note**: Otto BGP will function in collection-only mode if PyEZ is not installed. Install with: `pip install junos-eznc`

### Configuration Loading

NETCONF configuration operations use merge mode to preserve existing configuration:

```python
# Configuration merge operation from juniper_netconf.py
# Combines multiple policies into single configuration load
combined_config = self._combine_policies_for_load(policies)

# Load configuration in merge mode (doesn't replace existing)
self.config.load(combined_config, format='text', merge=True)

# Preview changes before applying
diff = self.config.diff()
if diff:
    logger.info(f"Configuration changes preview:\n{diff}")
```

### XML-RPC Command Structure

NETCONF uses XML-RPC for configuration operations:

```python
# Otto BGP uses PyEZ for NETCONF operations, not raw XML-RPC
# Actual policy combination from _combine_policies_for_load():
combined = []
combined.append("policy-options {")
for policy in policies:
    list_name = extract_prefix_list_name(policy['content'])
    list_content = extract_prefix_list_content(policy['content'])
    
    combined.append(f"    replace: prefix-list {list_name} {{")
    for line in list_content.strip().split('\n'):
        if line.strip():
            combined.append(f"        {line.strip()}")
    combined.append("    }")
combined.append("}")
```

## Permission Level Implementation

### Minimum Required Permissions

The bgp-policy-admin class requires these specific capabilities:

1. **Configuration Access**: Read and modify policy-options prefix-lists
2. **BGP Import Policies**: Modify import statements on BGP groups
3. **Commit Operations**: Execute commit, rollback, and commit confirmed
4. **Show Commands**: View configuration and operational status

### Configuration Boundary Enforcement

Regular expressions enforce configuration boundaries:

```junos
# Allow only AS number prefix-lists
allow-configuration "policy-options prefix-list AS[0-9]+"

# Allow only BGP import policy modifications  
allow-configuration "protocols bgp group .* import"

# Explicitly deny system modifications
deny-configuration "system"
deny-configuration "interfaces"
deny-configuration "routing-options"
```

### Command Execution Limits

Restrict available commands to safe operations:

```junos
allow-commands "(show|commit|load|rollback|commit confirmed)"
```

## Commit and Rollback Mechanisms

### Confirmed Commit Process

Confirmed commits provide automatic rollback capability:

```python
# Actual confirmed commit implementation from juniper_netconf.py
def apply_with_confirmation(self, policies, confirm_timeout=120, comment=None):
    if not comment:
        comment = f"Otto BGP v0.3.2 - Applied {len(policies)} policies"
    
    # Perform confirmed commit with timeout
    commit_result = self.config.commit(
        comment=comment,
        confirm=confirm_timeout  # Auto-rollback if not confirmed
    )
    
    # User must confirm within timeout period
    logger.warning(f"CONFIRMATION REQUIRED within {confirm_timeout} seconds!")
    
    return commit_result
```

### Automatic Rollback Triggers

Automatic rollback occurs when:

- Confirmation timeout expires (default 120 seconds)
- SSH connection terminates during confirmation window
- System reboot occurs during confirmation window
- Manual rollback command executed

### Rollback ID Management

Junos maintains rollback configurations with sequential IDs:

```bash
# View available rollback configurations
admin@router> show system rollback

# Rollback to specific configuration
admin@router> rollback 1
admin@router> commit comment "Manual rollback to previous config"
```

```python
# Programmatic rollback from juniper_netconf.py
def rollback_changes(self, rollback_id=None):
    rollback_id = rollback_id or 0  # Default to last change
    
    self.config.rollback(rollback_id)
    self.config.commit(comment=f"Otto BGP - Rollback to {rollback_id}")
    
    logger.info(f"Rollback to configuration {rollback_id} completed")
```

### Commit History Tracking

Every commit generates an entry with metadata:

```bash
# View commit history
admin@router> show system commit

# Example output:
0   2025-08-17 10:30:00 UTC by otto-bgp via netconf
    Otto BGP policy update - Applied 5 policies
1   2025-08-17 09:15:00 UTC by admin via cli
    Manual BGP neighbor configuration
```

## AS Number Validation

### RFC-Compliant Range Validation

AS numbers are strictly validated according to RFC 4893 specifications:

- **Valid Range**: 0 to 4294967295 (32-bit unsigned integer)
- **Reserved Ranges** (processed with warnings):
  - 0: Reserved (RFC 7607)
  - 23456: AS_TRANS (RFC 6793)
  - 64496-64511: Documentation (RFC 5398)
  - 64512-65534: Private use (RFC 6996)
  - 65535: Reserved (RFC 7300)
  - 65536-65551: Documentation (RFC 5398)
  - 4200000000-4294967294: Private use (RFC 6996)
  - 4294967295: Reserved (RFC 7300)

### Input Sanitization and Security

AS number validation prevents command injection and ensures data integrity:

```python
# Actual validation from bgpq4_wrapper.py
def validate_as_number(as_number) -> int:
    # Reject floats that could truncate
    if isinstance(as_number, float):
        raise ValueError(f"AS number must be integer, got float: {as_number}")
    
    # Convert string/other types to integer
    if not isinstance(as_number, int):
        try:
            as_number = int(as_number)
        except (ValueError, TypeError):
            raise ValueError(f"AS number must be convertible to int: {as_number}")
    
    # Validate RFC 4893 range (32-bit unsigned)
    if not 0 <= as_number <= 4294967295:
        raise ValueError(f"AS number out of valid range (0-4294967295): {as_number}")
    
    return as_number

# Additional filtering from as_extractor.py
# Automatically filters IP octets (≤255) to prevent false positives
# Warns about reserved AS ranges but still processes them
```

### bgpq4 Command Generation

Validated AS numbers generate safe bgpq4 commands:

```bash
# Generated command for AS 13335
bgpq4 -Jl 13335 AS13335

# Example output
policy-options {
    prefix-list 13335 {
        1.1.1.0/24;
        1.0.0.0/24;
        /* 2 entries */
    }
}
```

## Policy Generation Technical Details

### bgpq4 Execution Parameters

Otto BGP executes bgpq4 with these validated parameters:

```bash
# Actual command structure from bgpq4_wrapper.py
bgpq4 -Jl <validated_policy_name> AS<validated_as_number>
```

Parameter explanation:
- `-J`: Generate Juniper syntax output
- `-l <name>`: Set prefix-list name (AS number by default)
- `AS<number>`: Query specific AS number (strictly validated 0-4294967295)

**Security Features**:
- AS numbers validated against RFC 4893 range
- Policy names sanitized (alphanumeric, underscore, hyphen only)
- Command construction uses list format to prevent shell injection
- Configurable timeouts (default 45 seconds) with subprocess management

### Policy Name Generation

Otto BGP automatically generates policy names using AS numbers directly:

```python
# Actual policy generation from bgpq4_wrapper.py
def generate_policy_for_as(as_number: int, policy_name: str = None) -> PolicyGenerationResult:
    if policy_name is None:
        policy_name = str(as_number)  # Uses AS number directly
    
    # Validates policy name for security
    validated_name = validate_policy_name(policy_name)
    
    # Command construction with validation
    command = [bgpq4_path, '-Jl', validated_name, f'AS{as_number}']
```

**Policy Name Format**: Generated policies use the AS number directly (e.g., `prefix-list 13335` for AS13335).

### Policy Output Directory

Router-specific policies are stored with this structure (router-aware architecture):

```
policies/
├── edge-router-01/
│   ├── AS13335_policy.txt
│   ├── AS8075_policy.txt
│   └── metadata.json
├── core-router-01/
│   ├── AS174_policy.txt
│   └── metadata.json
└── reports/
    ├── deployment_matrix.yaml
    └── router_statistics.json
```

**Router-Aware Features**:
- Per-router policy directories named by hostname
- BGP group to AS number mappings preserved
- Deployment matrices for operational visibility
- Router interconnection relationship tracking

## Network Protocol Configuration

### SSH Connection Behavior

SSH collection uses strict host key verification with no exceptions in production. The system enforces key-based authentication and implements per-command timeouts. Connection parameters:

- **Authentication**: SSH key-based (preferred) or username/password from environment variables
- **Host Key Verification**: Strict verification against `/var/lib/otto-bgp/ssh-keys/known_hosts`
- **Timeouts**: Configurable connection (default 30s) and command timeouts (default 60s)
- **Parallel Collection**: Configurable worker count (default 5, max determined by `OTTO_BGP_SSH_MAX_WORKERS`)

### NETCONF Over SSH

NETCONF operates as SSH subsystem on port 830:

```bash
# Manual NETCONF connection test
ssh -p 830 otto-bgp@router.example.com -s netconf
```

### Parallel Collection

Otto BGP implements thread-safe parallel collection with resource management:

```python
# Parallel collection with ThreadPoolExecutor
with ThreadPoolExecutor(max_workers=max_workers) as executor:
    future_to_device = {
        executor.submit(self.collect_with_retry, device): device
        for device in devices
    }
```

- **Worker Management**: Default 5 workers, configurable via `OTTO_BGP_SSH_MAX_WORKERS`
- **Retry Logic**: Exponential backoff for transient failures
- **Connection Cleanup**: Automatic resource cleanup with context managers
- **Error Handling**: Per-device error isolation with detailed logging

## RPKI Validation

### RPKI/ROA Validation System (v0.3.2)

Otto BGP implements comprehensive RPKI validation with tri-state logic:

```bash
# RPKI validation command
./otto-bgp rpki-check input.txt --rpki-cache /var/lib/otto-bgp/rpki/
```

#### Validation States

- **VALID**: Prefix matches valid ROA with correct AS number
- **INVALID**: Prefix conflicts with ROA (wrong AS or too specific)
- **NOTFOUND**: No ROA covers this prefix
- **ERROR**: Validation system error (stale data, etc.)

#### VRP Cache Management

```bash
# VRP cache structure
/var/lib/otto-bgp/rpki/
├── vrp_cache.csv          # CSV format VRP data
├── vrp_cache.json         # JSON format (rpki-client/routinator)
└── allowlist.txt          # Exception handling for NOTFOUND prefixes
```

#### Fail-Closed Design

- **Stale VRP Data**: Validation fails if cache is older than configured threshold (default 24 hours)
- **Missing Cache**: System operates without RPKI validation if no cache present
- **Autonomous Mode**: RPKI validation required and enforced
- **System Mode**: RPKI validation optional but recommended

## Safety and Guardrails System (v0.3.2)

### Always-Active Guardrails

Otto BGP implements comprehensive safety mechanisms:

#### Built-in Guardrails

1. **Prefix Count Guardrail**: Prevents excessive prefix changes
   - System mode: 25% maximum change threshold
   - Autonomous mode: 10% maximum change threshold

2. **Bogon Prefix Detection**: Blocks invalid/private prefixes
   - RFC-defined bogon ranges (0.0.0.0/8, 10.0.0.0/8, etc.)
   - Critical risk level - always blocks operation

3. **Concurrent Operation Prevention**: Single operation at a time
   - Lock file management: `/var/lib/otto-bgp/locks/operation.lock`
   - Stale lock detection and cleanup

4. **Signal Handling**: Graceful shutdown capabilities
   - SIGTERM/SIGINT handlers for emergency stops
   - Automatic resource cleanup on termination

#### Mode-Based Safety

**System Mode** (Interactive):
- Guardrails active with warnings
- RPKI validation optional
- Confirmation required for policy application
- Higher risk thresholds allowed

**Autonomous Mode** (Unattended):
- All guardrails strictly enforced
- RPKI validation required
- No confirmation prompts
- Lower risk thresholds
- Enhanced logging and notifications

### Exit Code System

Comprehensive exit codes for automation integration:

- **0**: Success
- **1-99**: General errors
- **100-199**: Configuration errors
- **200-299**: Network/connection errors
- **300-399**: Validation errors (AS numbers, RPKI, syntax)
- **400-499**: Safety/guardrail errors
- **500-599**: Application errors (NETCONF, policy application)

**For system administration procedures, service configuration, and backend troubleshooting, see the System Administrator Guide.**

## Complete Command Reference

Otto BGP provides 9 comprehensive subcommands for complete BGP policy lifecycle management:

### Data Collection Commands

```bash
# Collect BGP peer data from Juniper devices
./otto-bgp collect devices.csv --output-dir ./bgp-data

# Process BGP data and extract AS numbers
./otto-bgp process bgp-data.txt --extract-as -o as-numbers.txt
```

### Policy Generation Commands

```bash
# Generate BGP policies using bgpq4 (combined output)
./otto-bgp policy input.txt -o output.txt

# Generate separate files per AS
./otto-bgp policy input.txt -s --output-dir ./policies

# Test bgpq4 connectivity
./otto-bgp policy --test
```

### Validation Commands

```bash
# RPKI/ROA validation for AS numbers
./otto-bgp rpki-check input.txt --rpki-cache /var/lib/otto-bgp/rpki/
```

### Discovery Commands

```bash
# Discover BGP configurations and generate router mappings
./otto-bgp discover devices.csv --output-dir ./discovery

# List discovered routers, AS numbers, or BGP groups
./otto-bgp list routers --output-dir ./discovery
./otto-bgp list as --output-dir ./discovery  
./otto-bgp list groups --output-dir ./discovery
```

### Policy Application Commands

```bash
# Apply BGP policies to routers via NETCONF (dry run)
./otto-bgp apply --router edge-router-01 --dry-run

# Apply with confirmation
./otto-bgp apply --router edge-router-01 --confirm
```

### Automation Commands

```bash
# Execute complete router-aware pipeline
./otto-bgp pipeline devices.csv --output-dir ./policies

# Skip SSH collection (use existing data)
./otto-bgp pipeline --input-file bgp-data.txt --output-dir ./policies

# Test IRR proxy connectivity
./otto-bgp test-proxy
```

## BGP Policy Application Testing

```bash
# Test policy application in candidate configuration on the router
ssh otto-bgp@router.example.com "
configure private;
load merge /var/tmp/test-policy.txt;
commit check;
show | compare;
rollback;
exit
"
```

## Security Monitoring

### Security Event Categories

Otto BGP logs these security events:

1. **Authentication Failures**: SSH key or username rejection
2. **Host Key Mismatches**: Potential MITM attack indicators  
3. **Permission Violations**: Unauthorized configuration attempts
4. **Command Injection Attempts**: Malformed AS numbers or policy names
5. **Configuration Anomalies**: Unexpected BGP configuration changes

### Network-Focused Security Monitoring

Monitor router-specific security events that impact network operations:

- **BGP Session Changes**: Monitor for unexpected neighbor session state changes
- **Policy Application Failures**: Track failed policy commits or rollbacks
- **Permission Violations**: Router access denied or unauthorized configuration attempts
- **Configuration Anomalies**: Unexpected changes to BGP configurations

**For detailed log analysis procedures and system monitoring setup, see the System Administrator Guide.**

### Audit Trail Maintenance

Maintain comprehensive audit trails:

- **Configuration Changes**: All NETCONF commits logged with timestamps
- **SSH Access**: Connection attempts and session durations
- **Policy Generation**: AS number queries and policy creation events
- **Error Conditions**: Failed operations with detailed error context

## Known Gaps and Limitations

### Technical Dependencies

1. **SSH Host Key Management**:
   - Initial host key collection requires manual setup via scripts
   - No automatic host key rotation handling
   - Setup mode should only be used for initial deployment
2. **Policy Application Scope**:
   - Only manages `policy-options prefix-list` configurations
   - Does not modify routing policies or import/export statements beyond basic import policy references
   - Router-specific advanced BGP features not supported

### Operational Limitations

1. **Guardrail Coverage**:
   - Prefix count changes detected but historical baselines not maintained
   - Bogon detection based on static RFC ranges (not dynamic threat intelligence)
   - No integration with external BGP monitoring systems

### Safety System Limitations

1. **Mode Detection**:
   - Autonomous vs system mode determined by environment variables
   - Configuration changes require application restart

2. **Error Recovery**:
   - Limited automatic recovery from transient network failures
   - NETCONF rollback requires manual confirmation in some scenarios
   - No automatic policy validation against current router state

3. **Memory Usage**:
   - Large policy sets are loaded into memory during generation
   - RPKI VRP validation supports streaming and lazy caching to reduce memory usage
   - Policy generation itself does not stream; memory scales with AS set size

### Performance Considerations

2. **Network Dependencies**:
   - All operations require network connectivity to target devices
   - No offline policy generation mode for network-isolated environments
   - BGP4 queries require Internet connectivity to IRR databases

This reference provides network engineering staff with the technical foundation to understand and work with Otto BGP router configurations, policy generation, and Juniper device integration. For backend system configuration and maintenance procedures, see the System Administrator Guide.

# Network Engineering Reference - Otto BGP v0.3.2

## Overview

Otto BGP collects AS numbers from Juniper router configurations and generates corresponding prefix-list policies using bgpq4. It connects over SSH to collect data and can optionally apply policies via NETCONF.

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
# PyEZ Device parameters (effective subset used by Otto BGP)
device_params = {
    'host': '192.168.1.1',
    'port': 830,
    'user': 'otto-bgp',      # or pass via CLI / environment
    'password': '***',       # or use SSH keys via system SSH configuration
    'gather_facts': True,
    'auto_probe': 30,
}
```

### PyEZ Library Requirements

Otto BGP requires these Python libraries for NETCONF operations:

- junos-eznc: Juniper PyEZ library
- jxmlease: XML handling
- lxml: XML parsing
- ncclient: NETCONF client protocol
- paramiko: SSH protocol implementation

### Configuration Loading

NETCONF configuration operations use merge mode to preserve existing configuration:

```python
# Configuration merge operation (Otto BGP loads text with merge=True)
config_content = """
policy-options {
    prefix-list AS13335 {
        1.1.1.0/24;
        1.0.0.0/24;
    }
}
"""
config.load(config_content, format='text', merge=True)
```

### XML-RPC Command Structure

NETCONF uses XML-RPC for configuration operations:

```xml
<rpc>
    <edit-config>
        <target>
            <candidate/>
        </target>
        <config>
            <configuration>
                <policy-options>
                    <prefix-list replace="replace">
                        <name>13335</name>
                        <prefix-list-item>
                            <name>1.1.1.0/24</name>
                        </prefix-list-item>
                    </prefix-list>
                </policy-options>
            </configuration>
        </config>
    </edit-config>
</rpc>
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
# Execute confirmed commit with timeout
result = config.commit(
    comment="Otto BGP policy update",
    confirm=120  # 120-second confirmation window
)
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

AS numbers must comply with RFC 4893 specifications:

- **Range**: 0 to 4294967295 (32-bit unsigned integer)
- **Reserved Ranges**:
  - 0: Reserved
  - 23456: AS_TRANS
  - 64496-64511: Documentation
  - 64512-65534: Private use
  - 65535: Reserved
  - 65536-65551: Documentation
  - 4200000000-4294967294: Private use
  - 4294967295: Reserved

### Input Sanitization

AS number validation prevents command injection:

```python
def validate_as_number(as_input) -> int:
    # Reject non-integer types
    if isinstance(as_input, float):
        raise ValueError("AS number must be integer")
    
    # Convert to integer
    as_number = int(as_input)
    
    # Validate range
    if not 0 <= as_number <= 4294967295:
        raise ValueError("AS number out of RFC 4893 range")
    
    return as_number
```

### bgpq4 Command Generation

Validated AS numbers generate safe bgpq4 commands:

```bash
# Generated command for AS 13335
bgpq4 -Jl AS13335 AS13335

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

Otto BGP executes bgpq4 with specific parameters:

```bash
bgpq4 -Jl <policy_name> AS<as_number>
```

Parameter explanation:
- `-J`: Generate Juniper syntax
- `-l <name>`: Set prefix-list name
- `AS<number>`: Query specific AS number

### Policy Name Sanitization

Policy names undergo sanitization for shell safety:

```python
def sanitize_policy_name(name: str) -> str:
    # Allow only alphanumeric, underscore, hyphen
    if not re.match(r'^[A-Za-z0-9_-]+$', name):
        raise ValueError("Invalid policy name characters")
    
    # Enforce length limit
    if len(name) > 64:
        raise ValueError("Policy name too long")
    
    return name
```

### Policy Output Directory

Router-specific policies are stored under the policy root directory:

```
policies/
└── routers/
    ├── edge-router1/
    │   ├── AS13335_policy.txt
    │   ├── AS8075_policy.txt
    │   └── metadata.json
    └── core-router1/
        ├── AS174_policy.txt
        └── metadata.json
```

## Network Protocol Configuration

### SSH Connection Behavior

SSH collection uses strict host key verification and per-command timeouts. Credentials can be key-based or password-based, as configured by system administrators.

### NETCONF Over SSH

NETCONF operates as SSH subsystem on port 830:

```bash
# Manual NETCONF connection test
ssh -p 830 otto-bgp@router.example.com -s netconf
```

### Parallel Collection

Otto BGP collects from multiple devices in parallel when applicable. The maximum workers are configurable via environment; connection and command timeouts are enforced per device.

**For system administration procedures, service configuration, and backend troubleshooting, see the System Administrator Guide.**

## BGP Policy Validation

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

This reference provides network engineering staff with the technical foundation to understand and work with Otto BGP router configurations, policy generation, and Juniper device integration. For backend system configuration and maintenance procedures, see the System Administrator Guide.

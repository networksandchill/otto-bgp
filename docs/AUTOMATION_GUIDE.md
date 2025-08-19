# Otto BGP Automation Guide

## Table of Contents
1. [Introduction](#introduction)
2. [Quick Start](#quick-start)
3. [Automation Workflows](#automation-workflows)
4. [CLI Commands](#cli-commands)
5. [Configuration](#configuration)
6. [Integration](#integration)
7. [Best Practices](#best-practices)
8. [Troubleshooting](#troubleshooting)

## Introduction

Otto BGP v0.3.2 provides comprehensive automation capabilities for BGP policy management across Juniper router fleets, including autonomous operation with risk-based decision logic. This guide covers automation workflows, integration patterns, and best practices.

## Operational Modes

Otto BGP operates in three distinct modes to serve different operational needs:

### SystemD Service (Production Policy Generation)
- **Purpose**: Headless, unattended policy generation for production environments
- **Execution**: Scheduled runs via systemd timer (default: hourly at :15 minutes)
- **Operation**: Autonomous policy generation - connects to devices, processes data, generates policies
- **Scope**: Policy generation with optional autonomous application based on configuration
- **Use Case**: Continuous policy generation and application without operator intervention
- **Benefits**: Consistent scheduling, automatic error handling, production logging, email notifications

### CLI Tool (Interactive Operations)  
- **Purpose**: On-demand execution for testing, debugging, and ad-hoc tasks
- **Execution**: Manual operator-initiated commands
- **Operation**: Flexible command structure (`collect`, `process`, `policy`, `apply`)
- **Scope**: Full policy generation and application capabilities with safety controls
- **Use Case**: Testing connectivity, generating specific policies, troubleshooting, autonomous operation
- **Benefits**: Immediate feedback, custom parameters, development workflows, autonomous mode support

### Autonomous Mode (Full Automation)
- **Purpose**: Complete automation including policy application for production environments
- **Execution**: CLI commands with `--autonomous` flag or systemd with autonomous configuration
- **Operation**: Full pipeline including NETCONF policy application with risk-based decisions
- **Scope**: **Production-ready** with comprehensive safety controls and email notifications
- **Use Case**: Hands-off BGP policy management, automated network optimization
- **Benefits**: End-to-end automation, email audit trail, risk-based safety, immediate notifications

**Example Usage:**
```bash
# SystemD (automated) - runs automatically every hour
sudo systemctl start otto-bgp.service

# CLI (interactive) - operator runs specific tasks  
./otto-bgp policy AS13335 --test
./otto-bgp collect devices.csv --verbose

# Autonomous mode - automatic policy application
./otto-bgp apply --autonomous --auto-threshold 100
./otto-bgp pipeline devices.csv --autonomous --system
```

## Quick Start

### Basic Automation Pipeline

```bash
# 1. Discover routers and their BGP configurations
./otto-bgp discover devices.csv --output-dir policies

# 2. Generate policies for discovered AS numbers
./otto-bgp policy sample_input.txt --output-dir policies/routers

# 3. Apply policies with autonomous mode (production-ready)
./otto-bgp apply --autonomous --auto-threshold 100

# 4. Traditional manual application with confirmation
./otto-bgp apply --router router1 --policy-dir policies --dry-run

# 5. Full pipeline automation with autonomous operation
./otto-bgp pipeline devices.csv --autonomous --system --output-dir bgp_output
```

## Automation Workflows

### 1. Discovery Workflow

Automatically discover BGP configurations across your router fleet:

```bash
# Basic discovery
./otto-bgp discover devices.csv

# With change detection
./otto-bgp discover devices.csv --show-diff

# List discovered resources
./otto-bgp list routers --output-dir policies
./otto-bgp list as --output-dir policies
./otto-bgp list groups --output-dir policies
```

#### Device CSV Format
```csv
hostname,address,username,model,location
edge-router1,10.1.1.1,admin,MX960,datacenter1
core-router1,10.1.2.1,admin,MX480,datacenter1
transit-router1,10.1.3.1,admin,MX240,datacenter2
```

### 2. Policy Generation Workflow

#### Automated Policy Generation

Otto BGP includes **RPKI validation by default** during policy generation to enhance security and policy accuracy.

```bash
# Generate policies with RPKI validation (default behavior)
./otto-bgp policy discovered_as.txt --separate

# Generate with custom output directory (RPKI validation included)
./otto-bgp policy as_list.txt --output-dir policies/routers/router1

# Test BGPq4 connectivity first
./otto-bgp policy as_list.txt --test --test-as 13335

# Disable RPKI validation if needed (not recommended)
./otto-bgp policy as_list.txt --no-rpki --separate
```

**RPKI Validation Features:**
- **Default Behavior**: RPKI validation runs automatically during policy generation
- **Status Comments**: Generated policies include RPKI validation status as comments
- **Opt-out Available**: Use `--no-rpki` flag to disable validation when necessary
- **Security Enhancement**: Helps identify potentially invalid or hijacked routes

#### Router-Specific Generation
```python
#!/usr/bin/env python3
from otto_bgp.generators.bgpq4_wrapper import BGPq4Wrapper
from otto_bgp.discovery import YAMLGenerator

# Load router mappings
yaml_gen = YAMLGenerator()
mappings = yaml_gen.load_previous_mappings()

# Generate for specific router
router_as = mappings['routers']['edge-router1']['discovered_as_numbers']
wrapper = BGPq4Wrapper()
results = wrapper.generate_policies_batch(router_as)
```

### 3. Policy Application Workflow

#### Safe Application Process
```bash
# 1. Dry run to preview changes
./otto-bgp apply --router lab-router1 --dry-run

# 2. Apply with confirmation (automatic rollback)
./otto-bgp apply --router lab-router1 --confirm --confirm-timeout 120

# 3. Monitor BGP sessions and let auto-rollback handle confirmation timeout
```

#### Batch Application Script
```bash
#!/bin/bash
# apply_to_lab.sh - Apply policies to lab routers

ROUTERS="lab-router1 lab-router2 lab-router3"
POLICY_DIR="policies"

for router in $ROUTERS; do
    echo "Applying policies to $router..."
    
    # Dry run first
    ./otto-bgp apply --router $router --policy-dir $POLICY_DIR --dry-run
    
    # If successful, apply with confirmation
    if [ $? -eq 0 ]; then
        ./otto-bgp apply --router $router --policy-dir $POLICY_DIR \
            --confirm --confirm-timeout 300 --yes
    else
        echo "Dry run failed for $router, skipping..."
    fi
done
```

### 4. Autonomous Operation Workflow

Otto BGP v0.3.2 supports production-ready autonomous operation with comprehensive safety controls, RPKI validation, and email notifications.

#### Setup Autonomous Mode
```bash
# Install with autonomous mode
./install.sh --autonomous

# Configure email notifications during setup:
# - SMTP server and port
# - TLS encryption settings
# - From and to email addresses
# - Subject prefix for notifications
```

#### Autonomous Operation Commands

**Note**: RPKI validation is enabled by default in autonomous mode for enhanced security.

```bash
# Standard autonomous operation (includes RPKI validation)
./otto-bgp apply --autonomous --auto-threshold 100

# System-wide autonomous operation with RPKI validation
./otto-bgp apply --system --autonomous

# Pipeline with autonomous application and RPKI validation
./otto-bgp pipeline devices.csv --autonomous --system

# Preview autonomous decisions (including RPKI status)
./otto-bgp apply --autonomous --dry-run

# Disable RPKI validation in autonomous mode (not recommended)
./otto-bgp apply --autonomous --no-rpki --auto-threshold 100
```

#### Monitoring Autonomous Operations
```bash
# Monitor systemd service for autonomous operations
sudo journalctl -u otto-bgp.service -f | grep -i "autonomous\|netconf\|commit"

# Check autonomous decision logs
cat /var/lib/otto-bgp/logs/otto-bgp.log | grep -i "risk\|threshold\|autonomous"

# Review email notifications for complete audit trail
```

#### Autonomous Configuration Example
```json
{
  "autonomous_mode": {
    "enabled": true,
    "auto_apply_threshold": 100,
    "require_confirmation": true,
    "safety_overrides": {
      "max_session_loss_percent": 5.0,
      "max_route_loss_percent": 10.0,
      "monitoring_duration_seconds": 300
    },
    "notifications": {
      "email": {
        "enabled": true,
        "smtp_server": "smtp.company.com",
        "smtp_port": 587,
        "smtp_use_tls": true,
        "from_address": "otto-bgp@company.com",
        "to_addresses": ["network-team@company.com"],
        "subject_prefix": "[Otto BGP Autonomous]",
        "send_on_success": true,
        "send_on_failure": true
      }
    }
  }
}
```

### 5. IRR Proxy Workflow

For restricted networks where direct IRR access is blocked:

#### Configure Proxy
```bash
# Set environment variables
export OTTO_BGP_PROXY_ENABLED=true
export OTTO_BGP_PROXY_JUMP_HOST=gateway.example.com
export OTTO_BGP_PROXY_JUMP_USER=admin
export OTTO_BGP_PROXY_SSH_KEY=/path/to/key

# Test proxy connectivity
./otto-bgp test-proxy --test-bgpq4

# Generate policies through proxy
./otto-bgp policy as_list.txt --output-dir policies
```

#### Proxy Configuration File
```json
{
  "irr_proxy": {
    "enabled": true,
    "method": "ssh_tunnel",
    "jump_host": "gateway.example.com",
    "jump_user": "admin",
    "ssh_key_file": "/home/user/.ssh/id_rsa",
    "tunnels": [
      {
        "name": "ntt",
        "local_port": 43001,
        "remote_host": "rr.ntt.net",
        "remote_port": 43
      },
      {
        "name": "radb",
        "local_port": 43002,
        "remote_host": "whois.radb.net",
        "remote_port": 43
      }
    ]
  }
}
```

## CLI Commands

### Core Commands

| Command | Description | Example |
|---------|-------------|---------|
| `discover` | Discover BGP configurations | `./otto-bgp discover devices.csv` |
| `policy` | Generate BGP policies | `./otto-bgp policy as_list.txt -s` |
| `apply` | Apply policies via NETCONF | `./otto-bgp apply --autonomous --auto-threshold 100` |
| `pipeline` | Run complete workflow | `./otto-bgp pipeline devices.csv` |
| `list` | List discovered resources | `./otto-bgp list routers` |
| `test-proxy` | Test IRR proxy setup | `./otto-bgp test-proxy --test-bgpq4` |

### Command Options

#### Global Options
- `--verbose, -v`: Enable debug logging
- `--quiet, -q`: Suppress info messages
- `--dev`: Use containerized bgpq4

#### Discovery Options
- `--output-dir`: Directory for results
- `--show-diff`: Generate change report
- `--timeout`: SSH connection timeout

#### Policy Options
- `--separate, -s`: One file per AS
- `--output-dir`: Policy output directory
- `--test`: Test bgpq4 connectivity

#### Apply Options
- `--autonomous`: Enable autonomous mode with risk-based decisions
- `--system`: Use system-wide configuration and resources
- `--auto-threshold N`: Reference prefix count for notification context (informational only)
- `--dry-run`: Preview without applying
- `--confirm`: Use confirmed commit
- `--force`: Override safety checks
- `--yes, -y`: Skip confirmation prompt
- `--router HOSTNAME`: Target specific router

## Configuration

### Environment Variables

```bash
# SSH Configuration
export OTTO_BGP_SSH_USERNAME=admin
export OTTO_BGP_SSH_PASSWORD=secret
export OTTO_BGP_SSH_KEY_FILE=/path/to/key

# BGPq4 Configuration
export OTTO_BGP_BGPQ4_PATH=/usr/local/bin/bgpq4
export OTTO_BGP_BGPQ4_TIMEOUT=45

# Proxy Configuration
export OTTO_BGP_PROXY_ENABLED=true
export OTTO_BGP_PROXY_JUMP_HOST=gateway.example.com
export OTTO_BGP_PROXY_JUMP_USER=admin

# Directory Configuration
export OTTO_BGP_OUTPUT_DIR=/var/lib/otto-bgp
export OTTO_BGP_CACHE_DIR=/var/cache/otto-bgp
```

### Configuration File

Create `~/.otto-bgp/config.json`:

```json
{
  "ssh": {
    "username": "admin",
    "connection_timeout": 30,
    "command_timeout": 60
  },
  "bgpq4": {
    "mode": "auto",
    "timeout": 45,
    "docker_image": "ghcr.io/bgp/bgpq4:latest"
  },
  "output": {
    "default_dir": "/var/lib/otto-bgp",
    "separate_files": true,
    "compress_old": true
  }
}
```

## Production Workflow

This section shows the **actual workflow** used by production deployments today. Otto BGP provides policy generation automation while maintaining safety through manual review and application processes.

### Typical Production Deployment

**Step 1: Automated Policy Generation**
```bash
# Option A: SystemD service (recommended for production)
sudo systemctl enable otto-bgp.timer
sudo systemctl start otto-bgp.timer
# Policies generated hourly to /var/lib/otto-bgp/policies/

# Option B: Manual pipeline execution
./otto-bgp pipeline devices.csv --output-dir ./policies/$(date +%Y%m%d)
```

**Step 2: Policy Review and Validation**
```bash
# Review generated policies
ls -la ./policies/$(date +%Y%m%d)/
diff ./policies/$(date +%Y%m%d)/ ./policies/previous/ | head -20

# Generate change summary for approval process
./otto-bgp compare --old ./policies/previous/ --new ./policies/$(date +%Y%m%d)/ \
    --output change-summary.txt
```

**Step 3: Lab Testing (Optional but Recommended)**
```bash
# Test policies in lab environment using NETCONF
./otto-bgp apply --router lab-router1 --policy-dir ./policies/$(date +%Y%m%d)/ --dry-run
./otto-bgp apply --router lab-router1 --policy-dir ./policies/$(date +%Y%m%d)/ --confirm
```

**Step 4: Change Management Integration**
```bash
# Create change request in your CM system
# Include generated policies and lab test results
# Attach change-summary.txt and any test outputs
# Schedule application during maintenance window
```

**Step 5: Manual Policy Application**
```bash
# During maintenance window, apply policies manually:
# 1. Load generated policies to router configuration candidate
# 2. Review configuration diff
# 3. Commit with confirmation timeout
# 4. Monitor BGP sessions and routing tables
# 5. Confirm commit or let timeout trigger rollback
```

## Enhanced Policy Automation

### Production-Ready Policy Application

**Otto BGP v0.3.2 provides multiple policy application approaches:**

**Autonomous Mode (Production-Ready):**
- **Risk-Based Decisions**: Only low-risk changes are automatically applied
- **Email Notifications**: Complete audit trail for all NETCONF operations
- **Safety Validation**: Comprehensive pre-application checks and confirmation timeouts
- **Manual Fallback**: High-risk changes require manual approval

**Manual Mode (Traditional):**
- Generate policies with Otto BGP: `./otto-bgp policy as-numbers.txt -o policies.txt`
- Review generated policies manually or with automation tools
- Test in development environment first
- Apply using existing change management procedures

### Automated Policy Application

**Prerequisites for Autonomous Operation:**
```bash
# Install PyEZ dependencies
pip install junos-eznc jxmlease lxml ncclient

# Configure Otto BGP for autonomous mode
./install.sh --autonomous  # Includes email configuration setup

# Verify configuration
./otto-bgp config show
```

**Autonomous Mode Commands:**
```bash
# Autonomous policy application (production-ready)
./otto-bgp apply --autonomous --auto-threshold 100

# System mode with autonomous decisions
./otto-bgp apply --system --autonomous

# Dry run to preview autonomous decisions
./otto-bgp apply --autonomous --dry-run

# Traditional manual confirmation
./otto-bgp apply --router router1 --confirm --confirm-timeout 120
```

### IRR Proxy Support

For networks with restricted IRR access:

```bash
# Configure proxy
export OTTO_BGP_PROXY_ENABLED=true
export OTTO_BGP_PROXY_JUMP_HOST=gateway.example.com
export OTTO_BGP_PROXY_JUMP_USER=admin

# Test proxy connectivity
./otto-bgp test-proxy --test-bgpq4

# Generate policies through proxy
./otto-bgp policy as_list.txt
```

### Complete Automation Workflow
```bash
# 1. Discover network
./otto-bgp discover devices.csv

# 2. Generate router-specific policies  
./otto-bgp policy discovered_as.txt --output-dir policies/routers

# 3. Autonomous mode - complete automation
./otto-bgp pipeline devices.csv --autonomous --auto-threshold 100

# 4. Monitor autonomous operations via email notifications and logs
journalctl -u otto-bgp.service -f

# Or run complete pipeline
./otto-bgp pipeline devices.csv --output-dir policies
```

## Minimal Lab Setup

For testing against real lab routers with production-like configuration:

- ✅ **Lab System**: Install prerequisites on dedicated lab server (Python 3.9+, bgpq4, SSH client)
- ✅ **Otto Deployment**: Clone and configure using installation and user setup steps
- ✅ **Lab SSH Keys**: Generate production-style keypair via SSH key configuration
- ✅ **Router Config**: Deploy SSH user and keys on lab routers using Juniper SSH user setup
- ✅ **Device Inventory**: Create `devices.csv` with lab router IPs following device inventory setup
- ✅ **Security Setup**: Collect lab router host keys via SSH host key verification
- ✅ **Production Config**: Mirror production settings with configuration setup 
- ✅ **Lab Pipeline**: Test full workflow with real BGP data using pipeline command

**Lab Validation**: `./otto-bgp pipeline lab-devices.csv --output-dir ./lab-results` against live routers.

## Monitoring

### SystemD Integration
```bash
# Service status
sudo systemctl status otto-bgp.service

# Recent executions
sudo systemctl list-timers otto-bgp.timer

# Service logs
sudo journalctl -u otto-bgp.service --since "1 hour ago"

# Follow live logs
sudo journalctl -u otto-bgp.service -f
```

### Log Analysis
```bash
# View execution summary
sudo grep "Pipeline execution complete" /var/lib/otto-bgp/logs/otto-bgp.log | tail -5

# Check for errors
sudo grep "ERROR" /var/lib/otto-bgp/logs/otto-bgp.log | tail -10

# Monitor performance
sudo grep "took.*s" /var/lib/otto-bgp/logs/otto-bgp.log | tail -10
```

### Health Monitoring Script
```bash
# Create monitoring script
sudo tee /usr/local/bin/otto-bgp-health << 'EOF'
#!/bin/bash
# Otto BGP Health Check

LOG_FILE="/var/lib/otto-bgp/logs/otto-bgp.log"
LAST_RUN=$(sudo systemctl show otto-bgp.service -p ActiveEnterTimestamp --value)
OUTPUT_DIR="/var/lib/otto-bgp/output"

echo "Otto BGP Health Status"
echo "========================="
echo "Last execution: $LAST_RUN"
echo "Service status: $(sudo systemctl is-active otto-bgp.service)"
echo "Timer status: $(sudo systemctl is-active otto-bgp.timer)"
echo "Output files: $(find $OUTPUT_DIR -name "*.txt" -mtime -1 | wc -l) (last 24h)"

# Recent errors
ERROR_COUNT=$(sudo grep -c "ERROR" $LOG_FILE)
if [ $ERROR_COUNT -gt 0 ]; then
    echo "Recent errors: $ERROR_COUNT"
    echo "Latest error:"
    sudo grep "ERROR" $LOG_FILE | tail -1
fi
EOF

sudo chmod +x /usr/local/bin/otto-bgp-health
```

### Alerting Integration
```bash
# Example: Send email alerts on failures
sudo tee /etc/systemd/system/otto-bgp-failure@.service << 'EOF'
[Unit]
Description=Otto BGP Failure Notification
After=otto-bgp.service

[Service]
Type=oneshot
ExecStart=/usr/bin/mail -s "Otto BGP Failed on %H" admin@company.com < /var/log/otto-bgp-error.log
EOF

# Add to main service
# OnFailure=otto-bgp-failure@%i.service
```

## Integration

### Systemd Integration

Enable automated policy updates:

```bash
# Install service files
sudo cp systemd/otto-bgp.service /etc/systemd/system/
sudo cp systemd/otto-bgp.timer /etc/systemd/system/

# Enable and start
sudo systemctl enable otto-bgp.timer
sudo systemctl start otto-bgp.timer

# Check status
sudo systemctl status otto-bgp.service
```

### Cron Integration

```cron
# Update BGP policies daily at 2 AM
0 2 * * * /opt/otto-bgp/venv/bin/python /opt/otto-bgp/otto_bgp/main.py pipeline /etc/otto-bgp/devices.csv --output-dir /var/lib/otto-bgp/policies

# Discovery only - every 6 hours
0 */6 * * * /opt/otto-bgp/venv/bin/python /opt/otto-bgp/otto_bgp/main.py discover /etc/otto-bgp/devices.csv --show-diff
```

### CI/CD Integration

#### GitLab CI Example
```yaml
stages:
  - discover
  - generate
  - validate

discover-routers:
  stage: discover
  script:
    - ./otto-bgp discover devices.csv --output-dir artifacts/
  artifacts:
    paths:
      - artifacts/discovered/

generate-policies:
  stage: generate
  dependencies:
    - discover-routers
  script:
    - ./otto-bgp policy artifacts/discovered/as_numbers.txt -s
  artifacts:
    paths:
      - policies/

validate-policies:
  stage: validate
  dependencies:
    - generate-policies
  script:
    - ./otto-bgp apply --router lab-router --dry-run --policy-dir policies/
```

#### Jenkins Pipeline
```groovy
pipeline {
    agent any
    
    stages {
        stage('Discovery') {
            steps {
                sh './otto-bgp discover devices.csv'
            }
        }
        
        stage('Generation') {
            steps {
                sh './otto-bgp policy discovered_as.txt --separate'
            }
        }
        
        stage('Validation') {
            steps {
                sh './otto-bgp apply --router ${ROUTER} --dry-run'
            }
        }
        
        stage('Deploy') {
            when {
                branch 'main'
            }
            steps {
                sh './otto-bgp apply --router ${ROUTER} --confirm'
            }
        }
    }
}
```

### Python Integration

```python
#!/usr/bin/env python3
"""
Example: Automated BGP policy management
"""

from otto_bgp.collectors import JuniperSSHCollector
from otto_bgp.discovery import RouterInspector, YAMLGenerator
from otto_bgp.generators import BGPq4Wrapper
from otto_bgp.appliers import JuniperPolicyApplier
from pathlib import Path

def automated_bgp_update(devices_csv: str, output_dir: str):
    """Complete automated BGP policy update"""
    
    # Initialize components
    collector = JuniperSSHCollector()
    inspector = RouterInspector()
    yaml_gen = YAMLGenerator(output_dir=Path(output_dir))
    bgpq4 = BGPq4Wrapper()
    applier = JuniperPolicyApplier()
    
    # Phase 1: Discovery
    print("Phase 1: Discovering routers...")
    devices = collector.load_devices_from_csv(devices_csv)
    profiles = []
    
    for device in devices:
        try:
            bgp_config = collector.collect_bgp_config(device.address)
            profile = device.to_router_profile()
            profile.bgp_config = bgp_config
            profiles.append(profile)
        except Exception as e:
            print(f"Failed to discover {device.hostname}: {e}")
    
    # Phase 2: Generate mappings
    print("Phase 2: Generating mappings...")
    mappings = yaml_gen.generate_mappings(profiles)
    yaml_gen.save_with_history(mappings)
    
    # Phase 3: Generate policies
    print("Phase 3: Generating policies...")
    for hostname, data in mappings['routers'].items():
        as_numbers = data['discovered_as_numbers']
        if as_numbers:
            results = bgpq4.generate_policies_batch(as_numbers)
            bgpq4.write_policies_to_files(
                results,
                output_dir=f"{output_dir}/routers/{hostname}",
                separate_files=True
            )
    
    # Phase 4: Apply policies (with safety checks)
    print("Phase 4: Applying policies...")
    for hostname in mappings['routers'].keys():
        policy_dir = Path(f"{output_dir}/routers/{hostname}")
        if policy_dir.exists():
            policies = applier.load_router_policies(policy_dir)
            
            # Preview changes
            diff = applier.preview_changes(policies)
            print(f"Changes for {hostname}:\n{diff}")
            
            # Apply with confirmation
            result = applier.apply_with_confirmation(
                policies=policies,
                confirm_timeout=120,
                comment=f"Automated update for {hostname}"
            )
            
            if result.success:
                print(f"Successfully updated {hostname}")
            else:
                print(f"Failed to update {hostname}: {result.error_message}")

if __name__ == "__main__":
    automated_bgp_update("devices.csv", "policies")
```

## Best Practices

### 1. Safety First
- Always run dry-run before applying changes
- Use confirmed commits with appropriate timeouts
- Implement gradual rollout (lab → staging → production)
- Maintain rollback procedures

### 2. Discovery Practices
- Run discovery regularly to detect changes
- Review diff reports before policy updates
- Maintain historical mappings for audit
- Validate discovered AS numbers

### 3. Generation Practices
- Separate policies by router
- Cache generated policies
- Validate policy syntax
- Test with known AS numbers

### 4. Application Practices
- Apply during maintenance windows
- Monitor BGP sessions during updates
- Use confirmation timeouts
- Document all changes

### 5. Monitoring
- Track discovery changes over time
- Monitor policy generation failures
- Alert on application errors
- Maintain audit logs

## Troubleshooting

### Common Issues

#### 1. Discovery Failures
```bash
# Check SSH connectivity
ssh admin@router1 "show version"

# Verify credentials
./otto-bgp discover devices.csv --verbose

# Test with single device
echo "router1,10.1.1.1" > test.csv
./otto-bgp discover test.csv --verbose
```

#### 2. Policy Generation Failures
```bash
# Test bgpq4 directly
bgpq4 -Jl test AS13335

# Check with container
docker run --rm ghcr.io/bgp/bgpq4:latest bgpq4 -Jl test AS13335

# Test through Otto
./otto-bgp policy test_as.txt --test --verbose
```

#### 3. Application Failures
```bash
# Check NETCONF connectivity
ssh admin@router1 -p 830 -s netconf

# Verify PyEZ installation
python3 -c "from jnpr.junos import Device; print('PyEZ OK')"

# Test with dry-run
./otto-bgp apply --router router1 --dry-run --verbose
```

#### 4. Proxy Issues
```bash
# Test SSH tunnel manually
ssh -L 43001:rr.ntt.net:43 admin@gateway.example.com

# Verify proxy configuration
./otto-bgp test-proxy --verbose

# Test bgpq4 through proxy
./otto-bgp test-proxy --test-bgpq4 --verbose
```

### Debug Mode

Enable comprehensive debugging:

```bash
# Set debug environment
export OTTO_BGP_DEBUG=true
export OTTO_BGP_LOG_LEVEL=DEBUG

# Run with verbose output
./otto-bgp discover devices.csv -v

# Check logs
tail -f /var/log/otto-bgp/debug.log
```

### Log Locations

- Application logs: `/var/log/otto-bgp/`
- Discovery results: `policies/discovered/`
- Generation logs: `policies/routers/*/metadata.json`
- Application logs: `policies/reports/`

## Advanced Topics

### Custom Workflows

Create custom automation workflows:

```python
from otto_bgp.pipeline import CustomPipeline

class MyBGPWorkflow(CustomPipeline):
    def pre_discovery_hook(self):
        """Custom pre-discovery logic"""
        pass
    
    def post_generation_hook(self, policies):
        """Custom post-generation validation"""
        pass
    
    def pre_application_hook(self, router, policies):
        """Custom pre-application checks"""
        pass
```

### Performance Tuning

```python
# Parallel discovery
wrapper = BGPq4Wrapper(
    max_workers=8,  # Parallel threads
    cache_ttl=3600,  # Cache for 1 hour
    batch_size=50    # Process in batches
)

# Connection pooling
collector = JuniperSSHCollector(
    pool_size=10,
    reuse_connections=True
)
```

### Integration APIs

Future REST API endpoints (planned):

```
GET  /api/v1/routers              # List routers
GET  /api/v1/routers/{id}         # Router details
POST /api/v1/discover             # Trigger discovery
POST /api/v1/generate             # Generate policies
POST /api/v1/apply                # Apply policies
GET  /api/v1/status               # System status
```
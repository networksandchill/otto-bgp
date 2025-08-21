# Otto BGP CLI Reference

## Overview

Otto BGP v0.3.2 provides a comprehensive command-line interface for autonomous BGP policy management. The CLI supports three-tier operation modes (user, system, autonomous) with extensive configuration options and safety controls.

**Design Philosophy**: Simple commands with powerful autonomous capabilities and comprehensive safety controls

## Command Structure

```bash
otto-bgp [global_flags] <command> [command_options] [arguments]
otto-bgp <command> [global_flags] [command_options] [arguments]
```

Global flags can be positioned either before or after the subcommand.

### Core Commands

| Command | Purpose | Autonomous Support |
|---------|---------|-------------------|
| `discover` | Collect BGP configurations from routers | Temporarily disabled |
| `policy` | Generate BGP prefix-list policies | ✅ |
| `apply` | Apply policies to routers via NETCONF | ✅ |
| `pipeline` | Run complete workflow (discover → generate → apply) | ✅ |
| `list` | List discovered resources | ❌ |
| `test-proxy` | Test IRR proxy connectivity | ❌ |

## Global Flags

### Operation Mode Flags (v0.3.2)

```bash
--autonomous              # Enable autonomous mode with automatic policy application
--system                  # Use system-wide configuration and resources
--auto-threshold N        # Reference prefix count for notification context (default: 100)
```

**Flag Relationships:**
- `--autonomous` requires autonomous mode to be enabled in configuration
- `--auto-threshold` is informational only - never blocks operations

### Deprecated Flags

```bash
--production             # DEPRECATED: Use --system instead (shows warning)
```

### General Flags

```bash
--verbose, -v            # Enable debug logging (conflicts with --quiet)
--quiet, -q             # Suppress info messages (conflicts with --verbose)
--help, -h              # Show help message
--version               # Show version information
--dev                   # Use containerized bgpq4 for development
```

## Command Reference

### 1. discover - Router Discovery

Collect BGP configurations from Juniper routers via SSH.

```bash
otto-bgp discover <devices.csv> [options]
```

#### Arguments
- `devices.csv` - CSV file with router information (required)

> Note: The `discover` command is temporarily disabled in this version while error handling is standardized. Running it exits with an error message. Supported parser options are present but the command does not execute discovery at this time.

#### Examples
No-op while disabled.

#### CSV Format
```csv
hostname,address,username,model,location
edge-router1,10.1.1.1,admin,MX960,datacenter1
core-router1,10.1.2.1,admin,MX480,datacenter1
transit-router1,10.1.3.1,admin,MX240,datacenter2
```

### 2. policy - Policy Generation

Generate BGP prefix-list policies using bgpq4 and IRR data with RPKI validation enabled by default.

```bash
otto-bgp policy <input_file> [options]
```

#### Arguments
- `input_file` - File containing AS numbers (required)

#### Options
```bash
-o FILE, --output FILE   # Combined output filename (default: bgpq4_output.txt)
-s, --separate           # Create separate file per AS
--output-dir DIR         # Output directory (default: policies)
--timeout SECONDS        # bgpq4 timeout per query (default: 30)
--test                   # Test bgpq4 connectivity and exit
--test-as AS_NUMBER      # AS number for connectivity test (default: 7922)
--no-rpki                # Disable RPKI validation during policy generation (not recommended)
```

#### Autonomous Mode Options
```bash
--autonomous               # Enable autonomous mode for generation
--system                  # Use system-wide configuration
--auto-threshold N        # Reference threshold for notifications (default: 100)
```

#### Examples
```bash
# Basic policy generation
otto-bgp policy as_numbers.txt -o policies/

# Separate files per AS (global flags work in both positions)
otto-bgp policy discovered_as.txt --separate
otto-bgp --separate policy discovered_as.txt

# Autonomous generation with threshold context
otto-bgp policy as_list.txt --autonomous --auto-threshold 150
otto-bgp --autonomous --auto-threshold 150 policy as_list.txt

# Test connectivity before generation
otto-bgp policy as_list.txt --test --test-as 13335

# Disable RPKI validation (not recommended)
otto-bgp policy as_list.txt --no-rpki

# RPKI validation enabled by default (shows RPKI status in output comments)
otto-bgp policy as_list.txt --separate  # Will include RPKI validation status
```

#### Input File Format
```text
# AS numbers in various formats
AS13335
15169
7922
AS8075
```

### 3. apply - Policy Application

Apply BGP policies to routers via NETCONF with safety controls.

```bash
otto-bgp apply [options]
```

#### Options
```bash
--router HOSTNAME         # Apply to specific router (required)
--policy-dir DIR          # Root policy directory (default: policies)
--dry-run                 # Preview changes without applying
--confirm                 # Use confirmed commits
--confirm-timeout SECONDS # Confirmation timeout (default: 120)
--diff-format FORMAT      # Diff format: text, set, xml (default: text)
--skip-safety             # Skip safety validation (not recommended)
--force                   # Force application despite high risk
--yes, -y                 # Skip confirmation prompts
--username USERNAME       # NETCONF username (or NETCONF_USERNAME env var)
--password PASSWORD       # NETCONF password (or NETCONF_PASSWORD env var)
--ssh-key PATH            # SSH private key (or NETCONF_SSH_KEY env var)
--port PORT               # NETCONF port (default: 830 or NETCONF_PORT env var)
--timeout SECONDS         # Connection timeout (default: 30)
--comment TEXT            # Commit comment
```

#### Autonomous Mode Options (v0.3.2)
```bash
--autonomous               # Enable autonomous mode with risk-based decisions
--system                  # Use system-wide configuration
--auto-threshold N        # Reference prefix count for notification context
```

#### Examples

**Basic Manual Application:**
```bash
# Dry run to preview changes
otto-bgp apply --router lab-router1 --dry-run

# Apply with confirmation window
otto-bgp apply --router lab-router1 --confirm --confirm-timeout 300

# Apply to specific router with custom policy root (code appends routers/<router>)
otto-bgp apply --router edge-router1 --policy-dir /var/lib/otto-bgp/policies
```

**Autonomous Application:**
```bash
# Standard autonomous application
otto-bgp apply --autonomous --auto-threshold 100

# System-wide autonomous application
otto-bgp apply --system --autonomous

# Autonomous with custom threshold (informational only)
otto-bgp apply --autonomous --auto-threshold 200 --policy-dir /var/lib/otto-bgp/policies
```

**Advanced Usage:**
```bash
# Force application (override safety checks)
otto-bgp apply --router router1 --force --yes

# Apply with extended confirmation window
otto-bgp apply --router router1 --confirm --confirm-timeout 600
```

#### Safety Behavior

**Manual Mode:**
- Dry-run validation required
- Confirmed commits with rollback capability
- Manual approval for all changes

**Autonomous Mode:**
- Risk-based decisions (only low-risk auto-applied)
- Email notifications when autonomous email notifications are enabled in configuration
- Threshold informational only (never blocks)
- Automatic fallback to manual approval for high-risk changes

### 4. pipeline - Complete Workflow

Execute the complete Otto BGP workflow: discover → generate → apply.

```bash
otto-bgp pipeline <devices.csv> [options]
```

#### Arguments
- `devices.csv` - CSV file with router information (required)

#### Options
```bash
--output-dir DIR           # Output directory for all pipeline results (default: bgp_pipeline_output)
--mode MODE               # Execution mode: system, autonomous (default: system)
--timeout SECONDS         # Command timeout in seconds (default: 30)
--command-timeout SECONDS # SSH command timeout in seconds (default: 60)
--no-rpki                 # Disable RPKI validation during policy generation (not recommended)
```

#### Autonomous Mode Options
```bash
--autonomous              # Enable full autonomous pipeline (global flag)
--system                 # Use system-wide configuration (global flag)
--auto-threshold N       # Reference threshold for notifications (global flag)
```

#### Examples

**Manual Pipeline:**
```bash
# Complete manual pipeline
otto-bgp pipeline devices.csv --output-dir /var/lib/otto-bgp/output
```

**Autonomous Pipeline:**
```bash
# Autonomous with custom threshold (autonomous must be enabled in configuration)
otto-bgp --autonomous --auto-threshold 150 pipeline devices.csv --output-dir /var/lib/otto-bgp/output
```

### 5. list - Resource Listing

List discovered routers, AS numbers, and BGP groups.

```bash
otto-bgp list <resource_type> [options]
```

#### Resource Types
```bash
routers                   # List discovered routers
as                       # List discovered AS numbers
groups                   # List BGP groups
policies                 # List generated policies
```

#### Options
```bash
--output-dir DIR         # Directory to scan (default: ./policies)
--format FORMAT          # Output format: table, json, csv (default: table)
--filter PATTERN         # Filter results by pattern
```

#### Examples
```bash
# List all discovered routers
otto-bgp list routers

# List AS numbers in JSON format
otto-bgp list as --format json

# List policies with filtering
otto-bgp list policies --filter "AS133*" --output-dir /var/lib/otto-bgp/policies
```

### 6. test-proxy - Proxy Testing

Test IRR proxy connectivity and configuration.

```bash
otto-bgp test-proxy [options]
```

#### Options
```bash
--test-bgpq4             # Test bgpq4 through proxy
--test-as AS_NUMBER      # Test with specific AS number
--verbose               # Show detailed connectivity information
```

#### Examples
```bash
# Test proxy connectivity
otto-bgp test-proxy

# Test bgpq4 through proxy
otto-bgp test-proxy --test-bgpq4 --test-as 13335 --verbose
```


## Flag Validation and Behavior

### Autonomous Mode Validation

The `--autonomous` flag triggers comprehensive validation:

```python
def validate_autonomous_mode(args, config):
    """Validate autonomous mode settings"""
    
    # Check configuration
    if args.autonomous and not config.autonomous_mode.enabled:
        logger.warning("Autonomous mode requested but not enabled in configuration")
        logger.info("Run ./install.sh --autonomous to enable autonomous mode")
        return False
    
    # Recommend system installation
    if args.autonomous and not args.system:
        logger.warning("Autonomous mode works best with system installation (--system)")
    
    # Validate threshold (informational warning only)
    if args.auto_threshold > 1000:
        logger.warning(f"Auto-threshold {args.auto_threshold} is very high (informational only)")
        logger.info("Note: Threshold is used for notification context only")
    
    return True
```

### Error Handling

**Configuration Errors:**
```bash
$ otto-bgp apply --autonomous
ERROR: Autonomous mode requested but not enabled in configuration
INFO: Run ./install.sh --autonomous to enable autonomous mode
```

**Invalid Arguments:**
```bash
$ otto-bgp apply --auto-threshold -1
ERROR: auto-threshold must be a positive integer

$ otto-bgp apply --router nonexistent-router
ERROR: Router 'nonexistent-router' not found in configuration
```

**Network Errors:**
```bash
$ otto-bgp discover devices.csv
ERROR: Failed to connect to router1.company.com: Connection timeout
INFO: Check SSH connectivity and credentials
```

## Environment Variables

### Configuration Override

```bash
# SSH Configuration
export OTTO_BGP_SSH_USERNAME=admin
export OTTO_BGP_SSH_KEY_FILE=/var/lib/otto-bgp/ssh-keys/otto-bgp
export OTTO_BGP_SSH_TIMEOUT=30

# BGPq4 Configuration  
export OTTO_BGP_BGPQ4_PATH=/usr/local/bin/bgpq4
export OTTO_BGP_BGPQ4_TIMEOUT=45

# Autonomous Mode Configuration
export OTTO_BGP_AUTONOMOUS_ENABLED=true
export OTTO_BGP_AUTO_APPLY_THRESHOLD=100

# Email Notification Configuration
export OTTO_BGP_SMTP_SERVER=smtp.company.com
export OTTO_BGP_SMTP_PORT=587
export OTTO_BGP_EMAIL_FROM=otto-bgp@company.com
export OTTO_BGP_EMAIL_TO=network-team@company.com

# Directory Configuration
export OTTO_BGP_OUTPUT_DIR=/var/lib/otto-bgp
export OTTO_BGP_CONFIG_DIR=/etc/otto-bgp
export OTTO_BGP_LOG_DIR=/var/log/otto-bgp

# Development/Testing
export OTTO_BGP_DEV_MODE=true
export OTTO_BGP_TEST_MODE=true
export OTTO_BGP_DEBUG=true
```

### Installation Mode Variables

```bash
# Installation mode selection
export OTTO_BGP_INSTALLATION_MODE=system  # user, system
export OTTO_BGP_SERVICE_USER=otto-bgp
export OTTO_BGP_SYSTEMD_ENABLED=true

# Autonomous mode setup
export OTTO_BGP_SETUP_MODE=false  # NEVER set to true in production
```

## Configuration File Integration

### CLI Flag to Config Mapping

| CLI Flag | Configuration Path | Default |
|----------|-------------------|---------|
| `--autonomous` | `autonomous_mode.enabled` | `false` |
| `--auto-threshold` | `autonomous_mode.auto_apply_threshold` | `100` |
| `--system` | `installation_mode.type` | `"user"` |
| `--timeout` | `ssh.connection_timeout` | `30` |
| `--parallel` | `discovery.max_workers` | `5` |

### Configuration Precedence

1. **CLI flags** (highest priority)
2. **Environment variables**
3. **Configuration file**
4. **Default values** (lowest priority)

Example:
```bash
# CLI flag overrides config file
otto-bgp apply --autonomous --auto-threshold 200
# Uses threshold=200 regardless of config file setting
```

## Advanced Usage Patterns

### Batch Operations

```bash
# Process multiple device files
for devices in production_*.csv; do
    otto-bgp pipeline "$devices" --autonomous --output-dir "/var/lib/otto-bgp/batch-$(date +%Y%m%d)"
done

# Apply policies to multiple routers
for router in router1 router2 router3; do
    otto-bgp apply --router "$router" --autonomous
done
```

### Scheduled Operations

```bash
# Daily autonomous pipeline (cron)
0 2 * * * /usr/local/bin/otto-bgp pipeline /etc/otto-bgp/devices.csv --autonomous --output-dir /var/lib/otto-bgp/daily

# Hourly discovery for change detection
0 * * * * /usr/local/bin/otto-bgp discover /etc/otto-bgp/devices.csv --show-diff --output-dir /var/lib/otto-bgp/monitoring
```

### Monitoring and Alerting

```bash
# Check autonomous operation status
otto-bgp pipeline devices.csv --autonomous --dry-run

# Generate status report
otto-bgp list routers --format json | jq '.[] | select(.last_update > "2025-08-16")'

# Monitor for failed operations
grep "FAILED" /var/log/otto-bgp/otto-bgp.log | tail -10
```

## Exit Codes

| Code | Meaning | Description |
|------|---------|-------------|
| `0` | Success | Operation completed successfully |
| `1` | General Error | Configuration or argument error |
| `2` | Invalid Usage | Invalid command line usage |
| `3` | Safety Check Failed | Safety validation failed |
| `4` | NETCONF Connection Failed | NETCONF connection failed |
| `5` | Policy Validation Failed | Policy validation failed |
| `6` | BGP Session Impact Critical | Critical BGP session impact detected |
| `7` | Rollback Failed | Configuration rollback failed |
| `8` | Autonomous Mode Blocked | Autonomous mode operation blocked |
| `130` | Interrupted | User interruption (Ctrl+C) |

## Best Practices

### Command Usage Guidelines

1. **Always test first**: Use `--dry-run` before applying policies
2. **Start with user mode**: Test with `--user` before `--system`
3. **Enable autonomous gradually**: Start with low `--auto-threshold`
4. **Monitor logs**: Check `/var/log/otto-bgp/` after autonomous operations
5. **Use confirmation**: Include `--confirm` for manual applications

### Safety Recommendations

1. **Backup configurations**: Ensure router backups before policy changes
2. **Monitor BGP sessions**: Watch for session flaps after application
3. **Test in lab first**: Validate policies in lab environment
4. **Review email alerts**: Monitor autonomous operation notifications
5. **Maintain rollback capability**: Keep confirmed commits enabled

### Performance Optimization

```bash
# High-performance discovery
otto-bgp discover devices.csv --parallel 10 --timeout 45

# Fast policy generation
otto-bgp policy as_list.txt --parallel 8 --timeout 60

# Efficient batch processing
otto-bgp pipeline devices.csv --autonomous --output-dir /var/lib/otto-bgp --separate
```

This CLI reference provides comprehensive documentation for all Otto BGP v0.3.2 commands, flags, and autonomous operation capabilities.

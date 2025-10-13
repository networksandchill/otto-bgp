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
| `collect` | Collect raw BGP peer data over SSH | ❌ |
| `process` | Process text or extract AS numbers | ❌ |
| `discover` | Discover BGP configs and mappings | ❌ |
| `policy` | Generate BGP prefix‑list policies | ✅ |
| `apply` | Apply policies to routers via NETCONF | ✅ |
| `pipeline` | Run complete workflow (collect → process → policy) | ✅ |
| `list` | List discovered routers/AS/groups | ❌ |
| `test-proxy` | Test IRR proxy connectivity | ❌ |
| `rpki-check` | Validate RPKI cache freshness | ❌ |

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
--dev                   # Use Podman for bgpq4 (development)
--no-rpki               # Disable RPKI validation (policy/pipeline)
```

## Command Reference

### 1. collect - BGP Data Collection

Collect BGP peer data from Juniper devices via SSH.

```bash
otto-bgp collect <devices.csv> [options]
```

#### Arguments
- `devices.csv` - CSV with an `address` column (required)

#### Options
```bash
--output-dir DIR          # Output directory (default: .)
--timeout SECONDS         # SSH connection timeout (default: 30)
--command-timeout SECONDS # SSH command timeout (default: 60)
```

#### Example
```bash
otto-bgp collect devices.csv --output-dir ./collected
```

### 2. process - Text Processing / AS Extraction

Process text files or extract AS numbers.

```bash
otto-bgp process <input_file> [options]
```

#### Options
```bash
-o FILE, --output FILE    # Write processed output to file
--extract-as              # Extract AS numbers (one per line)
--pattern PATTERN         # standard|peer_as|explicit_as|autonomous_system
```

#### Example
```bash
otto-bgp process bgp.txt --extract-as -o asns.txt
```

### 3. discover - Router Discovery

Discover BGP configurations and generate YAML mappings.

```bash
otto-bgp discover <devices.csv> [options]
```

#### Options
```bash
--output-dir DIR          # Output dir for discovered data (default: policies)
--show-diff               # Show diff report when changes detected
--timeout SECONDS         # SSH connection timeout (default: 30)
```

#### Example
```bash
otto-bgp discover devices.csv --show-diff --output-dir ./policies
```

### 4. policy - Policy Generation

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

Note: `--no-rpki` is available as a global flag and applies to this command.

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

### 5. apply - Policy Application

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

Global `--autonomous/--system/--auto-threshold` flags apply here.

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
# Standard autonomous application (router required)
otto-bgp apply --router edge-router1 --autonomous --auto-threshold 100

# System-wide autonomous application
otto-bgp apply --router edge-router1 --system --autonomous

# Autonomous with custom threshold (informational only)
otto-bgp apply --router edge-router1 --autonomous --auto-threshold 200 --policy-dir /var/lib/otto-bgp/policies
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

### 6. pipeline - Complete Workflow

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
--input-file FILE         # Process a file directly (bypasses SSH collection; CSV arg is ignored)
-s, --separate            # Generate per-resource output files
--dry-run                 # Skip NETCONF policy application (generate and report only)
```

Global autonomous flags apply (`--autonomous/--system/--auto-threshold`).

#### Examples

**Manual Pipeline:**
```bash
# Complete manual pipeline
otto-bgp pipeline devices.csv --output-dir /var/lib/otto-bgp/output

# Direct-file processing with separate outputs (no SSH collection)
otto-bgp pipeline devices.csv --input-file bgp.txt --separate --output-dir ./policies

# Dry-run to generate policies without applying to routers
otto-bgp pipeline devices.csv --dry-run --output-dir ./out
```

**Autonomous Pipeline:**
```bash
# Autonomous with custom threshold (autonomous must be enabled in configuration)
otto-bgp --autonomous --auto-threshold 150 pipeline devices.csv --output-dir /var/lib/otto-bgp/output
```

### 7. list - Resource Listing

List discovered routers, AS numbers, and BGP groups.

```bash
otto-bgp list <resource_type> [options]
```

#### Resource Types
```bash
routers                   # List discovered routers
as                        # List discovered AS numbers
groups                    # List BGP groups
```

#### Options
```bash
--output-dir DIR          # Directory containing discovered data (default: policies)
--format FORMAT           # Output format: text (default), json, or yaml
--filter KEY=VALUE        # Filter results with key=value expressions (repeatable)
```

#### Examples
```bash
# List all discovered routers (default text format)
otto-bgp list routers

# List AS numbers with JSON output
otto-bgp list as --format json

# List BGP groups with YAML output
otto-bgp list groups --format yaml --output-dir ./policies

# Filter routers by AS count
otto-bgp list routers --filter as_count=5

# Filter AS numbers by router count and output as JSON
otto-bgp list as --filter router_count=2 --format json

# Multiple filters (filters are AND combined)
otto-bgp list groups --filter as_count=3 --filter router_count=1
```

### 8. test-proxy - Proxy Testing

Test IRR proxy connectivity and configuration.

```bash
otto-bgp test-proxy [options]
```

#### Options
```bash
--test-bgpq4              # Test bgpq4 through proxy
--timeout SECONDS         # Proxy connection timeout (default: 10)
```

#### Examples
```bash
# Test proxy connectivity
otto-bgp test-proxy

# Test bgpq4 through proxy (use -v for details)
otto-bgp -v test-proxy --test-bgpq4
```

### 9. rpki-check - RPKI Cache Validation

Validate RPKI cache freshness and readability.

```bash
otto-bgp rpki-check [--max-age SECONDS]
```
Outputs a success/failure and cache age summary.


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

Otto BGP v0.3.2 provides enhanced error formatting with visual symbols and actionable guidance.

**Error Message Symbols:**
- `✓` Success operations
- `⚠` Warnings and advisories  
- `✗` Errors and failures
- `🛡️` Safety and security events
- `🔒` RPKI validation status
- `🌐` Network operations
- `⚙️` Configuration issues

**Configuration Errors:**
```bash
$ otto-bgp apply --autonomous
✗ Autonomous mode requested but not enabled in configuration
⚙️ Configuration required: autonomous_mode.enabled must be true
✓ Solution: Run ./install.sh --autonomous to enable autonomous mode
```

**Safety and Security Events:**
```bash
$ otto-bgp apply --router edge-router1 --force
🛡️ Safety guardrail triggered: prefix_count_exceeded
⚠ Risk Level: HIGH - proposed changes exceed 25% threshold
✗ Action: Review policy changes and reduce scope, or use --confirm for manual approval

$ otto-bgp collect devices.csv
🔒 SSH host key verification failed for router1.company.com
✗ Security: Host key mismatch detected - possible man-in-the-middle attack
✓ Action: Verify host key fingerprint and update known_hosts file
```

**Validation Errors:**
```bash
$ otto-bgp apply --auto-threshold -1
✗ Input validation failed: auto-threshold must be a positive integer
⚙️ Valid range: 1-10000 (recommended: 100-500)

$ otto-bgp policy invalid_file.txt
✗ Input file error: No AS numbers found in input file
✓ Expected format: AS12345 or 12345 (one per line or mixed with text)
```

**Network Errors:**
```bash
$ otto-bgp discover devices.csv
🌐 Network operation failed: SSH connection to router1.company.com
✗ Connection timeout after 30 seconds
✓ Check: Network connectivity, SSH credentials, and firewall rules
```

**RPKI Validation:**
```bash
$ otto-bgp policy as_numbers.txt
🔒 RPKI validation status: 3 valid, 1 invalid, 2 not found
⚠ AS64500: RPKI INVALID - origin validation failed
✓ AS13335: RPKI VALID - origin validation passed
ℹ AS99999: RPKI NOT FOUND - no ROA data available
```

## Environment Variables

### Configuration Override

```bash
# SSH (used by collectors)
export SSH_USERNAME=admin
export SSH_PASSWORD=…
export SSH_KEY_PATH=/var/lib/otto-bgp/ssh-keys/otto-bgp

# Autonomous Mode
export OTTO_BGP_AUTONOMOUS_ENABLED=true
export OTTO_BGP_AUTO_THRESHOLD=100   # Informational only

# Email (autonomous notifications)
export OTTO_BGP_SMTP_SERVER=smtp.company.com
export OTTO_BGP_SMTP_PORT=587
export OTTO_BGP_SMTP_USERNAME=otto-bgp@company.com
export OTTO_BGP_SMTP_PASSWORD=…
export OTTO_BGP_FROM_ADDRESS=otto-bgp@company.com
# Recipients (to_addresses) can be supplied via OTTO_BGP_EMAIL_TO or through config.json; values are normalized by the WebUI/backend when saved.

# Directories and logging
export OTTO_BGP_OUTPUT_DIR=/var/lib/otto-bgp
export OTTO_BGP_CONFIG_DIR=/etc/otto-bgp
export OTTO_BGP_LOG_LEVEL=INFO
export OTTO_BGP_LOG_FILE=/var/lib/otto-bgp/logs/otto-bgp.log

# Installation mode hints (read by app config)
export OTTO_BGP_INSTALL_MODE=system   # user|system
export OTTO_BGP_SERVICE_USER=otto-bgp
```

### Installation Mode Variables

Use `OTTO_BGP_INSTALL_MODE=system|user` and `OTTO_BGP_SERVICE_USER` to hint configuration in environments where a JSON config is used. The installer (install.sh) determines actual paths and ownership at install time.

## Configuration File Integration

### CLI Flag to Config Mapping

Common relationships used by the app:
- `--autonomous` (global) requires `autonomous_mode.enabled=true` in config to take effect.
- `--auto-threshold` maps to `autonomous_mode.auto_apply_threshold` (informational only).
- `--system` influences installation_mode/type at runtime.
- `--timeout` flags map to command‑specific timeouts.

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

Prefer the systemd timer created by install.sh for scheduled runs. For cron-like scheduling, invoke the `pipeline` or `policy` commands directly with required arguments.

### Monitoring and Alerting

Use `journalctl -u otto-bgp.service` and application logs for monitoring. The `list` command supports JSON and YAML output formats via `--format` for automation and monitoring integration.

## Known Gaps and Limitations

### Configuration and Environment
- **BGPQ4 env vars**: `OTTO_BGP_BGPQ4_*` overrides (mode, timeout, workers, retry, IRR source, protocol toggles) are honored by the ConfigManager. CLI flags still take precedence when provided.

### Feature Gaps
- **test-proxy**: Has `--test-bgpq4` and `--timeout`. There is no `--test-as` flag; test uses a built-in AS.
- **Batch operations**: No native support for processing multiple device files in a single command.
- **Configuration validation**: No built-in config file validation subcommand.

### Exit Codes
- Exit codes are comprehensive (80+ codes) covering all error conditions, not the simplified set shown in documentation.

## Exit Codes

Otto BGP uses comprehensive exit codes following UNIX conventions for monitoring and automation integration.

### Exit Code Categories

| Range | Category | Description |
|-------|----------|-------------|
| `0` | Success | Operation completed successfully |
| `1-2` | User/Configuration Errors | Basic usage and configuration errors |
| `3-63` | Application Errors | Otto BGP specific operational errors |
| `64-78` | System Errors | System-level errors (following sysexits.h) |
| `128+` | Signal Termination | Process terminated by signals |

### Key Exit Codes

| Code | Name | Description |
|------|------|-------------|
| `0` | SUCCESS | Operation completed successfully |
| `1` | GENERAL_ERROR | General error occurred |
| `2` | INVALID_USAGE | Invalid command line usage |
| `3` | SAFETY_CHECK_FAILED | Safety validation failed |
| `4` | NETCONF_CONNECTION_FAILED | NETCONF connection failed |
| `5` | POLICY_VALIDATION_FAILED | Policy validation failed |
| `6` | BGP_SESSION_IMPACT_CRITICAL | Critical BGP session impact detected |
| `7` | ROLLBACK_FAILED | Configuration rollback failed |
| `8` | AUTONOMOUS_MODE_BLOCKED | Autonomous mode operation blocked |
| `12` | HOST_KEY_VERIFICATION_FAILED | SSH host key verification failed |
| `13` | COMMAND_INJECTION_DETECTED | Command injection attempt detected |
| `16` | GUARDRAIL_VIOLATION | Safety guardrail violation |
| `21` | VALIDATION_FAILED | Input validation failed |
| `130` | SIGINT_TERMINATION | User interruption (Ctrl+C) |
| `143` | SIGTERM_TERMINATION | Terminated by system signal |

**Note**: The complete exit code system includes 80+ specific codes for precise error handling and monitoring integration. Use `echo $?` after command execution to retrieve the exit code.

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
# Optimized discovery with extended timeout
otto-bgp discover devices.csv --timeout 45

# Policy generation with extended timeout
otto-bgp policy as_list.txt --timeout 60

# Efficient autonomous pipeline
otto-bgp pipeline devices.csv --autonomous --output-dir /var/lib/otto-bgp
```

This CLI reference provides comprehensive documentation for all Otto BGP v0.3.2 commands, flags, and autonomous operation capabilities.

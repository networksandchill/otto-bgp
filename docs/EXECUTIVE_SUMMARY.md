# Otto BGP v0.3.2 Executive Summary

## Overview

Otto BGP discovers BGP context from Juniper routers over SSH, extracts AS numbers, generates router-aware Junos `policy-options` prefix-lists using bgpq4 (with optional IRR proxy tunneling), and applies changes via NETCONF with always-on safety guardrails. Email notifications for NETCONF events are configurable.

## Architecture

Otto BGP implements a sophisticated **router-aware pipeline** that maintains device identity throughout all processing stages. The system processes multiple routers in parallel while preserving individual router context, generating per-router policies with comprehensive safety validation.

**Key Architectural Features:**
- **Router Identity Preservation**: Each router maintains its `RouterProfile` from collection through policy generation
- **Parallel Processing**: Multiple devices processed simultaneously with individual error handling
- **Layered Safety**: Always-active guardrails plus optional RPKI validation based on operation mode
- **Flexible Deployment**: Supports both native and containerized bgpq4, with optional IRR proxy tunneling

### High-Level Data Flow

Data flows through five sequential stages:
1. **Device List** - Input CSV containing router hostnames, IPs, and roles
2. **Collection** - SSH connections retrieve BGP configuration data from routers
3. **Discovery** - Inspection of BGP groups and extraction of AS numbers
4. **Generation** - bgpq4 queries IRRs to create prefix-lists for each AS
5. **Validation** - Safety guardrails check prefix counts, bogons, and optionally RPKI
6. **Application** - NETCONF applies validated policies with confirmed commits

In autonomous mode, only low-risk changes proceed automatically. System mode requires manual confirmation for all changes.

### Detailed Module Architecture

**Data Collection Phase:**
- **Input**: CSV file with router details (hostname, IP, role) flows into `collectors/juniper_ssh.py`
- **Processing**: SSH collector establishes secure connections with host key verification
- **Output**: Raw BGP configuration data preserved with router identity

**Discovery & Processing Phase:**
- **Input**: Raw BGP data flows to `discovery/inspector.py` and `processors/as_extractor.py`
- **Processing**: Inspector identifies BGP groups and peer relationships; extractor validates AS numbers against RFC ranges
- **Output**: RouterProfile objects containing BGP groups mapped to AS numbers

**Policy Generation Phase:**
- **Input**: RouterProfiles with AS numbers flow to `generators/bgpq4_wrapper.py`
- **Processing**: bgpq4 queries Internet Routing Registries (via WHOIS port 43 or HTTPS 443), optionally through SSH tunnel proxy
- **Output**: Junos prefix-lists stored in per-router directories (`policies/router-name/`)

**Safety Validation Phase:**
- **Input**: Generated policies flow to `appliers/guardrails.py` and `validators/rpki.py`
- **Processing**: Always-active guardrails check prefix counts, detect bogons, prevent concurrent operations; RPKI validates prefixes against ROA cache
- **Output**: Risk assessment (LOW/MEDIUM/HIGH/CRITICAL) with detailed safety reports

**Application Phase:**
- **Input**: Validated policies flow to `appliers/juniper_netconf.py`
- **Processing**: NETCONF establishes secure connection, applies configuration with confirmed commit and automatic rollback timer
- **Output**: Deployment matrix showing cross-router relationships and application status

## Operation Modes

**System Mode** (Interactive):
- On-demand execution with manual confirmation
- NETCONF operations require explicit user confirmation
- 25% maximum prefix count change threshold
- RPKI validation optional
- Concurrent operations allowed

**Autonomous Mode** (Scheduled):
- Scheduled execution via systemd timer
- Automatic policy application with stricter safety thresholds
- 10% maximum prefix count change threshold
- RPKI validation required when configured
- No concurrent operations allowed
- Auto-confirmation only after health checks pass

### Operation Mode Decision Flow

**Mode Detection:**
The `OTTO_BGP_MODE` environment variable determines the operational path. System mode enables interactive operation while autonomous mode runs unattended with stricter safety requirements.

**System Mode Path:**
1. Guardrail validation applies 25% prefix count threshold with optional RPKI
2. Risk assessment evaluates changes (LOW/MEDIUM/HIGH/CRITICAL)
3. All risk levels except CRITICAL proceed to NETCONF application
4. Manual confirmation required before committing changes
5. User must explicitly approve or changes are rolled back

**Autonomous Mode Path:**
1. Guardrail validation applies stricter 10% threshold with required RPKI
2. Risk assessment blocks anything above LOW risk
3. Low-risk changes apply automatically with timer-based commit
4. Post-apply health checks validate successful application
5. Automatic finalization if health checks pass
6. Email notifications sent with operation report

**Blocking Conditions:**
- Critical risk detection in any mode immediately terminates operation
- Medium/High risk in autonomous mode blocks execution
- Failed health checks or timeout triggers automatic rollback

## Security Posture

**Network Security:**
- SSH host key strict verification with managed `known_hosts` database
- NETCONF connections with confirmed commits and automatic rollback
- Optional SSH tunnel proxy for IRR queries in restricted environments

**System Hardening:**
- SystemD services run as dedicated `otto-bgp` user with minimal privileges
- Filesystem restrictions: read-only access to configuration, limited write access to output directories
- Network restrictions: private network access only (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
- Resource limits: 1GB memory, 25% CPU quota, 50 process limit

**Input Validation:**
- AS number validation against RFC 4893 range (0-4294967295)
- Policy name sanitization to prevent command injection
- Subprocess execution with argument validation
- Timeout enforcement on all network operations

**RPKI Validation:**
- Tri-state validation logic (VALID/INVALID/NOTFOUND)
- VRP cache processing with fail-closed behavior
- Allowlist support for known-good prefixes
- Offline validation capabilities

### Always-Active Guardrail System

**Input Context:**
Policy context containing AS numbers, prefix lists, router profiles, and operation mode flows into the guardrail system for comprehensive safety validation.

**Guardrail Components (Always Active):**
- **Prefix Count Guardrail**: Monitors prefix count changes against mode-specific thresholds (System: 25%, Autonomous: 10%)
- **Bogon Prefix Guardrail**: Detects RFC-defined invalid ranges (0.0.0.0/8, 10.0.0.0/8, etc.) that should never appear in production
- **Concurrent Operation Guardrail**: Uses lock file management to prevent overlapping executions that could cause conflicts
- **Signal Handling Guardrail**: Intercepts SIGTERM/SIGINT for graceful shutdown and cleanup

**Risk Assessment:**
All guardrail outputs aggregate into a unified risk level (LOW/MEDIUM/HIGH/CRITICAL) that determines the safety decision path.

**Safety Decisions:**
- **Critical Risk**: Blocks execution in any mode with immediate termination
- **Medium/High Risk**: System mode proceeds with warnings and manual confirmation; Autonomous mode blocks
- **Low Risk**: Both modes can proceed (System with confirmation, Autonomous automatically)

## Risk Assessment

**Configuration Scope:**
- Modifies only Junos `policy-options` prefix-lists
- Does not alter BGP protocol configuration, interfaces, or routing policy logic
- Changes are isolated to prefix-list definitions within policy-options stanza

**Safety Mechanisms:**
- **Always-active guardrails:** Cannot be disabled in production
  - Prefix count threshold monitoring (10% autonomous, 25% system mode)
  - Bogon prefix detection using RFC-defined ranges
  - Concurrent operation prevention with lock files
  - Signal handling for graceful shutdown
- **NETCONF safety:** Confirmed commits with automatic rollback timers
- **RPKI validation:** Optional in system mode, configurable requirement in autonomous mode

**External Dependencies:**
- **IRR data availability:** bgpq4 requires access to Internet Routing Registries
- **RPKI data freshness:** VRP cache staleness triggers fail-closed behavior
- **SSH connectivity:** Host key verification requires initial setup
- **SystemD integration:** Autonomous mode requires proper timer configuration

### Deployment Architecture

**SystemD Service Flow:**
1. `otto-bgp.timer` triggers scheduled execution
2. `otto-bgp-autonomous.service` starts with hardened security profile
3. `otto-bgp-rpki-preflight.service` validates RPKI cache before main execution
4. Service runs as dedicated `otto-bgp` user with no shell access

**Filesystem Security Model:**
- **Read-Only Access**: Configuration (`/etc/otto-bgp/`), installation (`/opt/otto-bgp/`), SSH keys (`/var/lib/otto-bgp/ssh-keys/`)
- **Write Access**: Limited to output policies (`/var/lib/otto-bgp/output/`), logs (`/var/lib/otto-bgp/logs/`), and RPKI cache (`/var/lib/otto-bgp/cache/`)
- **Privilege Separation**: Service account cannot modify system files or configurations

**Network Boundaries:**
- **Allowed**: Private networks only (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
- **Blocked**: All public IP ranges preventing internet access
- **External Connections**: 
  - Juniper routers via SSH (port 22) and NETCONF (port 830)
  - Internet Routing Registries via WHOIS (port 43) and HTTPS (port 443)
  - Optional SSH tunnel proxy for restricted environments

**Resource Constraints:**
- Memory limited to 1GB maximum
- CPU quota restricted to 25% of system capacity
- Maximum 50 concurrent tasks
- 180-second startup timeout, 30-second shutdown timeout

**Operational Risks:**
- **Large AS sets:** Memory usage scales with AS set size and bgpq4 output
- **Network partitions:** IRR or RPKI unavailability impacts policy generation

## Known Gaps and Limitations

**RPKI Behavior:**
- **Fail-closed enforcement:** When configured (default), VRP cache staleness or absence blocks operations; preflight and guardrail checks enforce freshness
- **VRP sources:** Supports rpki-client and routinator JSON formats; other validators may require format conversion

**IPv6 Support:**
- **Prefix counting:** Guardrail counters are IPv4 and IPv6 aware, accurately counting both protocol families for risk calculations
- **Policy generation scope:** bgpq4 can generate both IPv4 and IPv6 policies with consistent guardrail validation across both families

**Operational Dependencies:**
- **IRR availability requirements:** bgpq4 requires Internet Routing Registry access; network partitions impact policy generation
- **SSH tunnel proxy limitations:** IRR proxy functionality depends on reachable jump hosts and properly configured SSH keys
- **Systemd integration:** Autonomous mode requires systemd; not compatible with other init systems
- **Host key management:** Initial SSH host key collection requires manual setup process before production use

**Monitoring and Alerting:**
- **Email notification dependency:** WebUI-managed SMTP settings still rely on external servers and offer best-effort delivery with no built-in retry/backoff.
- **Limited metrics export:** No integration with monitoring systems like Prometheus or SNMP
- **Log aggregation:** Structured logging exists but requires external log management for centralized monitoring

**Scalability Considerations:**
- **Memory usage with large AS sets:** Memory consumption scales with AS set size and bgpq4 output volume; RPKI VRP validation uses streaming and lazy caching to reduce memory during validation.
- **Parallel load tuning:** Pipeline runs device collection and policy generation in parallel; operators should tune worker counts for IRR/API limits and router session capacity.
- **Concurrent operation locks:** A process lock prevents concurrent runs. Stale locks are automatically removed when the holding PID is gone.

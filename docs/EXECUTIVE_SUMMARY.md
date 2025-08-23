# Otto BGP v0.3.2 Executive Summary

## Overview

Otto BGP discovers BGP context from Juniper routers over SSH, extracts AS numbers, generates router-aware Junos `policy-options` prefix-lists using bgpq4 (with optional IRR proxy tunneling), and applies changes via NETCONF with always-on safety guardrails. Email notifications for NETCONF events are configurable.

## Architecture

Otto BGP implements a router-aware pipeline that maintains device identity throughout all processing stages:

```mermaid
flowchart LR
  subgraph Inputs
    A["Devices CSV"]
  end

  subgraph Collection
    C1["collectors/juniper_ssh.py<br/>SSH + host key verify"]
  end

  subgraph Discovery/Processing
    D1["discovery/inspector.py<br/>Junos BGP groups/ASNs"]
    P1["processors/as_extractor.py<br/>AS parsing + cleaning"]
  end

  subgraph Generation
    G1["generators/bgpq4_wrapper.py<br/>bgpq4 (native/docker/podman)"]
    X["proxy/irr_tunnel.py<br/>optional SSH tunnels"]
  end

  subgraph Validation
    V1["validators/rpki.py<br/>RPKI VRP checks (config-dependent)"]
  end

  subgraph Application
    A1["appliers/juniper_netconf.py<br/>confirmed commit + rollback"]
    S1["appliers/safety.py + guardrails.py<br/>always-on guardrails"]
  end

  A --> C1 --> D1 --> P1 --> G1 --> V1 --> A1
  G1 <---> X
  S1 -.enforces before/after apply.- A1
```

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

```mermaid
sequenceDiagram
  participant Pipe as Pipeline
  participant G as Guardrails/RPKI
  participant N as NETCONF Applier
  Note over Pipe: Autonomous mode
  Pipe->>G: validate changes (prefix counts, bogons, RPKI)
  G-->>Pipe: risk low?
  alt low risk
    Pipe->>N: load + commit confirmed (timer)
    N->>G: post-apply health checks
    G-->>N: pass
    N->>N: auto-finalize commit
  else not low
    Pipe-->>N: do not auto-apply
  end
```

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

**Operational Risks:**
- **IPv6 prefix handling:** Guardrail counters optimized for IPv4 patterns
- **Large AS sets:** Memory usage scales with AS set size and bgpq4 output
- **Network partitions:** IRR or RPKI unavailability impacts policy generation

## Known Gaps and Limitations

**Platform Limitations:**
- **Juniper-only implementation:** Collection via SSH and NETCONF application target Junos exclusively; other network vendors (Cisco, Arista, etc.) are not supported
- **Python 3.10+ requirement:** Uses modern Python features not available in older distributions

**RPKI Implementation Gaps:**
- **Configuration-dependent validation:** RPKI checks only run when VRP cache paths and settings are provided in configuration
- **Cache staleness handling:** Fail-closed behavior when VRP data exceeds configured age threshold may block legitimate operations
- **Limited VRP sources:** Currently supports rpki-client and routinator JSON formats; other RPKI validators require format conversion

**IPv6 Support Limitations:**
- **Prefix counting accuracy:** Guardrail prefix counters use IPv4-optimized patterns that may undercount IPv6 prefixes in risk calculations
- **Policy generation scope:** While bgpq4 can generate IPv6 policies, guardrail thresholds should be reviewed for IPv6-heavy environments

**Operational Dependencies:**
- **IRR availability requirements:** bgpq4 requires Internet Routing Registry access; network partitions impact policy generation
- **SSH tunnel proxy limitations:** IRR proxy functionality depends on reachable jump hosts and properly configured SSH keys
- **SystemD integration:** Autonomous mode requires systemd; not compatible with other init systems
- **Host key management:** Initial SSH host key collection requires manual setup process before production use

**Monitoring and Alerting:**
- **Email notification dependency:** Autonomous mode email notifications require proper SMTP configuration; silent failures reduce operational visibility
- **Limited metrics export:** No integration with monitoring systems like Prometheus or SNMP
- **Log aggregation:** Structured logging exists but requires external log management for centralized monitoring

**Scalability Considerations:**
- **Memory usage with large AS sets:** Memory consumption scales linearly with AS set size and bgpq4 output volume
- **Sequential processing:** Router processing is sequential; no parallel SSH collection across multiple devices
- **Lock file cleanup:** Stale operation locks require manual cleanup if processes terminate unexpectedly

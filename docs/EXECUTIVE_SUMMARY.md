# Otto BGP v0.3.2 Executive Summary

## Project Overview

Otto BGP is an autonomous BGP policy generator and applier that replaces manual prefix list management. It discovers BGP configuration from Juniper routers, extracts AS numbers, generates Junos policy-options prefix-lists using Internet Routing Registry (IRR) data via bgpq4, and supports production-grade autonomous application with always‑on safety guardrails and email audit trails.

**Core Value**: Eliminates manual BGP policy maintenance while safeguarding stability through automated discovery, validation, and controlled application.

## System Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌──────────────────────┐    ┌─────────────────┐
│   COLLECTORS    │    │   PROCESSORS    │    │      GENERATORS      │    │     APPLIERS     │
│                 │    │                 │    │                      │    │                 │
│ • SSH Discovery │───▶│ • AS Extraction │───▶│ • bgpq4 Wrapper      │───▶│ • NETCONF Apply  │
│ • Config Parser │    │ • Data Cleaning │    │ • IRR Queries        │    │ • Safety Guardrails│
│ • Device Mgmt   │    │ • Validation    │    │ • IRR Proxy (tunnel) │    │ • Email Audit    │
└─────────────────┘    └─────────────────┘    └──────────────────────┘    └─────────────────┘
         │                       │                        │                        │
         ▼                       ▼                        ▼                        ▼
┌─────────────────┐    ┌─────────────────┐     ┌─────────────────┐    ┌─────────────────┐
│ Router Profiles │    │ AS Number Lists │     │ Policy Files    │    │ Applied Configs │
│ BGP Groups      │    │ Cleaned Data    │     │ Router-Specific │    │ (Manual/Auto)   │
└─────────────────┘    └─────────────────┘     └─────────────────┘    └─────────────────┘
```

## Operational Workflow

```
                              ┌───────────────────────────────────┐
                              │           DISCOVERY PHASE         │
                              │                                   │
                              │  CSV Input ──▶ SSH Collection    │
                              │      │             │              │
                              │      ▼             ▼              │
                              │  Device Info ──▶ BGP Configs     │
                              └───────────────┬───────────────────┘
                                              │
                                              ▼
                              ┌───────────────────────────────────┐
                              │         GENERATION PHASE          │
                              │                                   │
                              │  AS Numbers ──▶ IRR Queries      │
                              │      │              │             │
                              │      ▼              ▼             │
                              │  Validation ──▶ Policy Files     │
                              └───────────────┬───────────────────┘
                                              │
                                              ▼
                              ┌───────────────────────────────────┐
                              │        APPLICATION PHASE          │
                              │   (MANUAL WITH SAFETY, OR AUTO)   │
                              │                                   │
                              │  Guardrails  ──▶ Email Audit     │
                              │      │                 │          │
                              │      ▼                 ▼          │
                              │  Commit/Confirm ─▶ NETCONF Events│
                              └───────────────────────────────────┘
```

## Security Architecture

Otto BGP implements defense‑in‑depth controls across collection, generation, and application.

### Authentication & Access Control
- **SSH Host Key Verification**: Strict verification using a managed `known_hosts` file.
- **Key‑Based Preferred**: SSH key auth is preferred; password auth is supported for non‑prod and transitions. Production deployments should use keys only.
- **Least Privilege**: Systemd units run under a dedicated service account with constrained permissions.

### Input Validation & Sanitization
- **AS Number Validation**: RFC‑aligned 32‑bit range with reserved ranges handled.
- **Command Injection Prevention**: Strict validation on policy names and arguments for subprocess calls.
- **Safe File Operations**: Router directory names sanitized; outputs written under controlled base dirs.

### Network Security
- **Encrypted Access**: All device access via SSH; IRR access via native bgpq4.
- **IRR Proxy Support**: SSH tunnel manager enables IRR access in restricted networks.
- **Timeouts**: Connection/command timeouts across SSH, subprocess, and workers.

### Operational Security
- **Audit Logging**: Structured logging across modules; NETCONF events can be emailed.
- **RPKI Guardrail**: Optional validation via VRP cache; fail‑closed and thresholds configurable.
- **Config Hygiene**: Env‑driven configuration with schema validation for key settings.

## Risk Tolerance & Safety Mechanisms

### Autonomous Production Approach
Generate and apply policies automatically where risk is assessed as low and RPKI/safety guardrails pass, with audit notifications for all NETCONF events.

```
AUTONOMOUS WORKFLOW:
┌─────────────────┐    ┌──────────────────────┐    ┌─────────────────┐
│ Otto Generation │───▶│ Guardrails + RPKI    │───▶│ Auto Application│
│ (Automated)     │    │ (Low Risk Only)      │    │ (Email Audited) │
└─────────────────┘    └──────────────────────┘    └─────────────────┘
```

### Three‑Tier Operation Modes
```
OPERATION MODES:
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ User Mode       │    │ System Mode     │    │ Autonomous Mode │
│ (Development)   │    │ (Production)    │    │ (Auto + Audit)  │
│ Local install   │    │ System‑wide     │    │ Low‑risk auto   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Safety Mechanisms
- **Always‑On Guardrails**: Modular checks (e.g., prefix counts, bogons, RPKI) before apply.
- **Risk‑Based Auto‑Apply**: Only low‑risk changes auto‑applied; others require manual approval.
- **Confirmed Commits**: Junos confirmed‑commit with automatic rollback if not confirmed.
- **Email Audit Trail**: Immediate email notifications for connect/preview/commit/rollback.
- **Performance/Health**: Parallel worker health monitors and timeouts across modules.

## Data Flow Diagram

```
                        INPUT SOURCES
                             │
                    ┌────────┼────────┐
                    │                 │
                    ▼                 ▼
            ┌──────────────┐   ┌──────────────┐
            │ Device CSV   │   │ AS Text File │
            │ (Discovery)  │   │ (Direct Gen) │
            └──────┬───────┘   └──────┬───────┘
                   │                  │
                   ▼                  ▼
            ┌──────────────────────────────────┐
            │       OTTO BGP PROCESSING        │
            │                                  │
            │  SSH Collection ──▶ AS Extract  │
            │       │                │         │
            │       ▼                ▼         │
            │  Config Parse  ──▶ bgpq4 Gen    │
            │       │                │         │
            │       ▼                ▼         │
            │  Router Map    ──▶ Policy Files │
            └──────────────┬───────────────────┘
                           │
                           ▼
                    OUTPUT PRODUCTS
                           │
              ┌────────────┼────────────┐
              │                         │
              ▼                         ▼
    ┌─────────────────┐        ┌─────────────────┐
    │ Policy Files    │        │ Reports + YAML  │
    │ • Per‑Router    │        │ • Diffs/Matrix  │
    │ • Per‑AS        │        │ • Discovery Map │
    └─────────────────┘        └─────────────────┘
```

## Known Gaps & Limitations

- **SSH Auth Policy**: The code supports both SSH key and password authentication (via env). Production should use key‑based auth; the previous statement “no password authentication permitted” was overly strict.
- **Path Validation Scope**: Hostname/path sanitization is implemented for router directories, but there is no global “absolute path” validator for all file operations. Outputs are written under managed base dirs.
- **IPv6 Prefix Accounting**: Some guardrails (e.g., prefix counters) match IPv4 patterns and may under‑count IPv6 entries in risk assessments.
- **SMTP Secret Source**: Systemd env templates mention `OTTO_BGP_SMTP_PASSWORD_FILE`, but the code reads `OTTO_BGP_SMTP_PASSWORD`. If a password file is used, an external mechanism must populate the env var.
- **RPKI Data Freshness**: RPKI validation relies on a locally cached VRP JSON; correctness depends on timely updates (a preflight systemd unit is provided). Misconfigured or stale VRP data will degrade or block auto‑apply depending on `fail_closed`.
- **bgpq4 Availability**: Policy generation requires bgpq4 (native or container). Environments without bgpq4 will fail until installed or Docker/Podman is available.
- **Juniper Focus**: NETCONF apply and collectors are Juniper‑specific (PyEZ). Other vendors are out of scope in this version.


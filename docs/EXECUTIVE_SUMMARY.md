# Otto BGP v0.3.2 Executive Summary

## Project Overview

Otto BGP is an autonomous BGP policy generator that replaces manual prefix list management processes. The system discovers BGP configurations from Juniper routers, extracts AS numbers, generates policies using Internet Routing Registry (IRR) data, and provides production-ready autonomous application with comprehensive safety controls and email audit trails.

**Core Value**: Eliminates manual BGP policy maintenance while ensuring network stability through automated discovery and policy generation.

## System Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   COLLECTORS    │    │   PROCESSORS    │    │   GENERATORS    │    │    APPLIERS     │
│                 │    │                 │    │                 │    │                 │
│ • SSH Discovery │───▶│ • AS Extraction │───▶│ • BGPq4 Wrapper │───▶│ • Policy Loader │
│ • Config Parser │    │ • Data Cleaning │    │ • IRR Queries   │    │ • NETCONF (Lab) │
│ • Device Mgmt   │    │ • Validation    │    │ • Proxy Support │    │ • Safety Checks │
└─────────────────┘    └─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │                       │
         ▼                       ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ Router Profiles │    │ AS Number Lists │    │ Policy Files    │    │ Applied Configs │
│ BGP Groups      │    │ Cleaned Data    │    │ Router-Specific │    │ (Autonomous)    │
└─────────────────┘    └─────────────────┘    └─────────────────┘    └─────────────────┘
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
                              │         APPLICATION PHASE         │
                              │      (AUTONOMOUS & MANUAL)        │
                              │                                   │
                              │  Risk Assessment ──▶ Email Audit │
                              │      │                 │          │
                              │      ▼                 ▼          │
                              │  Auto Apply ──▶ NETCONF Events   │
                              └───────────────────────────────────┘
```

## Security Architecture

Otto BGP implements defense-in-depth security with multiple protection layers:

### Authentication & Access Control
- **SSH Key-Based Authentication**: No password authentication permitted
- **Host Key Verification**: Strict verification against known_hosts file
- **Limited User Permissions**: Restricted to BGP policy configuration only

### Input Validation & Sanitization
- **AS Number Validation**: RFC-compliant range checking (0-4294967295)
- **Command Injection Prevention**: Strict input sanitization for shell commands
- **Path Traversal Protection**: Absolute path validation for file operations

### Network Security
- **Encrypted Communications**: All device communication via SSH
- **Proxy Support**: Secure tunneling for restricted network environments
- **Connection Timeouts**: Prevents hanging connections and resource exhaustion

### Operational Security
- **Audit Logging**: Comprehensive logging of all security events
- **Privilege Separation**: Minimal required permissions for each operation
- **Secure Configuration**: Environment variable validation and sanitization

## Risk Tolerance & Safety Mechanisms

### Autonomous Production Approach
**Philosophy**: Generate and apply policies automatically with risk-based decisions and comprehensive audit trails.

```
AUTONOMOUS WORKFLOW:
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ Otto Generation │───▶│ Risk Assessment │───▶│ Auto Application│
│ (Automated)     │    │ (Low Risk Only) │    │ (Email Audited) │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Three-Tier Operation Modes
**Purpose**: Flexible deployment options for different environments and risk tolerance

```
OPERATION MODES:
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ User Mode       │    │ System Mode     │    │ Autonomous Mode │
│ (Development)   │    │ (Production)    │    │ (Auto + Audit)  │
│ Local install   │    │ System-wide     │    │ Risk-based auto │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Safety Mechanisms
- **Risk-Based Decisions**: Only low-risk changes are auto-applied
- **Email Audit Trail**: Complete NETCONF event notifications (success/failure)
- **Confirmed Commits**: Automatic rollback if not confirmed within timeout
- **Safety Validation**: Comprehensive pre-application checks
- **Threshold Monitoring**: Informational limits with notification context

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
            │  Config Parse  ──▶ BGPq4 Query  │
            │       │                │         │
            │       ▼                ▼         │
            │  Router Map    ──▶ Policy Gen   │
            └──────────────┬───────────────────┘
                           │
                           ▼
                    OUTPUT PRODUCTS
                           │
              ┌────────────┼────────────┐
              │                         │
              ▼                         ▼
    ┌─────────────────┐        ┌─────────────────┐
    │ Policy Files    │        │ Config Reports  │
    │ • Per-Router    │        │ • Change Diffs  │
    │ • Per-AS        │        │ • Discovery Log │
    │ • Combined      │        │ • Error Reports │
    └─────────────────┘        └─────────────────┘
```

## Risk Assessment Summary

| Risk Category | Mitigation Strategy | Impact |
|---------------|-------------------|--------|
| **Command Injection** | Input validation, no shell construction | **Eliminated** |
| **SSH MITM** | Strict host key verification | **Eliminated** |
| **Configuration Errors** | Dry run validation, confirmed commits | **Minimized** |
| **Network Outages** | BGP session monitoring, auto-rollback | **Contained** |
| **Data Corruption** | Read-only discovery, separate generation | **Prevented** |

## Deployment Model

**Autonomous Mode**: Production-ready automatic application with risk-based decisions and email audit trail
**System Mode**: Production-grade installation with enhanced safety controls
**User Mode**: Development and testing with local installation and containerized bgpq4

This architecture enables full automation with comprehensive safety controls, providing production-ready autonomous operation while maintaining complete audit trails and risk-based decision making for network stability.
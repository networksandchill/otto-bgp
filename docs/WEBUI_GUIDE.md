# Otto BGP WebUI Guide

This guide documents the Otto BGP WebUI: what it does, how it is configured, and current limitations. It complements the CLI and systemd service documentation.

## Overview
- Technology: FastAPI backend with a static frontend served by the adapter.
- Scope: Device inventory management, configuration import/export, log viewing, basic RPKI status, and service controls (optional).
- Not in scope: Running the policy pipeline from the UI. Use the CLI or systemd timers/services.

## Prerequisites
- Systemd-based host recommended for full functionality (journal integration, service control).
- Config and data directories:
  - `CONFIG_DIR` (default: `/etc/otto-bgp`)
  - `DATA_DIR` (default: `/var/lib/otto-bgp`)
- TLS certificates:
  - Adapter and service use `CONFIG_DIR/tls/cert.pem` and `CONFIG_DIR/tls/key.pem`.

## TLS and Certificates
- The WebUI adapter and the systemd service are unified to use:
  - `CONFIG_DIR/tls/cert.pem`
  - `CONFIG_DIR/tls/key.pem`
- Ensure the directory exists and files are readable by the service user.

## Service Control (Optional)
- Disabled by default. Enable with environment flag:
  - `OTTO_WEBUI_ENABLE_SERVICE_CONTROL=true` in `otto.env`.
- Requires sudoers entries for the service user to run `/usr/bin/systemctl` via `/usr/bin/sudo` non-interactively.
- If not configured, WebUI endpoints will return a friendly error indicating service control is disabled or not permitted.

## Logs and Visibility
- Systemd journal integration:
  - When systemd is present, the Logs page reads `journalctl -o json` for the selected unit.
- File logs:
  - On non-systemd systems, only file logs under `DATA_DIR/logs` are available.
  - Application file logging is enabled via environment/config (see System Admin Guide).

## Device Management
- Backed by `CONFIG_DIR/devices.csv`.
- UI fields: `address`, `hostname`, `role`, `region`.
- Per-device SSH credentials are not managed in the UI. Use global SSH settings or manage extended device columns via CSV manually.

## RPKI Status Panel
- Provides informative, heuristic counts derived from VRP list size; not authoritative validation results.
- Exact validation occurs in the core pipeline/guardrails and may differ from the UI summary.

## What the WebUI Does Not Do
- No endpoint or control to trigger the unified policy pipeline from the UI. Use CLI (`otto-bgp pipeline …`) or systemd timers/services to run.

## Environment Flags (selected)
- `OTTO_WEBUI_ENABLE_SERVICE_CONTROL`: enable service control features (requires sudoers).
- `OTTO_BGP_CONFIG_DIR`, `OTTO_BGP_DATA_DIR`: override config/data directories.

## Known Limitations
- Service control requires systemd and properly configured sudoers; otherwise it is unavailable.
- Log viewing depends on systemd journal for best detail; non-systemd platforms show only file logs.
- RPKI status in the UI is approximate by design.
- Per-device credentials are not editable in the UI.


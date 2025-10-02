# Otto BGP v0.3.2 Router‑Aware Architecture

## Overview

Otto BGP v0.3.x implements a router‑aware architecture that discovers BGP context per router, generates AS policies via bgpq4, and safely applies configuration through NETCONF with always‑on safety guardrails. This document reflects the current codebase and module APIs.

## Core Components

### 1) Models (source of truth)

- RouterProfile: Complete BGP profile carried through the pipeline.
  - Fields: `hostname: str`, `ip_address: str`, `bgp_config: str`, `discovered_as_numbers: Set[int]`, `bgp_groups: Dict[str, List[int]]`, `metadata: Dict`.
- DeviceInfo: Enhanced device identity for collection.
  - Fields: `address: str`, `hostname: str` (required; auto‑generated from IP if omitted), optional `username`, `password`, `port`, `role`, `region`.

References: `otto_bgp/models/__init__.py`

### 2) Discovery

- JuniperSSHCollector: Collects BGP configuration via SSH with strict host‑key policy.
- RouterInspector: Parses BGP config to extract groups and peer ASNs.
  - Key methods: `discover_bgp_groups(config: str) -> Dict[str, List[int]]`, `extract_peer_relationships(config: str) -> Dict[int, str]`, `identify_bgp_version(config: str) -> str`, `inspect_router(profile: RouterProfile) -> DiscoveryResult`, `merge_discovery_results(results) -> Dict`.
- YAMLGenerator: Writes auto‑generated discovery artifacts with history and diffs.
  - Files: `policies/discovered/bgp-mappings.yaml`, `policies/discovered/router-inventory.json`, timestamped `policies/discovered/history/*`, and `diff_report_*.txt` when diffing.

References: `otto_bgp/collectors/juniper_ssh.py`, `otto_bgp/discovery/inspector.py`, `otto_bgp/discovery/yaml_generator.py`

CLI: `otto-bgp discover <devices.csv> --output-dir policies` runs discovery and writes to `policies/discovered/`.

### 3) Policy Generation

- BGPq4Wrapper: Secure wrapper around bgpq4 (native or container) with optional proxy and caching.
  - Validates AS numbers and policy names; builds commands without string interpolation.
  - Methods:
    - `generate_policy_for_as(as_number, policy_name=None, irr_server=None, timeout=None)`
    - `generate_policies_batch(as_numbers, custom_policy_names=None, parallel=True, max_workers=None)`
    - `generate_policies_parallel(...)`
    - `write_policies_to_files(batch_result, output_dir, separate_files=True, combined_filename=...)`
    - `test_bgpq4_connection(test_as=7922)`
  - Features: parallel generation, process‑safe file cache, optional IRR proxy integration.

References: `otto_bgp/generators/bgpq4_wrapper.py`

### 4) Directory Management

- DirectoryManager: Creates and manages output layout for router‑aware outputs (routers/, discovered/, reports/).
  - Creates `policies/routers/{hostname}/AS{number}_policy.txt`, `combined_policies.txt` and `metadata.json` when used by pipelines/components that target router‑scoped output.
  - Also manages `policies/discovered/` and `policies/reports/` folders.

References: `otto_bgp/utils/directories.py`, optional integration via pipeline/combiner utilities.

### 5) Adaptation & Application

- PolicyAdapter: Transforms generated policies into Junos configuration (prefix‑lists and/or policy‑statements) and can build group import chains.
- JuniperPolicyApplier: Applies config via NETCONF/PyEZ with preview, confirmed commits, and rollback.
- UnifiedSafetyManager: Always‑active safety validation (guardrails, syntax checks, prefix limits, impact estimation, signal‑safe rollbacks) with optional autonomous‑mode notifications.

Typical apply flow:
1) Caller reads generated files (e.g., `AS{n}_policy.txt`) and constructs a list of dicts: `{ 'as_number': int, 'content': str }`.
2) `PolicyAdapter.adapt_policies_for_router(hostname, policies, bgp_groups, policy_style)` produces configuration text.
3) `JuniperPolicyApplier.connect_to_router(...)` → `preview_changes([...])` → `apply_with_confirmation(policies, confirm_timeout, comment)`.

References: `otto_bgp/appliers/adapter.py`, `otto_bgp/appliers/juniper_netconf.py`, `otto_bgp/appliers/safety.py`

### 6) IRR Proxy (restricted networks)

- IRRProxyManager: Manages SSH tunnels to IRR servers and rewrites bgpq4 commands to use local endpoints.
  - Health monitoring and auto‑recovery, strict host‑key checking, resource cleanup.
  - `wrap_bgpq4_command(cmd, irr_server=None)` integrates transparently with `BGPq4Wrapper`.

References: `otto_bgp/proxy/irr_tunnel.py` (imported as `otto_bgp.proxy`)

## Data Flow

```
1) Discovery (programmatic):
   devices.csv → DeviceInfo → JuniperSSHCollector → RouterProfile(bgp_config)
                                           ↓
                                   RouterInspector → DiscoveryResult
                                           ↓
                          YAMLGenerator → bgp-mappings.yaml + router-inventory.json

2) Generation:
   Router/AS sets → BGPq4Wrapper.generate_policies_batch → PolicyBatchResult
                                           ↓
                         write_policies_to_files → AS{n}_policy.txt (or combined)

3) Adapt & Apply:
   AS{n}_policy.txt → PolicyAdapter (Junos config)
                                           ↓
   UnifiedSafetyManager.validate_policies_before_apply
                                           ↓
   JuniperPolicyApplier.preview_changes → apply_with_confirmation → NETCONF
```

Notes:
- Discovery artifacts are written to `policies/discovered/` as `bgp-mappings.yaml` and `router-inventory.json` (not `router_mappings.yaml` or `router_inventory.yaml`).
- `JuniperPolicyApplier.load_router_policies(policies_dir)` is available to load `AS*_policy.txt` files into the list-of-dicts structure used by the applier.

## Directory Structure

```
policies/
├── discovered/
│   ├── bgp-mappings.yaml        # Auto-generated mappings (DO NOT EDIT)
│   ├── router-inventory.json    # Router profiles summary
│   ├── diff_report_*.txt        # Human-readable diffs (optional)
│   └── history/                 # Snapshots of previous runs
├── routers/
│   └── {router-hostname}/
│       ├── AS12345_policy.txt   # Generated per-AS policies (when router-scoped output is used)
│       ├── AS67890_policy.txt
│       └── metadata.json
└── reports/
    ├── deployment-matrix.csv    # Deployment matrix (reports module)
    ├── deployment-matrix.json   # JSON matrix (reports module)
    └── deployment-summary.txt   # Human-readable summary (reports module)
```

Related: `otto_bgp/reports/matrix.py` can also emit a text summary alongside CSV/JSON.

## Example Usage

### Collect & Discover
```python
from otto_bgp.collectors.juniper_ssh import JuniperSSHCollector
from otto_bgp.discovery import RouterInspector, YAMLGenerator
from otto_bgp.models import DeviceInfo

collector = JuniperSSHCollector()
devices = [DeviceInfo(address='192.0.2.10', hostname='edge-nyc-1')]

profiles = []
for d in devices:
    cfg = collector.collect_bgp_config(d.address)
    profile = d.to_router_profile()
    profile.bgp_config = cfg
    result = RouterInspector().inspect_router(profile)
    profiles.append(profile)

yaml_gen = YAMLGenerator()
mappings = yaml_gen.generate_mappings(profiles)
yaml_gen.save_with_history(mappings)
```

### Generate Policies
```python
from otto_bgp.generators.bgpq4_wrapper import BGPq4Wrapper

bgpq4 = BGPq4Wrapper()
batch = bgpq4.generate_policies_batch({13335, 15169, 32934})
files = bgpq4.write_policies_to_files(batch, output_dir='policies/routers/edge-nyc-1')
```

### Adapt & Apply (preview + confirmed commit)
```python
from pathlib import Path
from otto_bgp.appliers import JuniperPolicyApplier, PolicyAdapter, UnifiedSafetyManager

# Option A: Load policies from a directory
applier = JuniperPolicyApplier()
policies = applier.load_router_policies(Path('policies/routers/edge-nyc-1'))

# Option B: Manually build [{'as_number', 'content'}] from files (equivalent)
# policies = [
#     { 'as_number': 13335, 'content': open('policies/routers/edge-nyc-1/AS13335_policy.txt').read() }
# ]

# Optional adaptation for custom import/policy chains
adapter = PolicyAdapter()
adapted = adapter.adapt_policies_for_router('edge-nyc-1', policies, bgp_groups={'external-peers': [13335]})

safety = UnifiedSafetyManager()
check = safety.validate_policies_before_apply(policies)
if not check.safe_to_proceed:
    raise RuntimeError('Safety validation failed')

applier.connect_to_router(hostname='192.0.2.10', username='netconf', password='secret')
diff = applier.preview_changes(policies)
result = applier.apply_with_confirmation(policies, confirm_timeout=120, comment='Otto BGP policy update')
```

## Security

- Host keys: Strict SSH host‑key verification with a setup mode for first‑time key collection.
- Command safety: AS numbers validated (0–4294967295) and policy names sanitized; bgpq4 commands constructed as argument lists.
- Guardrails: Always‑active safety checks (bogon detection, prefix thresholds, duplicates, syntax), unified risk assessment, and signal‑safe emergency rollback.
- Process hygiene: Managed subprocesses, tunnel lifecycle management, and cleanup on exit.

## Performance

- Parallelism: Parallel bgpq4 invocation with adaptive worker counts; optional sequential mode.
- Caching: Process‑safe policy cache (and in‑process cache when enabled) reduces repeated bgpq4 calls.
- Reporting: Deployment matrices and summaries to help analyze router/AS distribution.

## Error Handling & Reporting

- Graceful degradation: Collects errors per device/AS and continues where safe.
- Rollback: Confirmed commits with rollback and a rollback checkpoint mechanism.
- Diffing: `YAMLGenerator` emits human‑readable diffs of discovery changes.
- Reports: `reports/matrix.py` generates CSV/JSON/text deployment matrices.

## Known Gaps and Limitations

- Discovery diff customization: `otto-bgp discover --show-diff` now calls `generate_diff_report_from_current()` automatically. For bespoke workflows, load historical snapshots manually and call `generate_diff_report(diff)` with your own diff objects.
- Adapter scope: `PolicyAdapter` and its merge logic are simplified and not a full Junos configuration parser. Validate outputs in a lab before use.
- Vendor support: Discovery, adaptation, and applier paths target Junos. Other vendors are not implemented.
- Reports: The reports module writes `deployment-matrix.csv`, `deployment-matrix.json`, and `deployment-summary.txt`. There is no `generation-log.json` writer in the current codebase.
- IRR proxy: `IRRProxyManager` requires a reachable jump host and valid SSH key/known_hosts. If proxy tunnels cannot be established, bgpq4 runs without proxy.

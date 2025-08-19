# BRANDING.md - Otto BGP Identity & Refactor Plan

## Brand Identity

### The Name: Otto BGP

**Otto** - A play on "auto" (automatic/autonomous), representing the tool's autonomous nature in managing BGP policies. Otto is your automated BGP policy assistant.

**BGP** - The surname, grounding Otto firmly in the Border Gateway Protocol domain.

**Full Title**: Otto BGP - Orchestrated Transit Traffic Optimizer for BGP

### Naming Conventions

| Context | Old Name | New Name |
|---------|----------|----------|
| **CLI Command** | `bgp-toolkit` | `otto-bgp` |
| **Python Package** | `bgp_toolkit` | `otto_bgp` |
| **System User** | `otto.bgp` | `otto.bgp` (unchanged) |
| **Service Name** | `bgp-toolkit.service` | `otto-bgp.service` |
| **Repository** | `bgp_toolkit` | `otto-bgp` (future) |
| **Display Name** | BGP Toolkit | Otto BGP |
| **Informal Reference** | "the toolkit" | "Otto" |

### Usage Examples

**Command Line:**
```bash
# Old
bgp-toolkit policy input.txt -o output.txt

# New  
otto-bgp policy input.txt -o output.txt
```

**In Documentation:**
- "Otto BGP orchestrates BGP policy generation"
- "Let Otto handle your BGP policies"
- "Deploy Otto to automate prefix list management"

**In Conversation:**
- "Otto is running the hourly policy updates"
- "Check if Otto collected all the device data"
- "Otto generated 47 policies last night"

## Refactor Implementation Plan

### Phase 1: Core Functionality Refactor (Priority: HIGH)

#### 1.1 Python Package Rename

**Directory Structure Change:**
```
bgp_toolkit/ → otto_bgp/
```

**Files Requiring Import Updates:**

| File | Import Changes |
|------|----------------|
| `bgp-toolkit` | `from bgp_toolkit.main` → `from otto_bgp.main` |
| `main.py` | All `from bgp_toolkit.*` → `from otto_bgp.*` |
| `collectors/juniper_ssh.py` | `from bgp_toolkit.utils` → `from otto_bgp.utils` |
| `pipeline/workflow.py` | Update all internal imports |
| `scripts/setup_host_keys.py` | Update toolkit imports |
| `utils/logging.py` | `from bgp_toolkit.utils` → `from otto_bgp.utils` |

**Total Files with Imports: 14**

#### 1.2 Executable Rename

**Main Executable:**
```bash
bgp-toolkit → otto-bgp
```

**Update Shebang Documentation:**
```python
#!/usr/bin/env python3
"""
Otto BGP - Executable entry point

Orchestrated Transit Traffic Optimizer for BGP policy generation.
Autonomous BGP policy management replacing legacy manual processes.
"""
```

### Phase 2: System Integration (Priority: HIGH)

#### 2.1 SystemD Service Files

**Service File Rename:**
```
/etc/systemd/system/bgp-toolkit.service → /etc/systemd/system/otto-bgp.service
/etc/systemd/system/bgp-toolkit.timer → /etc/systemd/system/otto-bgp.timer
```

**Service File Content Updates:**
```ini
[Unit]
Description=Otto BGP - Orchestrated Transit Traffic Optimizer
Documentation=file:///opt/otto-bgp/README.md

[Service]
ExecStart=/var/lib/otto-bgp/venv/bin/python /opt/otto-bgp/otto_bgp/main.py
SyslogIdentifier=otto-bgp
```

#### 2.2 Directory Structure

**System Directories:**
```
/opt/bgp-toolkit/ → /opt/otto-bgp/
/var/lib/bgp-toolkit/ → /var/lib/otto-bgp/
/etc/bgp-toolkit/ → /etc/otto-bgp/
```

**Log References:**
```
/var/lib/bgp-toolkit/logs/bgp-toolkit.log → /var/lib/otto-bgp/logs/otto-bgp.log
```

### Phase 3: Documentation Updates (Priority: MEDIUM)

#### 3.1 Primary Documentation Files

| File | References to Update | Priority |
|------|---------------------|----------|
| `README.md` | ~150 references | HIGH |
| `CLAUDE.md` (root) | ~20 references | HIGH |
| `bgp_toolkit/CLAUDE.md` | All module refs | HIGH |
| `SECURITY.md` | Service names | MEDIUM |
| `LICENSE` | Attribution | LOW |

#### 3.2 Module Documentation

**CLAUDE.md Files Requiring Updates:**
- `otto_bgp/CLAUDE.md` - Update module paths
- `collectors/CLAUDE.md` - Update import examples
- `generators/CLAUDE.md` - Update module references
- `processors/CLAUDE.md` - Update paths
- `utils/CLAUDE.md` - Update examples
- `scripts/CLAUDE.md` - Update script references

#### 3.3 Help Text & Messages

**CLI Help Text:**
```python
parser = argparse.ArgumentParser(
    prog='otto-bgp',
    description='Otto BGP - Orchestrated Transit Traffic Optimizer'
)
```

**Log Messages:**
```python
logger.info("Otto BGP pipeline starting")
logger.info("Otto collected data from %d devices", count)
```

### Phase 4: Repository & External (Priority: LOW)

#### 4.1 Repository Changes

**GitHub Repository:**
- Consider rename: `bgp_toolkit` → `otto-bgp`
- Update repository description
- Update clone URLs in documentation

**Git Configuration:**
```bash
git remote set-url origin https://github.com/networksandchill/otto-bgp.git
```

#### 4.2 External References

- Docker/Podman image tags
- CI/CD pipelines
- External documentation
- Blog posts/announcements

## Migration Guide

### For Existing Deployments

#### Step 1: Create Compatibility Symlinks
```bash
# Maintain backward compatibility during transition
ln -s /usr/local/bin/otto-bgp /usr/local/bin/bgp-toolkit
ln -s /opt/otto-bgp /opt/bgp-toolkit
```

#### Step 2: Update SystemD Services
```bash
# Stop old timer
sudo systemctl stop bgp-toolkit.timer
sudo systemctl disable bgp-toolkit.timer

# Install new service files
sudo cp otto-bgp.service /etc/systemd/system/
sudo cp otto-bgp.timer /etc/systemd/system/

# Enable new timer
sudo systemctl daemon-reload
sudo systemctl enable otto-bgp.timer
sudo systemctl start otto-bgp.timer
```

#### Step 3: Update Configuration
```bash
# Copy configuration
sudo cp -r /etc/bgp-toolkit/* /etc/otto-bgp/

# Update paths in config.json
sudo sed -i 's/bgp-toolkit/otto-bgp/g' /etc/otto-bgp/config.json
```

#### Step 4: Verify Operation
```bash
# Test CLI
otto-bgp --version

# Test service
sudo systemctl start otto-bgp.service
sudo journalctl -u otto-bgp.service
```

### Rollback Procedure

If issues arise during migration:

```bash
# Restore old service
sudo systemctl stop otto-bgp.timer
sudo systemctl start bgp-toolkit.timer

# Use compatibility symlinks
# Original bgp-toolkit commands will work via symlinks

# Monitor and fix issues before retry
sudo journalctl -u bgp-toolkit.service -f
```

## Implementation Checklist

### Week 1: Core Changes ✅ COMPLETED
- [x] Rename `bgp_toolkit/` directory to `otto_bgp/`
- [x] Update all Python imports (14 files)
- [x] Rename main executable
- [x] Test basic CLI functionality
- [x] Update __init__.py files

### Week 2: System Integration ✅ COMPLETED
- [x] Create new systemd service files
- [x] Update system directories
- [x] Test service execution
- [x] Verify timer scheduling
- [x] Update log file paths

### Week 3: Documentation ✅ COMPLETED
- [x] Update README.md
- [x] Update all CLAUDE.md files
- [x] Update help text in CLI
- [x] Update log messages
- [x] Update error messages

### Week 4: Finalization
- [ ] Consider repository rename
- [ ] Update external documentation
- [ ] Create migration announcement
- [ ] Test rollback procedures
- [ ] Release Otto BGP v2.0.0

## Brand Guidelines

### Voice & Tone
- **Professional**: "Otto BGP provides enterprise-grade policy automation"
- **Approachable**: "Let Otto handle your BGP policies"
- **Reliable**: "Otto ensures consistent policy deployment"

### Key Messages
1. **Autonomous Operation**: Otto works independently, requiring minimal oversight
2. **Policy Expertise**: Otto generates optimal BGP policies using industry best practices
3. **Production Ready**: Otto is designed for 24/7 operation in service provider networks

### Logo Concepts (Future)
- Consider a friendly robot/assistant icon
- Incorporate BGP/network imagery
- Use professional color scheme (blues/grays)

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1.0 | 2025-08-14 | BGP Toolkit (initial beta) |
| 0.2.0 | 2025-08-15 | Otto BGP (rebranded beta) ✅ COMPLETED |

## Notes

- The `otto.bgp` system user remains unchanged (already perfect for branding)
- Consider gradual rollout: internal testing → pilot deployments → full migration
- Maintain backward compatibility symlinks for 6 months minimum
- Document all changes in CHANGELOG.md for v2.0.0 release
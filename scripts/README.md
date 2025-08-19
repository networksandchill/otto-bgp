# Otto BGP Setup Scripts

This directory contains deployment and setup scripts for Otto BGP. **Both script implementations serve distinct operational purposes and should NOT be consolidated.**

## Host Key Setup Scripts

### Why Two Implementations?

We maintain **two complementary implementations** for SSH host key collection, each serving different operational contexts:

#### 🔧 `setup-host-keys.sh` (Bash Implementation)
**Target Users**: System Administrators, CI/CD Pipelines, Production Deployments

**Use Cases:**
- **Production deployments** where minimal dependencies are critical
- **CI/CD pipelines** in containerized environments
- **Emergency situations** when Python environment is unavailable
- **System administrator workflows** requiring simple, reliable tools

**Advantages:**
- ✅ **Zero dependencies** - Only requires `ssh-keyscan` (standard Unix tool)
- ✅ **Fast execution** - Direct system calls, no interpreter overhead
- ✅ **Container-friendly** - Works in minimal Alpine/scratch containers
- ✅ **Visual feedback** - Color-coded progress for operations teams
- ✅ **User validation** - Checks for expected `otto.bgp` service account

**Usage:**
```bash
# Simple production deployment
./setup-host-keys.sh /path/to/devices.csv /path/to/known_hosts

# Using defaults
./setup-host-keys.sh
```

#### 🐍 `setup_host_keys.py` (Python Implementation)
**Target Users**: Developers, Advanced Operations, Integration Testing

**Use Cases:**
- **Development workflows** with Otto BGP integration
- **Advanced debugging** with verbose logging and verification
- **Audit and compliance** requiring detailed reports
- **Integration testing** with existing Python modules

**Advantages:**
- ✅ **Otto BGP integration** - Reuses existing collector and security modules
- ✅ **Dual collection methods** - ssh-keyscan OR paramiko-based testing
- ✅ **Audit capabilities** - JSON export, fingerprint verification
- ✅ **Advanced error handling** - Structured logging, comprehensive validation
- ✅ **Development features** - `--verify-only`, `--verbose`, structured output

**Usage:**
```bash
# Otto BGP integration
./bgp-toolkit setup-host-keys

# Direct Python execution with options
python3 setup_host_keys.py --devices devices.csv --output known_hosts --verbose

# Verification only
python3 setup_host_keys.py --verify-only --output known_hosts
```

## Operational Decision Matrix

| Context | Use Bash Script | Use Python Script |
|---------|----------------|-------------------|
| **Production Deployment** | ✅ Primary choice | ❌ Unnecessary complexity |
| **CI/CD Pipeline** | ✅ Reliable, fast | ❌ Dependency overhead |
| **Development/Testing** | ⚠️ Limited features | ✅ Full integration |
| **Emergency Recovery** | ✅ Always available | ❌ May be unavailable |
| **Audit/Compliance** | ⚠️ Basic logging | ✅ Comprehensive reports |
| **Integration Testing** | ❌ No toolkit integration | ✅ Uses existing modules |

## Implementation Principles

### ⚠️ **DO NOT CONSOLIDATE** - Both Are Required

**Anti-Pattern**: "Let's just keep one script to reduce maintenance"

**Why This Fails**:
- Loses **operational resilience** (bash works when Python fails)
- Removes **dependency isolation** for production deployments
- Eliminates **user persona optimization** (sysadmin vs developer needs)
- Breaks **container deployment** scenarios with minimal dependencies

### ✅ **Maintenance Strategy**

**Core Logic Synchronization**:
- Keep security patterns identical between implementations
- Ensure both scripts collect the same host key types (ed25519, rsa)
- Maintain consistent timeout and retry behavior
- Validate identical CSV format handling

**Feature Differentiation**:
- Bash: Focus on simplicity, reliability, visual feedback
- Python: Enhance integration, auditing, debugging capabilities

## Script Selection Guide

### 🎯 **Choose Bash Script When:**
- Deploying to production servers
- Running in containerized CI/CD pipelines
- Working in environments with restricted Python installations
- Need maximum reliability with minimal dependencies
- System administrators managing infrastructure

### 🎯 **Choose Python Script When:**
- Integrating with Otto BGP development workflows
- Requiring detailed audit trails and verification reports
- Testing SSH connectivity alongside host key collection
- Need advanced error handling and structured logging
- Developers working with the existing Python codebase

## Directory Structure

```
scripts/
├── README.md                 # This file - architectural decisions
├── setup-host-keys.sh        # Bash implementation (production-focused)
└── setup_host_keys.py        # Python implementation (development-focused)
```

## Security Considerations

**Both scripts implement identical security controls**:
- Host key collection only (no authentication required)
- Timeout protection against hanging connections
- Secure file permissions (600 for known_hosts)
- Validation of CSV input format
- Protection against running in production environments

**Deployment Security**:
- Always validate collected host key fingerprints
- Never run host key collection scripts in production (initial setup only)
- Store known_hosts files with restrictive permissions
- Review any changes to host key files

## Troubleshooting

### Common Issues

**Script Selection Confusion**:
- **Problem**: "Which script should I use?"
- **Solution**: Use the decision matrix above based on your operational context

**Dependency Errors**:
- **Problem**: Python script fails with import errors
- **Solution**: Use bash script for dependency-free operation

**Permission Errors**:
- **Problem**: Cannot write to `/var/lib/otto-bgp/`
- **Solution**: Run as `otto.bgp` user or with appropriate sudo privileges

**Host Key Collection Failures**:
- **Problem**: Some devices fail to respond
- **Solution**: Verify network connectivity, SSH service status, and firewall rules

## Future Enhancements

**Acceptable Improvements**:
- Add more detailed progress reporting to bash script
- Enhance audit capabilities in Python script
- Improve error messages in both implementations

**Forbidden Changes**:
- ❌ Consolidating into single script
- ❌ Adding Python dependencies to bash script
- ❌ Removing user context validation
- ❌ Changing core security behavior

---

**Remember**: These scripts serve different operational contexts. Maintaining both ensures **operational resilience** and **user experience optimization** across diverse deployment scenarios.
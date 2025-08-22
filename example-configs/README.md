# Otto BGP v0.3.0 Configuration Examples

This directory contains example configurations and workflows for Otto BGP v0.3.0 router-aware architecture.

## Configuration Files

### `config.json.example`
Complete configuration example with all v0.3.2 features:
- Router discovery settings
- IRR proxy configuration
- Performance optimization settings
- Security controls
- Logging configuration

### `devices.csv`
Example device inventory with v0.3.0 router-aware format:
- Hostname field for router identification
- Role and region metadata
- Enhanced device information

### `router-bgp-config.txt`
Example BGP configuration that Otto discovers from routers:
- Shows BGP groups and AS relationships
- Demonstrates what Otto extracts automatically
- Explains router-specific policy mapping

## Workflow Examples

For workflow examples, see the documentation:
- `docs/AUTOMATION_GUIDE.md`
- `docs/CLI_REFERENCE.md` 
- `README.md`

## Quick Start

1. **Copy configuration template:**
   ```bash
   sudo cp example-configs/config.json.example /etc/otto-bgp/config.json
   sudo chown otto-bgp:otto-bgp /etc/otto-bgp/config.json
   sudo chmod 640 /etc/otto-bgp/config.json
   ```

2. **Create your device inventory:**
   ```bash
   cp example-configs/devices.csv ./my-devices.csv
   # Edit with your router details
   ```

3. **Run router discovery:**
   ```bash
   otto-bgp discover my-devices.csv --output-dir bgp_output
   ```

4. **Generate policies:**
   ```bash
   otto-bgp policy sample_input.txt --output-dir bgp_output/policies/routers
   ```

5. **Run complete workflow:**
   ```bash
   otto-bgp pipeline my-devices.csv --output-dir results
   ```

## v0.3.0 Features Demonstrated

- ✅ **Router Discovery**: Automatic BGP configuration analysis
- ✅ **Router-Specific Policies**: Per-router policy generation
- ✅ **Parallel Processing**: Multi-threaded operations
- ✅ **Intelligent Caching**: Performance optimization
- ✅ **Security Controls**: Input validation and SSH security
- ✅ **IRR Proxy Support**: Network isolation support
- ✅ **Policy Application**: Automated deployment (lab environments)

## Configuration Notes

### SSH Security
- Always use SSH key-based authentication
- Enable strict host key verification in production
- Use dedicated BGP read-only user accounts

### Performance Settings
- Adjust `parallel_workers` based on system resources
- Enable caching for repeated operations
- Configure appropriate timeouts for network conditions

### IRR Proxy
- Enable for networks requiring external IRR access via proxy
- Configure SSH tunnels for whois.radb.net, whois.ripe.net
- Test connectivity before enabling in production

For complete documentation, see:
- `docs/AUTOMATION_GUIDE.md`
- `docs/ROUTER_ARCHITECTURE.md`
- `README.md`
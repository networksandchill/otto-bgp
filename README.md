# Otto BGP v0.3.2 - Orchestrated Transit Traffic Optimizer

**Automated BGP policy generation and application** with router-aware architecture. Otto autonomously generates Juniper policies from network data and provides configurable automation for policy application, from development to production deployment.

## Key Features

- **Juniper-Tailored**: Purpose-built for Juniper routers with PyEZ-based NETCONF and Junos configuration generation
- **Autonomous Operation**: Production-ready automatic policy application with risk-based decisions and email audit trail
- **Router Discovery**: Automatic network topology understanding and BGP relationship mapping
- **Security-First**: SSH host key verification, command injection prevention, strict input validation
- **Three-Tier Installation**: User mode for development, system mode for production, autonomous mode for hands-off operations
- **Policy Generation**: bgpq4-based prefix-list generation with router-specific targeting
- **Safety Controls**: Comprehensive pre-application validation, confirmation timeouts, and rollback protection

## Quick Install

```bash
# Latest v0.3.2 with unified safety architecture
curl -fsSL https://raw.githubusercontent.com/networksandchill/otto-bgp/main/install.sh | bash

# For production deployment (requires sudo)
curl -fsSL https://raw.githubusercontent.com/networksandchill/otto-bgp/main/install.sh | sudo bash -s -- --system

# For autonomous operation with RPKI validation
curl -O https://raw.githubusercontent.com/networksandchill/otto-bgp/main/install.sh
chmod +x install.sh
sudo ./install.sh --autonomous
```

## Quick Uninstall

```bash
# Complete removal (interactive prompts for confirmation)
curl -fsSL https://raw.githubusercontent.com/networksandchill/otto-bgp/main/uninstall.sh | sudo bash

# Non-interactive removal (requires explicit confirmation)
curl -fsSL https://raw.githubusercontent.com/networksandchill/otto-bgp/main/uninstall.sh | sudo bash -s -- --yes
```

## Basic Usage

```bash
# Test bgpq4 connectivity (flags work before or after subcommand)
otto-bgp policy sample_input.txt --test
otto-bgp --test policy sample_input.txt

# Generate policies for AS numbers in a file
otto-bgp policy input.txt -o policies.txt

# Generate separate files per AS
otto-bgp policy input.txt -s --output-dir ./output
otto-bgp -s policy input.txt --output-dir ./output

# Full pipeline (SSH collection → processing → policy generation)
otto-bgp pipeline devices.csv --output-dir ./results
otto-bgp --output-dir ./results pipeline devices.csv

# Autonomous mode - automatic policy application
otto-bgp apply --autonomous --auto-threshold 100
otto-bgp --autonomous --auto-threshold 100 apply

# SystemD service for scheduled operation
sudo systemctl enable otto-bgp.timer
sudo systemctl start otto-bgp.timer
```

## Documentation

- **[Installation Guide](docs/INSTALLATION_GUIDE.md)** - Complete installation instructions for all modes
- **[CLI Reference](docs/CLI_REFERENCE.md)** - Detailed command reference and options
- **[Automation Guide](docs/AUTOMATION_GUIDE.md)** - Automation workflows and operational modes
- **[Policy Application Guide](docs/POLICY_APPLICATION_GUIDE.md)** - Policy application methods and router discovery
- **[Network Engineering Reference](docs/NETWORK_ENGINEERING_REFERENCE.md)** - Juniper configuration and SSH security

## Prerequisites

- **Linux/macOS** with Python 3.10+
- **bgpq4** for policy generation
- **SSH access** to target Juniper routers
- **Virtual environment** (automatically created by installer)

## Input Format

Otto BGP accepts text files with AS numbers in various formats:

```
AS13335
AS15169
12345
AS64512
```

## Output Format

Generates Juniper policy-options configuration:

```junos
policy-options {
    prefix-list 13335 {
        1.1.1.0/24;
        1.0.0.0/24;
    }
}
```

## Support

- **Help**: Run `otto-bgp --help` or see documentation links above
- **Issues**: Report bugs at [GitHub Issues](https://github.com/networksandchill/otto-bgp/issues)
- **CLI Help**: Use `/help` command for CLI-specific guidance

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with appropriate validation
4. Submit a pull request

For production deployment issues, please include:
- System information (`uname -a`, `python3 --version`)
- Service logs (`journalctl -u otto-bgp.service`)
- Configuration files (sanitized)

## License

This project is licensed under the MIT License - see the LICENSE file for details.
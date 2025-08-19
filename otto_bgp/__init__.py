"""
BGP Toolkit - Production-ready CLI tool for automated BGP prefix list generation.

Refactored from legacy scripts to provide:
- SSH-based BGP peer data collection from Juniper devices
- AS number extraction and text processing
- bgpq3-based policy configuration generation
- Full pipeline automation with systemd service capability
"""

__version__ = "0.3.2"
__author__ = "BGP Toolkit Project"
"""
Otto BGP - Orchestrated Transit Traffic Optimizer for automated BGP prefix list generation.

Provides router-aware BGP policy management with:
- SSH-based BGP peer data collection from Juniper devices
- AS number extraction with RFC-compliant validation
- bgpq4-based policy configuration generation
- NETCONF policy application with always-on safety guardrails
- Full pipeline automation with systemd service capability
"""

__version__ = "0.3.2"
__author__ = "BGP Toolkit Project"

"""
Otto BGP Proxy Module

Provides IRR proxy support for networks behind firewalls or with restricted access
to Internet Routing Registry (IRR) services.

Components:
- IRRProxyManager: SSH tunnel management for IRR access
- ProxyConfig: Configuration management for proxy settings
- TunnelMonitor: Health monitoring for proxy connections
"""

from .irr_tunnel import IRRProxyManager, ProxyConfig, TunnelStatus

__all__ = [
    'IRRProxyManager',
    'ProxyConfig', 
    'TunnelStatus'
]
"""
Otto BGP v0.3.2 Discovery Engine

This module provides auto-discovery of BGP configurations and relationships.
It parses router configurations to extract BGP groups, AS numbers, and peer
relationships, generating auto-maintained YAML mappings.

Key Components:
- RouterInspector: Main discovery interface
- BGPConfigParser: Parses Juniper BGP configurations
- YAMLGenerator: Generates and maintains YAML mappings with history

Principle: "Zero YAML maintenance" - all discovered files are READ-ONLY
and auto-generated. Never manually edit files in policies/discovered/.
"""

from .inspector import RouterInspector
from .parser import BGPConfigParser
from .yaml_generator import YAMLGenerator

__all__ = [
    'RouterInspector',
    'BGPConfigParser',
    'YAMLGenerator'
]

__version__ = '0.3.2'
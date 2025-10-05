"""
Router Inspector - Main discovery interface for BGP configuration analysis

This module provides the core inspection capabilities for discovering BGP
groups, AS numbers, and peer relationships from router configurations.
"""

import re
import logging
from typing import Dict, List, Set
from dataclasses import dataclass, field

from ..models import RouterProfile


@dataclass
class DiscoveryResult:
    """Container for discovery results from a single router."""
    hostname: str
    bgp_groups: Dict[str, List[int]] = field(default_factory=dict)
    peer_relationships: Dict[int, str] = field(default_factory=dict)  # AS -> group name
    bgp_version: str = ""
    total_as_numbers: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class RouterInspector:
    """
    Main discovery interface for analyzing router BGP configurations.

    This class coordinates the discovery process, extracting BGP groups,
    AS numbers, and peer relationships from router configurations.
    """

    def __init__(self):
        """Initialize RouterInspector."""
        self.logger = logging.getLogger(__name__)

        # Pre-compile all regex patterns for performance optimization
        self._compiled_patterns = {
            'group_pattern': re.compile(r'group\s+(\S+)\s*\{'),
            'peer_as_pattern': re.compile(r'peer-as\s+(\d+);'),
            'external_as_pattern': re.compile(r'external-as\s+(\d+);')
        }

    def discover_bgp_groups(self, bgp_config: str) -> Dict[str, List[int]]:
        """
        Discover BGP groups and their associated AS numbers from configuration.

        Args:
            bgp_config: Raw BGP configuration text from router

        Returns:
            Dictionary mapping group names to lists of AS numbers

        Example:
            Input config fragment:
                group external-peers {
                    neighbor 10.0.0.1 {
                        peer-as 65001;
                    }
                    neighbor 10.0.0.2 {
                        peer-as 65002;
                    }
                }

            Returns:
                {"external-peers": [65001, 65002]}
        """
        groups = {}

        # Find all group statements using pre-compiled pattern
        for match in self._compiled_patterns['group_pattern'].finditer(bgp_config):
            group_name = match.group(1)
            start_pos = match.end() - 1  # Position of opening brace

            # Find matching closing brace by counting braces
            group_content = self._extract_block_content(bgp_config, start_pos)

            if group_content:
                # Extract AS numbers from peer-as statements within the group
                as_numbers = self._extract_as_numbers_from_group(group_content)

                if as_numbers:
                    groups[group_name] = sorted(list(as_numbers))
                    self.logger.info(f"Discovered BGP group '{group_name}' with AS numbers: {groups[group_name]}")

        return groups

    def extract_peer_relationships(self, bgp_config: str) -> Dict[int, str]:
        """
        Extract peer AS relationships and their group associations.

        Args:
            bgp_config: Raw BGP configuration text

        Returns:
            Dictionary mapping AS numbers to their group names

        Example:
            Returns: {65001: "external-peers", 65002: "external-peers", 13335: "cdn-peers"}
        """
        relationships = {}

        # Find all group statements using pre-compiled pattern
        for match in self._compiled_patterns['group_pattern'].finditer(bgp_config):
            group_name = match.group(1)
            start_pos = match.end() - 1  # Position of opening brace

            # Find matching closing brace by counting braces
            group_content = self._extract_block_content(bgp_config, start_pos)

            if group_content:
                # Find all peer-as statements using pre-compiled pattern
                for as_match in self._compiled_patterns['peer_as_pattern'].finditer(group_content):
                    as_number = int(as_match.group(1))
                    if self._is_valid_as_number(as_number):
                        relationships[as_number] = group_name

        return relationships

    def identify_bgp_version(self, bgp_config: str) -> str:
        """
        Identify the BGP version/configuration style from the config.

        Args:
            bgp_config: Raw BGP configuration text

        Returns:
            String identifying the BGP version or style (e.g., "junos", "junos-evolved")
        """
        # Look for Juniper-specific patterns
        if "protocols bgp" in bgp_config or "protocol bgp" in bgp_config:
            if "junos:changed" in bgp_config:
                return "junos-evolved"
            return "junos"

        # Could be extended for other vendors
        return "unknown"

    def inspect_router(self, router_profile: RouterProfile) -> DiscoveryResult:
        """
        Perform complete discovery on a router's BGP configuration.

        Args:
            router_profile: RouterProfile with BGP configuration loaded

        Returns:
            DiscoveryResult containing all discovered information
        """
        result = DiscoveryResult(hostname=router_profile.hostname)

        if not router_profile.bgp_config:
            result.errors.append("No BGP configuration available")
            return result

        try:
            # Discover BGP groups
            result.bgp_groups = self.discover_bgp_groups(router_profile.bgp_config)

            # Extract peer relationships
            result.peer_relationships = self.extract_peer_relationships(router_profile.bgp_config)

            # Identify BGP version
            result.bgp_version = self.identify_bgp_version(router_profile.bgp_config)

            # Count total unique AS numbers
            all_as_numbers = set()
            for as_list in result.bgp_groups.values():
                all_as_numbers.update(as_list)
            result.total_as_numbers = len(all_as_numbers)

            # Update router profile with discovered AS numbers
            router_profile.discovered_as_numbers = all_as_numbers
            router_profile.bgp_groups = result.bgp_groups

            self.logger.info(
                "Discovery complete for %s: Found %d groups with %d AS numbers",
                router_profile.hostname,
                len(result.bgp_groups),
                result.total_as_numbers,
            )

        except Exception as e:
            error_msg = f"Discovery failed: {str(e)}"
            result.errors.append(error_msg)
            self.logger.error(f"Error during discovery for {router_profile.hostname}: {e}")

        return result

    def _extract_as_numbers_from_group(self, group_content: str) -> Set[int]:
        """
        Extract AS numbers from within a BGP group configuration.

        Args:
            group_content: Content within a BGP group block

        Returns:
            Set of AS numbers found
        """
        as_numbers = set()

        # Find peer-as statements using pre-compiled pattern
        for match in self._compiled_patterns['peer_as_pattern'].finditer(group_content):
            as_num = int(match.group(1))
            if self._is_valid_as_number(as_num):
                as_numbers.add(as_num)

        # Also look for external-as in Juniper configs using pre-compiled pattern
        for match in self._compiled_patterns['external_as_pattern'].finditer(group_content):
            as_num = int(match.group(1))
            if self._is_valid_as_number(as_num):
                as_numbers.add(as_num)

        return as_numbers

    def _is_valid_as_number(self, as_number: int) -> bool:
        """
        Validate AS number is within valid range.

        Args:
            as_number: AS number to validate

        Returns:
            True if valid AS number
        """
        return 0 <= as_number <= 4294967295

    def _extract_block_content(self, text: str, start_pos: int) -> str:
        """
        Extract content between matching braces starting at start_pos.

        Args:
            text: Full text to extract from
            start_pos: Position of opening brace

        Returns:
            Content between braces (excluding the braces themselves)
        """
        if start_pos >= len(text) or text[start_pos] != '{':
            return ""

        brace_count = 0
        end_pos = start_pos

        for i in range(start_pos, len(text)):
            if text[i] == '{':
                brace_count += 1
            elif text[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_pos = i
                    break

        if end_pos > start_pos:
            return text[start_pos + 1:end_pos]

        return ""

    def merge_discovery_results(self, results: List[DiscoveryResult]) -> Dict:
        """
        Merge discovery results from multiple routers into a unified view.

        Args:
            results: List of DiscoveryResult objects from multiple routers

        Returns:
            Dictionary with merged discovery data
        """
        merged = {
            "total_routers": len(results),
            "total_groups": 0,
            "total_as_numbers": 0,
            "all_groups": {},  # Group name -> list of routers that have it
            "all_as_numbers": {},  # AS number -> list of routers that peer with it
            "group_as_mappings": {},  # Group name -> set of AS numbers across all routers
            "errors": [],
            "warnings": []
        }

        all_as = set()
        all_groups = set()

        for result in results:
            # Collect groups
            for group_name, as_list in result.bgp_groups.items():
                all_groups.add(group_name)

                if group_name not in merged["all_groups"]:
                    merged["all_groups"][group_name] = []
                merged["all_groups"][group_name].append(result.hostname)

                if group_name not in merged["group_as_mappings"]:
                    merged["group_as_mappings"][group_name] = set()
                merged["group_as_mappings"][group_name].update(as_list)

                # Track AS numbers
                for as_num in as_list:
                    all_as.add(as_num)
                    if as_num not in merged["all_as_numbers"]:
                        merged["all_as_numbers"][as_num] = []
                    merged["all_as_numbers"][as_num].append(result.hostname)

            # Collect errors and warnings
            merged["errors"].extend([f"{result.hostname}: {e}" for e in result.errors])
            merged["warnings"].extend([f"{result.hostname}: {w}" for w in result.warnings])

        # Convert sets to sorted lists for JSON serialization
        for group_name in merged["group_as_mappings"]:
            merged["group_as_mappings"][group_name] = sorted(list(merged["group_as_mappings"][group_name]))

        merged["total_groups"] = len(all_groups)
        merged["total_as_numbers"] = len(all_as)

        return merged

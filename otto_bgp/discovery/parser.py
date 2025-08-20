"""
BGP Configuration Parser - Extracts structured data from router configs

This module provides specialized parsing for Juniper BGP configurations,
extracting groups, AS numbers, peer relationships, and other BGP data.
"""

import re
import logging
from typing import Dict, List, Set, Optional, Tuple
from dataclasses import dataclass


@dataclass
class BGPNeighbor:
    """Represents a BGP neighbor configuration."""
    address: str
    peer_as: Optional[int] = None
    group: Optional[str] = None
    description: Optional[str] = None
    import_policy: List[str] = None
    export_policy: List[str] = None
    
    def __post_init__(self):
        if self.import_policy is None:
            self.import_policy = []
        if self.export_policy is None:
            self.export_policy = []


@dataclass
class BGPGroup:
    """Represents a BGP group configuration."""
    name: str
    type: str = ""  # internal, external
    neighbors: List[BGPNeighbor] = None
    peer_as_list: List[int] = None
    import_policy: List[str] = None
    export_policy: List[str] = None
    
    def __post_init__(self):
        if self.neighbors is None:
            self.neighbors = []
        if self.peer_as_list is None:
            self.peer_as_list = []
        if self.import_policy is None:
            self.import_policy = []
        if self.export_policy is None:
            self.export_policy = []


class BGPConfigParser:
    """
    Parser for Juniper BGP configurations.
    
    Extracts structured data from raw BGP configuration text, including:
    - BGP groups and their properties
    - Neighbor configurations
    - AS numbers and peer relationships
    - Import/export policies
    """
    
    def __init__(self):
        """Initialize BGPConfigParser."""
        self.logger = logging.getLogger(__name__)
        
        # Pre-compile all regex patterns for performance optimization
        self._compiled_patterns = {
            # Group and neighbor patterns
            'group_pattern': re.compile(r'group\s+(\S+)\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}', re.DOTALL),
            'neighbor_pattern': re.compile(r'neighbor\s+(\S+)\s*\{([^}]*)\}'),
            
            # Configuration element patterns
            'type_pattern': re.compile(r'type\s+(\S+);'),
            'import_pattern': re.compile(r'import\s+\[\s*([^\]]+)\s*\];'),
            'export_pattern': re.compile(r'export\s+\[\s*([^\]]+)\s*\];'),
            'peer_as_pattern': re.compile(r'peer-as\s+(\d+);'),
            'external_as_pattern': re.compile(r'(?:peer-as|external-as)\s+(\d+);'),
            'description_pattern': re.compile(r'description\s+"([^"]+)";'),
            
            # AS number extraction patterns
            'local_as_pattern': re.compile(r'autonomous-system\s+(\d+);'),
            'local_as_alt_pattern': re.compile(r'local-as\s+(\d+);'),
            'as_path_prepend_pattern': re.compile(r'as-path-prepend\s+"(\d+(?:\s+\d+)*)"'),
            
            # Address family patterns
            'family_inet_pattern': re.compile(r'family\s+inet\s*\{'),
            'family_inet6_pattern': re.compile(r'family\s+inet6\s*\{'),
            'ipv6_address_pattern': re.compile(r'[0-9a-fA-F]{1,4}:[0-9a-fA-F]{1,4}')
        }
    
    def parse_config(self, config: str) -> Dict:
        """
        Parse complete BGP configuration.
        
        Args:
            config: Raw BGP configuration text
            
        Returns:
            Dictionary containing parsed BGP data
        """
        result = {
            "groups": {},
            "as_numbers": set(),
            "neighbors": [],
            "policies": set(),
            "local_as": None
        }
        
        # Extract local AS if present
        local_as = self._extract_local_as(config)
        if local_as:
            result["local_as"] = local_as
        
        # Parse BGP groups
        groups = self.parse_bgp_groups(config)
        result["groups"] = {g.name: g for g in groups}
        
        # Collect all AS numbers
        for group in groups:
            result["as_numbers"].update(group.peer_as_list)
            for neighbor in group.neighbors:
                if neighbor.peer_as:
                    result["as_numbers"].add(neighbor.peer_as)
        
        # Collect all neighbors
        for group in groups:
            result["neighbors"].extend(group.neighbors)
        
        # Collect all policies
        for group in groups:
            result["policies"].update(group.import_policy)
            result["policies"].update(group.export_policy)
        
        # Convert sets to sorted lists for consistency
        result["as_numbers"] = sorted(list(result["as_numbers"]))
        result["policies"] = sorted(list(result["policies"]))
        
        return result
    
    def parse_bgp_groups(self, config: str) -> List[BGPGroup]:
        """
        Parse all BGP groups from configuration.
        
        Args:
            config: Raw BGP configuration text
            
        Returns:
            List of BGPGroup objects
        """
        groups = []
        
        # Pattern to match BGP groups with nested content
        # This handles both single-line and multi-line group definitions
        # Use pre-compiled pattern for BGP groups
        for match in self._compiled_patterns['group_pattern'].finditer(config):
            group_name = match.group(1)
            group_content = match.group(2)
            
            group = self._parse_single_group(group_name, group_content)
            groups.append(group)
            
            self.logger.debug(f"Parsed BGP group '{group_name}' with {len(group.neighbors)} neighbors")
        
        return groups
    
    def _parse_single_group(self, name: str, content: str) -> BGPGroup:
        """
        Parse a single BGP group.
        
        Args:
            name: Group name
            content: Group configuration content
            
        Returns:
            BGPGroup object
        """
        group = BGPGroup(name=name)
        
        # Extract group type using pre-compiled pattern
        type_match = self._compiled_patterns['type_pattern'].search(content)
        if type_match:
            group.type = type_match.group(1)
        
        # Extract import policies using pre-compiled pattern
        import_matches = self._compiled_patterns['import_pattern'].findall(content)
        for match in import_matches:
            policies = [p.strip() for p in match.split()]
            group.import_policy.extend(policies)
        
        # Extract export policies using pre-compiled pattern
        export_matches = self._compiled_patterns['export_pattern'].findall(content)
        for match in export_matches:
            policies = [p.strip() for p in match.split()]
            group.export_policy.extend(policies)
        
        # Parse neighbors
        neighbors = self._parse_neighbors(content, group.name)
        group.neighbors = neighbors
        
        # Collect peer AS numbers
        peer_as_set = set()
        for neighbor in neighbors:
            if neighbor.peer_as:
                peer_as_set.add(neighbor.peer_as)
        
        # Also check for group-level peer-as using pre-compiled pattern
        group_peer_as = self._compiled_patterns['external_as_pattern'].search(content)
        if group_peer_as:
            as_num = int(group_peer_as.group(1))
            if self._is_valid_as_number(as_num):
                peer_as_set.add(as_num)
        
        group.peer_as_list = sorted(list(peer_as_set))
        
        return group
    
    def _parse_neighbors(self, content: str, group_name: str) -> List[BGPNeighbor]:
        """
        Parse neighbor configurations from group content.
        
        Args:
            content: Group configuration content
            group_name: Name of the parent group
            
        Returns:
            List of BGPNeighbor objects
        """
        neighbors = []
        
        # Use pre-compiled pattern to match neighbor blocks
        for match in self._compiled_patterns['neighbor_pattern'].finditer(content):
            address = match.group(1)
            neighbor_content = match.group(2)
            
            neighbor = BGPNeighbor(address=address, group=group_name)
            
            # Extract peer AS using pre-compiled pattern
            peer_as_match = self._compiled_patterns['peer_as_pattern'].search(neighbor_content)
            if peer_as_match:
                as_num = int(peer_as_match.group(1))
                if self._is_valid_as_number(as_num):
                    neighbor.peer_as = as_num
            
            # Extract description using pre-compiled pattern
            desc_match = self._compiled_patterns['description_pattern'].search(neighbor_content)
            if desc_match:
                neighbor.description = desc_match.group(1)
            
            # Extract import policies using pre-compiled pattern
            import_match = self._compiled_patterns['import_pattern'].search(neighbor_content)
            if import_match:
                neighbor.import_policy = [p.strip() for p in import_match.group(1).split()]
            
            # Extract export policies using pre-compiled pattern
            export_match = self._compiled_patterns['export_pattern'].search(neighbor_content)
            if export_match:
                neighbor.export_policy = [p.strip() for p in export_match.group(1).split()]
            
            neighbors.append(neighbor)
        
        return neighbors
    
    def _extract_local_as(self, config: str) -> Optional[int]:
        """
        Extract local AS number from configuration.
        
        Args:
            config: Raw BGP configuration
            
        Returns:
            Local AS number if found, None otherwise
        """
        # Look for autonomous-system statement using pre-compiled pattern
        as_match = self._compiled_patterns['local_as_pattern'].search(config)
        if as_match:
            as_num = int(as_match.group(1))
            if self._is_valid_as_number(as_num):
                return as_num
        
        # Alternative pattern for local-as using pre-compiled pattern
        local_as_match = self._compiled_patterns['local_as_alt_pattern'].search(config)
        if local_as_match:
            as_num = int(local_as_match.group(1))
            if self._is_valid_as_number(as_num):
                return as_num
        
        return None
    
    def extract_as_numbers(self, config: str) -> Set[int]:
        """
        Extract all AS numbers from configuration.
        
        Args:
            config: Raw BGP configuration
            
        Returns:
            Set of all AS numbers found
        """
        as_numbers = set()
        
        # Extract AS numbers using pre-compiled patterns
        # Single AS number patterns
        single_as_patterns = [
            self._compiled_patterns['peer_as_pattern'],
            self._compiled_patterns['external_as_pattern'], 
            self._compiled_patterns['local_as_alt_pattern'],
            self._compiled_patterns['local_as_pattern']
        ]
        
        for pattern in single_as_patterns:
            for match in pattern.finditer(config):
                as_num = int(match.group(1))
                if self._is_valid_as_number(as_num):
                    as_numbers.add(as_num)
        
        # AS path prepend can have multiple AS numbers
        for match in self._compiled_patterns['as_path_prepend_pattern'].finditer(config):
            as_nums = match.group(1).split()
            for as_str in as_nums:
                as_num = int(as_str)
                if self._is_valid_as_number(as_num):
                    as_numbers.add(as_num)
        
        return as_numbers
    
    def extract_policies(self, config: str) -> Dict[str, List[str]]:
        """
        Extract import/export policies from configuration.
        
        Args:
            config: Raw BGP configuration
            
        Returns:
            Dictionary with 'import' and 'export' keys containing policy names
        """
        policies = {
            "import": [],
            "export": []
        }
        
        # Extract import policies using pre-compiled pattern
        import_matches = self._compiled_patterns['import_pattern'].findall(config)
        for match in import_matches:
            policy_names = [p.strip() for p in match.split()]
            policies["import"].extend(policy_names)
        
        # Extract export policies using pre-compiled pattern
        export_matches = self._compiled_patterns['export_pattern'].findall(config)
        for match in export_matches:
            policy_names = [p.strip() for p in match.split()]
            policies["export"].extend(policy_names)
        
        # Remove duplicates while preserving order
        policies["import"] = list(dict.fromkeys(policies["import"]))
        policies["export"] = list(dict.fromkeys(policies["export"]))
        
        return policies
    
    def _is_valid_as_number(self, as_number: int) -> bool:
        """
        Validate AS number is within valid range.
        
        Args:
            as_number: AS number to validate
            
        Returns:
            True if valid AS number
        """
        return 0 <= as_number <= 4294967295
    
    def identify_address_families(self, config: str) -> List[str]:
        """
        Identify configured address families (IPv4, IPv6).
        
        Args:
            config: Raw BGP configuration
            
        Returns:
            List of address families found (e.g., ["inet", "inet6"])
        """
        families = []
        
        # Look for family statements using pre-compiled patterns
        if self._compiled_patterns['family_inet_pattern'].search(config):
            families.append("inet")
        
        if self._compiled_patterns['family_inet6_pattern'].search(config):
            families.append("inet6")
        
        # If no explicit family, check for IPv6 addresses
        if not families:
            # Simple check for IPv6 address pattern using pre-compiled pattern
            if self._compiled_patterns['ipv6_address_pattern'].search(config):
                families.append("inet6")
            else:
                families.append("inet")  # Default to IPv4
        
        return families
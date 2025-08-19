"""
Policy Combiner - Merge multiple BGP policies for a single router

This module combines individual AS policies into a unified configuration
file that can be applied to a router. It handles proper formatting,
deduplication, and sectioning of Juniper policy configurations.
"""

import logging
from pathlib import Path
from typing import List, Dict, Optional, Set
from dataclasses import dataclass
from datetime import datetime


@dataclass
class CombinedPolicyResult:
    """Result of policy combination operation"""
    router_hostname: str
    policies_combined: int
    output_file: str
    success: bool
    total_prefixes: int = 0
    error_message: Optional[str] = None


class PolicyCombiner:
    """
    Combine multiple BGP policies into router-specific configuration files
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize policy combiner
        
        Args:
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
        
    def combine_policies_for_router(self, 
                                   router_hostname: str,
                                   policy_files: List[Path],
                                   output_dir: Path,
                                   format: str = "juniper") -> CombinedPolicyResult:
        """
        Combine multiple policy files for a single router
        
        Args:
            router_hostname: Hostname of the router
            policy_files: List of policy file paths to combine
            output_dir: Directory to save combined policy
            format: Output format (juniper, set, hierarchical)
            
        Returns:
            CombinedPolicyResult with operation details
        """
        try:
            self.logger.info(f"Combining {len(policy_files)} policies for {router_hostname}")
            
            if not policy_files:
                return CombinedPolicyResult(
                    router_hostname=router_hostname,
                    policies_combined=0,
                    output_file="",
                    success=False,
                    error_message="No policy files provided"
                )
            
            # Read all policy files
            policies = []
            for policy_file in policy_files:
                if policy_file.exists():
                    content = policy_file.read_text()
                    as_number = self._extract_as_number_from_filename(policy_file.name)
                    policies.append({
                        "as_number": as_number,
                        "content": content,
                        "file": policy_file.name
                    })
                else:
                    self.logger.warning(f"Policy file not found: {policy_file}")
            
            if not policies:
                return CombinedPolicyResult(
                    router_hostname=router_hostname,
                    policies_combined=0,
                    output_file="",
                    success=False,
                    error_message="No valid policy files found"
                )
            
            # Generate combined policy based on format
            if format == "juniper":
                combined_content = self._combine_juniper_format(router_hostname, policies)
            elif format == "set":
                combined_content = self._combine_set_format(router_hostname, policies)
            elif format == "hierarchical":
                combined_content = self._combine_hierarchical_format(router_hostname, policies)
            else:
                raise ValueError(f"Unsupported format: {format}")
            
            # Count total prefixes
            total_prefixes = combined_content.count("prefix")
            
            # Save combined policy
            output_file = output_dir / f"{router_hostname}_combined_policy.txt"
            output_file.write_text(combined_content)
            
            self.logger.info(f"Combined policy saved to {output_file}")
            
            return CombinedPolicyResult(
                router_hostname=router_hostname,
                policies_combined=len(policies),
                output_file=str(output_file),
                success=True,
                total_prefixes=total_prefixes
            )
            
        except Exception as e:
            self.logger.error(f"Failed to combine policies for {router_hostname}: {e}")
            return CombinedPolicyResult(
                router_hostname=router_hostname,
                policies_combined=0,
                output_file="",
                success=False,
                error_message=str(e)
            )
    
    def _combine_juniper_format(self, router_hostname: str, policies: List[Dict]) -> str:
        """
        Combine policies in Juniper hierarchical format
        
        Args:
            router_hostname: Router hostname for header
            policies: List of policy dictionaries
            
        Returns:
            Combined policy configuration
        """
        lines = []
        
        # Header
        lines.append(f"/* Combined BGP policies for {router_hostname} */")
        lines.append(f"/* Generated: {datetime.now().isoformat()} */")
        lines.append(f"/* Total policies: {len(policies)} */")
        lines.append("")
        
        # Main policy-options block
        lines.append("policy-options {")
        
        # Process each policy
        prefix_lists = {}
        for policy in policies:
            as_number = policy["as_number"]
            content = policy["content"]
            
            # Extract prefix-list content
            prefix_list = self._extract_prefix_list(content)
            if prefix_list:
                list_name = prefix_list.get("name", f"AS{as_number}")
                if list_name not in prefix_lists:
                    prefix_lists[list_name] = {
                        "as_number": as_number,
                        "prefixes": []
                    }
                prefix_lists[list_name]["prefixes"].extend(prefix_list.get("prefixes", []))
        
        # Write deduplicated prefix lists
        for list_name, data in prefix_lists.items():
            lines.append(f"    /* AS{data['as_number']} */")
            lines.append(f"    prefix-list {list_name} {{")
            
            # Deduplicate prefixes
            unique_prefixes = sorted(set(data["prefixes"]))
            for prefix in unique_prefixes:
                lines.append(f"        {prefix};")
            
            lines.append("    }")
            lines.append("")
        
        # Close policy-options
        lines.append("}")
        
        return "\n".join(lines)
    
    def _combine_set_format(self, router_hostname: str, policies: List[Dict]) -> str:
        """
        Combine policies in Juniper set command format
        
        Args:
            router_hostname: Router hostname for header
            policies: List of policy dictionaries
            
        Returns:
            Combined policy as set commands
        """
        lines = []
        
        # Header
        lines.append(f"# Combined BGP policies for {router_hostname}")
        lines.append(f"# Generated: {datetime.now().isoformat()}")
        lines.append(f"# Total policies: {len(policies)}")
        lines.append("")
        
        # Process each policy
        seen_commands = set()
        for policy in policies:
            as_number = policy["as_number"]
            content = policy["content"]
            
            lines.append(f"# AS{as_number}")
            
            # Convert to set commands
            set_commands = self._convert_to_set_commands(content)
            for cmd in set_commands:
                if cmd not in seen_commands:
                    lines.append(cmd)
                    seen_commands.add(cmd)
            
            lines.append("")
        
        return "\n".join(lines)
    
    def _combine_hierarchical_format(self, router_hostname: str, policies: List[Dict]) -> str:
        """
        Combine policies with clear hierarchical organization
        
        Args:
            router_hostname: Router hostname for header
            policies: List of policy dictionaries
            
        Returns:
            Hierarchically organized combined policy
        """
        lines = []
        
        # Header
        lines.append("/*")
        lines.append(f" * BGP Policy Configuration")
        lines.append(f" * Router: {router_hostname}")
        lines.append(f" * Generated: {datetime.now().isoformat()}")
        lines.append(f" * Policies: {len(policies)}")
        lines.append(" */")
        lines.append("")
        
        # Group policies by type
        transit_policies = []
        customer_policies = []
        cdn_policies = []
        
        for policy in policies:
            as_number = policy["as_number"]
            # Categorize based on AS number ranges (example logic)
            if 13000 <= as_number <= 14000:
                cdn_policies.append(policy)
            elif as_number >= 64512:
                customer_policies.append(policy)
            else:
                transit_policies.append(policy)
        
        lines.append("policy-options {")
        
        # Transit providers section
        if transit_policies:
            lines.append("    /* TRANSIT PROVIDERS */")
            for policy in transit_policies:
                lines.extend(self._format_policy_section(policy, indent=1))
        
        # CDN providers section
        if cdn_policies:
            lines.append("    /* CDN PROVIDERS */")
            for policy in cdn_policies:
                lines.extend(self._format_policy_section(policy, indent=1))
        
        # Customer section
        if customer_policies:
            lines.append("    /* CUSTOMERS */")
            for policy in customer_policies:
                lines.extend(self._format_policy_section(policy, indent=1))
        
        lines.append("}")
        
        return "\n".join(lines)
    
    def _extract_prefix_list(self, policy_content: str) -> Optional[Dict]:
        """
        Extract prefix-list information from policy content
        
        Args:
            policy_content: Raw policy configuration
            
        Returns:
            Dictionary with prefix-list name and prefixes
        """
        import re
        
        # Find prefix-list block
        list_match = re.search(r'prefix-list\s+(\S+)\s*{([^}]*)}', policy_content, re.DOTALL)
        if not list_match:
            return None
        
        list_name = list_match.group(1)
        list_content = list_match.group(2)
        
        # Extract prefixes
        prefixes = re.findall(r'(\d+\.\d+\.\d+\.\d+/\d+)', list_content)
        
        return {
            "name": list_name,
            "prefixes": prefixes
        }
    
    def _extract_as_number_from_filename(self, filename: str) -> int:
        """
        Extract AS number from policy filename
        
        Args:
            filename: Policy filename (e.g., "AS65001_policy.txt")
            
        Returns:
            AS number or 0 if not found
        """
        import re
        
        match = re.search(r'AS(\d+)', filename)
        if match:
            return int(match.group(1))
        return 0
    
    def _convert_to_set_commands(self, policy_content: str) -> List[str]:
        """
        Convert hierarchical policy to set commands
        
        Args:
            policy_content: Hierarchical policy configuration
            
        Returns:
            List of set commands
        """
        import re
        
        commands = []
        
        # Extract prefix-list entries
        list_match = re.search(r'prefix-list\s+(\S+)\s*{([^}]*)}', policy_content, re.DOTALL)
        if list_match:
            list_name = list_match.group(1)
            list_content = list_match.group(2)
            
            prefixes = re.findall(r'(\d+\.\d+\.\d+\.\d+/\d+)', list_content)
            for prefix in prefixes:
                commands.append(f"set policy-options prefix-list {list_name} {prefix}")
        
        return commands
    
    def _format_policy_section(self, policy: Dict, indent: int = 0) -> List[str]:
        """
        Format a policy section with proper indentation
        
        Args:
            policy: Policy dictionary
            indent: Indentation level
            
        Returns:
            List of formatted lines
        """
        lines = []
        indent_str = "    " * indent
        
        as_number = policy["as_number"]
        content = policy["content"]
        
        # Extract and format prefix-list
        prefix_list = self._extract_prefix_list(content)
        if prefix_list:
            lines.append(f"{indent_str}prefix-list AS{as_number} {{")
            for prefix in prefix_list["prefixes"]:
                lines.append(f"{indent_str}    {prefix};")
            lines.append(f"{indent_str}}}")
            lines.append("")
        
        return lines
    
    def merge_policy_directories(self, 
                                router_dirs: List[Path],
                                output_dir: Path,
                                format: str = "juniper") -> List[CombinedPolicyResult]:
        """
        Merge policies from multiple router directories
        
        Args:
            router_dirs: List of router directories containing policies
            output_dir: Output directory for combined policies
            format: Output format
            
        Returns:
            List of CombinedPolicyResult for each router
        """
        results = []
        
        for router_dir in router_dirs:
            if not router_dir.exists():
                self.logger.warning(f"Router directory not found: {router_dir}")
                continue
            
            # Get router hostname from directory name
            router_hostname = router_dir.name
            
            # Find all policy files in directory
            policy_files = list(router_dir.glob("AS*_policy.txt"))
            
            if policy_files:
                result = self.combine_policies_for_router(
                    router_hostname=router_hostname,
                    policy_files=policy_files,
                    output_dir=output_dir,
                    format=format
                )
                results.append(result)
            else:
                self.logger.warning(f"No policy files found in {router_dir}")
        
        return results
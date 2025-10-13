"""
Policy Adaptation Layer - Transform Policies for Router Application

Adapts generated BGP policies to specific router contexts including:
- BGP group assignment
- Policy-statement creation
- Prefix-list integration
- Import/export policy chains
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class AdaptationResult:
    """Result of policy adaptation"""

    success: bool
    router_hostname: str
    policies_adapted: int
    bgp_groups_configured: Dict[str, List[int]]  # group -> AS numbers
    configuration: Optional[str] = None
    error_message: Optional[str] = None


class PolicyAdapter:
    """
    Adapt BGP policies for specific router contexts

    Handles transformation of raw BGP policies into router-specific
    configurations that integrate with existing BGP groups and policies.
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize policy adapter

        Args:
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger(__name__)

    def adapt_policies_for_router(
        self,
        router_hostname: str,
        policies: List[Dict[str, str]],
        bgp_groups: Dict[str, List[int]],
        policy_style: str = "prefix-list",
    ) -> AdaptationResult:
        """
        Adapt policies for specific router and BGP groups

        Args:
            router_hostname: Target router hostname
            policies: List of policy dictionaries
            bgp_groups: Mapping of BGP group names to AS numbers
            policy_style: Style of policy (prefix-list, policy-statement)

        Returns:
            AdaptationResult with adapted configuration
        """
        self.logger.info(f"Adapting {len(policies)} policies for {router_hostname}")

        try:
            if policy_style == "prefix-list":
                config = self._generate_prefix_list_config(policies, bgp_groups)
            elif policy_style == "policy-statement":
                config = self._generate_policy_statement_config(policies, bgp_groups)
            else:
                raise ValueError(f"Unsupported policy style: {policy_style}")

            # Count adapted policies per group
            groups_configured = {}
            for group_name, as_numbers in bgp_groups.items():
                groups_configured[group_name] = as_numbers

            result = AdaptationResult(
                success=True,
                router_hostname=router_hostname,
                policies_adapted=len(policies),
                bgp_groups_configured=groups_configured,
                configuration=config,
            )

            groups_count = len(bgp_groups)
            self.logger.info(
                f"Successfully adapted policies for {groups_count} BGP groups"
            )
            return result

        except Exception as e:
            self.logger.error(f"Policy adaptation failed: {e}")
            return AdaptationResult(
                success=False,
                router_hostname=router_hostname,
                policies_adapted=0,
                bgp_groups_configured={},
                error_message=str(e),
            )

    def _generate_prefix_list_config(
        self, policies: List[Dict[str, str]], bgp_groups: Dict[str, List[int]]
    ) -> str:
        """
        Generate prefix-list based configuration

        Args:
            policies: List of policies
            bgp_groups: BGP group mappings

        Returns:
            Configuration string
        """
        lines = []

        # Generate prefix-lists
        lines.append("policy-options {")

        for policy in policies:
            content = policy.get("content", "")

            # Extract prefix-list content
            import re

            pattern = r"prefix-list\s+(\S+)\s*{([^}]*)}"
            match = re.search(pattern, content, re.DOTALL)
            if match:
                list_name = match.group(1)
                list_content = match.group(2)

                lines.append(f"    prefix-list {list_name} {{")
                for line in list_content.strip().split("\n"):
                    if line.strip():
                        lines.append(f"        {line.strip()}")
                lines.append("    }")

        lines.append("}")

        # Generate BGP group assignments
        lines.append("")
        lines.append("protocols {")
        lines.append("    bgp {")

        for group_name, as_numbers in bgp_groups.items():
            lines.append(f"        group {group_name} {{")

            # Add import policies for AS numbers in this group
            import_policies = []
            for as_num in as_numbers:
                # Check if we have a policy for this AS
                if any(p.get("as_number") == as_num for p in policies):
                    import_policies.append(f"AS{as_num}")

            if import_policies:
                policy_list = " ".join(import_policies)
                lines.append(f"            import [ {policy_list} ];")

            lines.append("        }")

        lines.append("    }")
        lines.append("}")

        return "\n".join(lines)

    def _generate_policy_statement_config(
        self, policies: List[Dict[str, str]], bgp_groups: Dict[str, List[int]]
    ) -> str:
        """
        Generate policy-statement based configuration

        Args:
            policies: List of policies
            bgp_groups: BGP group mappings

        Returns:
            Configuration string
        """
        lines = []

        lines.append("policy-options {")

        # First, create prefix-lists
        for policy in policies:
            content = policy.get("content", "")

            # Extract prefix-list
            import re

            pattern = r"prefix-list\s+(\S+)\s*{([^}]*)}"
            match = re.search(pattern, content, re.DOTALL)
            if match:
                list_name = match.group(1)
                list_content = match.group(2)

                lines.append(f"    prefix-list {list_name} {{")
                for line in list_content.strip().split("\n"):
                    if line.strip():
                        lines.append(f"        {line.strip()}")
                lines.append("    }")

        # Create policy-statements
        for policy in policies:
            as_number = policy.get("as_number", 0)

            lines.append(f"    policy-statement IMPORT-AS{as_number} {{")
            lines.append("        term accept-prefixes {")
            lines.append("            from {")
            lines.append(f"                prefix-list AS{as_number};")
            lines.append("            }")
            lines.append("            then accept;")
            lines.append("        }")
            lines.append("        term reject-others {")
            lines.append("            then reject;")
            lines.append("        }")
            lines.append("    }")

        lines.append("}")

        return "\n".join(lines)

    def create_bgp_import_chain(
        self,
        group_name: str,
        as_numbers: List[int],
        existing_policies: List[str] = None,
    ) -> str:
        """
        Create BGP import policy chain for a group

        Args:
            group_name: BGP group name
            as_numbers: AS numbers to include
            existing_policies: Existing policies to preserve

        Returns:
            Configuration snippet for import chain
        """
        policies = existing_policies or []

        # Add AS-specific policies
        for as_num in as_numbers:
            policy_name = f"IMPORT-AS{as_num}"
            if policy_name not in policies:
                policies.append(policy_name)

        # Generate configuration
        if policies:
            return f"import [ {' '.join(policies)} ];"
        return ""

    def validate_adapted_config(self, configuration: str) -> List[str]:
        """
        Validate adapted configuration for common issues

        Args:
            configuration: Configuration to validate

        Returns:
            List of validation warnings/errors
        """
        issues = []

        # Check for empty prefix-lists
        import re

        empty_pattern = r"prefix-list\s+(\S+)\s*{\s*}"
        prefix_lists = re.findall(empty_pattern, configuration)
        for empty_list in prefix_lists:
            issues.append(f"Empty prefix-list: {empty_list}")

        # Check for duplicate prefix-lists
        all_lists = re.findall(r"prefix-list\s+(\S+)", configuration)
        duplicates = [pl for pl in set(all_lists) if all_lists.count(pl) > 1]
        for dup in duplicates:
            issues.append(f"Duplicate prefix-list definition: {dup}")

        # Check for missing policy-statements referenced in import
        imports = re.findall(r"import\s+\[([^\]]+)\]", configuration)
        for import_line in imports:
            policies = import_line.split()
            for policy in policies:
                if f"policy-statement {policy}" not in configuration:
                    # Only warn if it looks like an AS policy
                    is_as_policy = policy.startswith("AS") or policy.startswith(
                        "IMPORT-AS"
                    )
                    if is_as_policy:
                        msg = f"Referenced policy not defined: {policy}"
                        issues.append(msg)

        return issues

    def merge_with_existing(
        self, new_config: str, existing_config: str, merge_strategy: str = "replace"
    ) -> str:
        """
        Merge new configuration with existing router config

        Args:
            new_config: New configuration to apply
            existing_config: Existing router configuration
            merge_strategy: How to merge (replace, append, smart)

        Returns:
            Merged configuration
        """
        if merge_strategy == "replace":
            # Replace matching sections
            return new_config
        elif merge_strategy == "append":
            # Append new to existing
            return existing_config + "\n" + new_config
        elif merge_strategy == "smart":
            # Smart merge - combine prefix-lists, update groups
            return self._smart_merge(new_config, existing_config)
        else:
            raise ValueError(f"Unknown merge strategy: {merge_strategy}")

    def _smart_merge(self, new_config: str, existing_config: str) -> str:
        """
        Intelligently merge configurations

        Args:
            new_config: New configuration
            existing_config: Existing configuration

        Returns:
            Smartly merged configuration
        """
        # This is a simplified smart merge
        # In production, would use proper Juniper config parsing

        merged_lines = []

        # Extract prefix-lists from both configs
        import re

        # Get existing prefix-lists
        existing_lists = {}
        pattern = r"prefix-list\s+(\S+)\s*{([^}]*)}"
        for match in re.finditer(pattern, existing_config, re.DOTALL):
            list_name = match.group(1)
            existing_lists[list_name] = match.group(2)

        # Get new prefix-lists
        new_lists = {}
        for match in re.finditer(pattern, new_config, re.DOTALL):
            list_name = match.group(1)
            new_lists[list_name] = match.group(2)

        # Merge prefix-lists (new overwrites existing)
        all_lists = {**existing_lists, **new_lists}

        # Generate merged configuration
        merged_lines.append("policy-options {")

        for list_name, content in all_lists.items():
            merged_lines.append(f"    replace: prefix-list {list_name} {{")
            for line in content.strip().split("\n"):
                if line.strip():
                    merged_lines.append(f"        {line.strip()}")
            merged_lines.append("    }")

        merged_lines.append("}")

        return "\n".join(merged_lines)

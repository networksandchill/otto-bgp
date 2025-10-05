"""
YAML Generator - Creates and maintains auto-generated YAML mappings

This module generates YAML files for discovered BGP configurations.
All generated files are READ-ONLY and should never be manually edited.
"""

import yaml
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

from ..models import RouterProfile


class YAMLGenerator:
    """
    Generates and maintains YAML mappings with history tracking.

    Implements the "Zero YAML maintenance" principle - all YAML files
    are auto-generated and should never be manually edited.
    """

    def __init__(self, output_dir: Path = None):
        """
        Initialize YAMLGenerator.

        Args:
            output_dir: Directory for YAML output (default: policies/discovered)
        """
        self.logger = logging.getLogger(__name__)

        if output_dir is None:
            output_dir = Path("policies/discovered")

        self.output_dir = Path(output_dir)
        self.history_dir = self.output_dir / "history"

        # Ensure directories exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.history_dir.mkdir(parents=True, exist_ok=True)

    def generate_mappings(self, profiles: List[RouterProfile]) -> Dict:
        """
        Generate complete BGP mappings from router profiles.

        Args:
            profiles: List of RouterProfile objects with discovered data

        Returns:
            Dictionary containing all mappings
        """
        mappings = {
            "_metadata": {
                "generated_at": datetime.now().isoformat(),
                "generator": "Otto BGP",
                "total_routers": len(profiles),
                "warning": "AUTO-GENERATED FILE - DO NOT EDIT MANUALLY"
            },
            "routers": {},
            "bgp_groups": {},
            "as_numbers": {},
            "group_to_as_mapping": {},
            "router_to_groups": {}
        }

        # Process each router profile
        for profile in profiles:
            # Router entry
            mappings["routers"][profile.hostname] = {
                "ip_address": profile.ip_address,
                "discovered_as_numbers": sorted(list(profile.discovered_as_numbers)),
                "bgp_groups": list(profile.bgp_groups.keys())
            }

            # Router to groups mapping
            mappings["router_to_groups"][profile.hostname] = list(profile.bgp_groups.keys())

            # Process BGP groups
            for group_name, as_list in profile.bgp_groups.items():
                # Initialize group if not exists
                if group_name not in mappings["bgp_groups"]:
                    mappings["bgp_groups"][group_name] = {
                        "as_numbers": set(),
                        "routers": []
                    }

                # Add AS numbers and router to group
                mappings["bgp_groups"][group_name]["as_numbers"].update(as_list)
                mappings["bgp_groups"][group_name]["routers"].append(profile.hostname)

                # Group to AS mapping
                if group_name not in mappings["group_to_as_mapping"]:
                    mappings["group_to_as_mapping"][group_name] = set()
                mappings["group_to_as_mapping"][group_name].update(as_list)

                # AS number tracking
                for as_num in as_list:
                    if as_num not in mappings["as_numbers"]:
                        mappings["as_numbers"][as_num] = {
                            "routers": [],
                            "groups": []
                        }

                    if profile.hostname not in mappings["as_numbers"][as_num]["routers"]:
                        mappings["as_numbers"][as_num]["routers"].append(profile.hostname)

                    if group_name not in mappings["as_numbers"][as_num]["groups"]:
                        mappings["as_numbers"][as_num]["groups"].append(group_name)

        # Convert sets to sorted lists for YAML serialization
        for group_name in mappings["bgp_groups"]:
            mappings["bgp_groups"][group_name]["as_numbers"] = sorted(
                list(mappings["bgp_groups"][group_name]["as_numbers"])
            )

        for group_name in mappings["group_to_as_mapping"]:
            mappings["group_to_as_mapping"][group_name] = sorted(
                list(mappings["group_to_as_mapping"][group_name])
            )

        # Add summary statistics
        mappings["_metadata"]["total_bgp_groups"] = len(mappings["bgp_groups"])
        mappings["_metadata"]["total_as_numbers"] = len(mappings["as_numbers"])

        return mappings

    def save_with_history(self, mappings: Dict, output_dir: Path = None) -> Path:
        """
        Save mappings to YAML with history snapshot.

        Args:
            mappings: Dictionary to save as YAML
            output_dir: Optional override for output directory

        Returns:
            Path to saved YAML file
        """
        if output_dir is None:
            output_dir = self.output_dir

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Main output file
        output_file = output_dir / "bgp-mappings.yaml"

        # Create history snapshot before overwriting
        if output_file.exists():
            self._create_history_snapshot(output_file)

        # Write new mappings
        with open(output_file, 'w') as f:
            # Add header comment
            f.write("# AUTO-GENERATED FILE - DO NOT EDIT MANUALLY\n")
            f.write(f"# Generated by Otto BGP at {datetime.now().isoformat()}\n")
            f.write("# This file is automatically regenerated during discovery\n")
            f.write("# Any manual changes will be lost\n\n")

            # Write YAML with proper formatting
            yaml.dump(mappings, f, default_flow_style=False, sort_keys=False, indent=2)

        self.logger.info(f"Saved BGP mappings to {output_file}")

        # Also save as JSON for easier programmatic access
        json_file = output_dir / "bgp-mappings.json"
        with open(json_file, 'w') as f:
            json.dump(mappings, f, indent=2)

        return output_file

    def save_router_inventory(self, profiles: List[RouterProfile], output_dir: Path = None) -> Path:
        """
        Save router inventory as JSON.

        Args:
            profiles: List of RouterProfile objects
            output_dir: Optional override for output directory

        Returns:
            Path to saved inventory file
        """
        if output_dir is None:
            output_dir = self.output_dir

        output_dir = Path(output_dir)
        inventory_file = output_dir / "router-inventory.json"

        inventory = {
            "_metadata": {
                "generated_at": datetime.now().isoformat(),
                "total_routers": len(profiles),
                "warning": "AUTO-GENERATED FILE - DO NOT EDIT MANUALLY"
            },
            "routers": []
        }

        for profile in profiles:
            router_data = {
                "hostname": profile.hostname,
                "ip_address": profile.ip_address,
                "discovered_as_numbers": sorted(list(profile.discovered_as_numbers)),
                "bgp_groups": profile.bgp_groups,
                "metadata": profile.metadata
            }
            inventory["routers"].append(router_data)

        # Create history snapshot if file exists
        if inventory_file.exists():
            self._create_history_snapshot(inventory_file)

        with open(inventory_file, 'w') as f:
            json.dump(inventory, f, indent=2)

        self.logger.info(f"Saved router inventory to {inventory_file}")

        return inventory_file

    def load_previous_mappings(self) -> Optional[Dict]:
        """
        Load previous mappings if they exist.

        Returns:
            Previous mappings dictionary or None if not found
        """
        mappings_file = self.output_dir / "bgp-mappings.yaml"

        if not mappings_file.exists():
            return None

        try:
            with open(mappings_file, 'r') as f:
                mappings = yaml.safe_load(f)

            self.logger.debug(f"Loaded previous mappings from {mappings_file}")
            return mappings

        except Exception as e:
            self.logger.warning(f"Failed to load previous mappings: {e}")
            return None

    def diff_mappings(self, old: Dict, new: Dict) -> Dict:
        """
        Calculate differences between old and new mappings.

        Args:
            old: Previous mappings
            new: New mappings

        Returns:
            Dictionary describing the differences
        """
        diff = {
            "added": {
                "routers": [],
                "groups": [],
                "as_numbers": []
            },
            "removed": {
                "routers": [],
                "groups": [],
                "as_numbers": []
            },
            "modified": {
                "routers": {},
                "groups": {}
            },
            "summary": ""
        }

        # Compare routers
        old_routers = set(old.get("routers", {}).keys())
        new_routers = set(new.get("routers", {}).keys())

        diff["added"]["routers"] = sorted(list(new_routers - old_routers))
        diff["removed"]["routers"] = sorted(list(old_routers - new_routers))

        # Check for modified routers
        for router in old_routers & new_routers:
            old_as = set(old["routers"][router].get("discovered_as_numbers", []))
            new_as = set(new["routers"][router].get("discovered_as_numbers", []))

            if old_as != new_as:
                diff["modified"]["routers"][router] = {
                    "added_as": sorted(list(new_as - old_as)),
                    "removed_as": sorted(list(old_as - new_as))
                }

        # Compare BGP groups
        old_groups = set(old.get("bgp_groups", {}).keys())
        new_groups = set(new.get("bgp_groups", {}).keys())

        diff["added"]["groups"] = sorted(list(new_groups - old_groups))
        diff["removed"]["groups"] = sorted(list(old_groups - new_groups))

        # Check for modified groups
        for group in old_groups & new_groups:
            old_as = set(old["bgp_groups"][group].get("as_numbers", []))
            new_as = set(new["bgp_groups"][group].get("as_numbers", []))

            if old_as != new_as:
                diff["modified"]["groups"][group] = {
                    "added_as": sorted(list(new_as - old_as)),
                    "removed_as": sorted(list(old_as - new_as))
                }

        # Compare AS numbers
        old_as_nums = set(old.get("as_numbers", {}).keys())
        new_as_nums = set(new.get("as_numbers", {}).keys())

        diff["added"]["as_numbers"] = sorted(list(new_as_nums - old_as_nums))
        diff["removed"]["as_numbers"] = sorted(list(old_as_nums - new_as_nums))

        # Generate summary
        changes = []
        if diff["added"]["routers"]:
            changes.append(f"Added {len(diff['added']['routers'])} routers")
        if diff["removed"]["routers"]:
            changes.append(f"Removed {len(diff['removed']['routers'])} routers")
        if diff["added"]["groups"]:
            changes.append(f"Added {len(diff['added']['groups'])} groups")
        if diff["added"]["as_numbers"]:
            changes.append(f"Added {len(diff['added']['as_numbers'])} AS numbers")

        if changes:
            diff["summary"] = "Changes detected: " + ", ".join(changes)
        else:
            diff["summary"] = "No changes detected"

        return diff

    def _create_history_snapshot(self, file_path: Path) -> Path:
        """
        Create a history snapshot of a file.

        Args:
            file_path: Path to file to snapshot

        Returns:
            Path to snapshot file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_name = f"{file_path.stem}_{timestamp}{file_path.suffix}"
        snapshot_path = self.history_dir / snapshot_name

        try:
            # Copy file content to history
            with open(file_path, 'r') as src:
                with open(snapshot_path, 'w') as dst:
                    dst.write(src.read())

            self.logger.debug(f"Created history snapshot: {snapshot_path}")

            # Clean old snapshots (keep last 10)
            self._cleanup_old_snapshots(file_path.stem)

            return snapshot_path

        except Exception as e:
            self.logger.warning(f"Failed to create history snapshot: {e}")
            return None

    def _cleanup_old_snapshots(self, file_stem: str, keep_count: int = 10):
        """
        Clean up old history snapshots, keeping only the most recent ones.

        Args:
            file_stem: Base name of file to clean snapshots for
            keep_count: Number of snapshots to keep
        """
        try:
            # Find all snapshots for this file
            snapshots = sorted(self.history_dir.glob(f"{file_stem}_*"))

            # Remove oldest if we have too many
            if len(snapshots) > keep_count:
                for snapshot in snapshots[:-keep_count]:
                    snapshot.unlink()
                    self.logger.debug(f"Removed old snapshot: {snapshot}")

        except Exception as e:
            self.logger.warning(f"Failed to cleanup old snapshots: {e}")

    def generate_diff_report(self, diff: Dict, output_dir: Path = None) -> Path:
        """
        Generate a human-readable diff report.

        Args:
            diff: Diff dictionary from diff_mappings()
            output_dir: Optional override for output directory

        Returns:
            Path to diff report file
        """
        if output_dir is None:
            output_dir = self.output_dir

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = output_dir / f"diff_report_{timestamp}.txt"

        with open(report_file, 'w') as f:
            f.write("BGP Discovery Diff Report\n")
            f.write("=" * 50 + "\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n\n")

            f.write(f"Summary: {diff['summary']}\n\n")

            # Added items
            if any(diff["added"].values()):
                f.write("ADDED:\n")
                if diff["added"]["routers"]:
                    f.write(f"  Routers: {', '.join(diff['added']['routers'])}\n")
                if diff["added"]["groups"]:
                    f.write(f"  Groups: {', '.join(diff['added']['groups'])}\n")
                if diff["added"]["as_numbers"]:
                    f.write(f"  AS Numbers: {', '.join(map(str, diff['added']['as_numbers']))}\n")
                f.write("\n")

            # Removed items
            if any(diff["removed"].values()):
                f.write("REMOVED:\n")
                if diff["removed"]["routers"]:
                    f.write(f"  Routers: {', '.join(diff['removed']['routers'])}\n")
                if diff["removed"]["groups"]:
                    f.write(f"  Groups: {', '.join(diff['removed']['groups'])}\n")
                if diff["removed"]["as_numbers"]:
                    f.write(f"  AS Numbers: {', '.join(map(str, diff['removed']['as_numbers']))}\n")
                f.write("\n")

            # Modified items
            if diff["modified"]["routers"]:
                f.write("MODIFIED ROUTERS:\n")
                for router, changes in diff["modified"]["routers"].items():
                    f.write(f"  {router}:\n")
                    if changes["added_as"]:
                        f.write(f"    Added AS: {', '.join(map(str, changes['added_as']))}\n")
                    if changes["removed_as"]:
                        f.write(f"    Removed AS: {', '.join(map(str, changes['removed_as']))}\n")
                f.write("\n")

            if diff["modified"]["groups"]:
                f.write("MODIFIED GROUPS:\n")
                for group, changes in diff["modified"]["groups"].items():
                    f.write(f"  {group}:\n")
                    if changes["added_as"]:
                        f.write(f"    Added AS: {', '.join(map(str, changes['added_as']))}\n")
                    if changes["removed_as"]:
                        f.write(f"    Removed AS: {', '.join(map(str, changes['removed_as']))}\n")

        self.logger.info(f"Generated diff report: {report_file}")

        return report_file

    def generate_diff_report_from_current(self, current_mappings: Dict) -> Optional[Path]:
        """
        Generate diff report comparing current mappings to the latest history snapshot.

        This convenience method handles loading previous mappings from history and
        calling diff calculation automatically for CLI integration.

        Args:
            current_mappings: Current mappings to compare against history.

        Returns:
            Path to generated diff report, or None if no previous mappings exist.
        """
        # Ensure history directory exists
        if not self.history_dir.exists():
            self.logger.info("No history directory found for diff comparison")
            return None

        # Find history files for bgp-mappings snapshots (timestamp sorted)
        history_files = sorted(self.history_dir.glob("bgp-mappings_*.yaml"))

        if not history_files:
            self.logger.info("No previous mappings found in history for diff comparison")
            return None

        # Load most recent history file (lexicographically latest timestamp)
        latest_history = history_files[-1]
        self.logger.debug(f"Loading previous mappings from: {latest_history}")

        try:
            with open(latest_history, 'r') as f:
                previous_mappings = yaml.safe_load(f)

            if not previous_mappings:
                self.logger.warning(f"Previous mappings file is empty: {latest_history}")
                return None

            # Calculate diff using existing method
            diff = self.diff_mappings(previous_mappings, current_mappings)

            # Generate and return diff report path
            diff_report_path = self.generate_diff_report(diff)
            self.logger.info(f"Generated diff report: {diff_report_path}")

            return diff_report_path

        except yaml.YAMLError as e:
            self.logger.error(f"Failed to parse YAML from history file {latest_history}: {e}")
            return None
        except FileNotFoundError:
            self.logger.error(f"History file not found: {latest_history}")
            return None
        except Exception as e:
            self.logger.error(f"Failed to generate diff report from current mappings: {e}")
            return None

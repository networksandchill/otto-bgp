"""
Otto BGP Directory Management

This module handles the creation and management of router-specific directory structures
for the router-aware architecture.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class DirectoryManager:
    """
    Manages directory structure for router-aware policy generation.

    Creates and maintains the following structure:
    policies/
    ├── routers/
    │   ├── {hostname}/
    │   │   ├── AS{number}_policy.txt
    │   │   ├── combined_policies.txt
    │   │   └── metadata.json
    ├── discovered/
    │   ├── bgp-mappings.yaml
    │   ├── router-inventory.json
    │   └── history/
    └── reports/
        ├── deployment-matrix.csv
        └── generation-log.json
    """

    def __init__(self, base_dir: str = "policies"):
        """
        Initialize DirectoryManager with base directory.

        Args:
            base_dir: Base directory for all policy outputs (default: "policies")
        """
        self.base_dir = Path(base_dir)
        self.logger = logging.getLogger(__name__)

        # Define directory structure
        self.routers_dir = self.base_dir / "routers"
        self.discovered_dir = self.base_dir / "discovered"
        self.history_dir = self.discovered_dir / "history"
        self.reports_dir = self.base_dir / "reports"

        # Create base structure on initialization
        self._initialize_base_structure()

    def _initialize_base_structure(self) -> None:
        """Create the base directory structure if it doesn't exist."""
        directories = [
            self.base_dir,
            self.routers_dir,
            self.discovered_dir,
            self.history_dir,
            self.reports_dir,
        ]

        for directory in directories:
            if not directory.exists():
                directory.mkdir(parents=True, exist_ok=True)
                self.logger.debug(f"Created directory: {directory}")

    def create_router_structure(self, hostname: str) -> Path:
        """
        Create directory structure for a specific router.

        Args:
            hostname: Router hostname (e.g., "edge-router-01.nyc")

        Returns:
            Path to the created router directory
        """
        # Sanitize hostname for filesystem (replace invalid chars)
        safe_hostname = self._sanitize_hostname(hostname)
        router_dir = self.routers_dir / safe_hostname

        if not router_dir.exists():
            router_dir.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"Created router directory: {router_dir}")

            # Create initial metadata file
            metadata_path = router_dir / "metadata.json"
            initial_metadata = {
                "hostname": hostname,
                "safe_hostname": safe_hostname,
                "created_at": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
                "policies": [],
                "as_numbers": [],
            }

            with open(metadata_path, "w") as f:
                json.dump(initial_metadata, f, indent=2)

            self.logger.debug(f"Created metadata file: {metadata_path}")

        return router_dir

    def get_router_policy_dir(self, hostname: str) -> Path:
        """
        Get the policy directory path for a specific router.

        Args:
            hostname: Router hostname

        Returns:
            Path to router's policy directory
        """
        safe_hostname = self._sanitize_hostname(hostname)
        return self.routers_dir / safe_hostname

    def create_discovery_dir(self) -> Path:
        """
        Ensure discovery directory exists and return its path.

        Returns:
            Path to discovery directory
        """
        if not self.discovered_dir.exists():
            self.discovered_dir.mkdir(parents=True, exist_ok=True)
            self.logger.debug(f"Created discovery directory: {self.discovered_dir}")

        return self.discovered_dir

    def create_history_snapshot(self, snapshot_name: Optional[str] = None) -> Path:
        """
        Create a history snapshot directory with timestamp.

        Args:
            snapshot_name: Optional name for snapshot (defaults to timestamp)

        Returns:
            Path to created snapshot directory
        """
        if not snapshot_name:
            snapshot_name = datetime.now().strftime("%Y%m%d_%H%M%S")

        snapshot_dir = self.history_dir / snapshot_name
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        self.logger.info(f"Created history snapshot: {snapshot_dir}")
        return snapshot_dir

    def list_router_directories(self) -> List[str]:
        """
        List all router directories.

        Returns:
            List of router directory names (hostnames)
        """
        if not self.routers_dir.exists():
            return []

        return [d.name for d in self.routers_dir.iterdir() if d.is_dir()]

    def get_router_metadata(self, hostname: str) -> Optional[Dict]:
        """
        Read metadata for a specific router.

        Args:
            hostname: Router hostname

        Returns:
            Metadata dictionary or None if not found
        """
        metadata_path = self.get_router_policy_dir(hostname) / "metadata.json"

        if metadata_path.exists():
            try:
                with open(metadata_path, "r") as f:
                    return json.load(f)
            except Exception as e:
                self.logger.error(f"Error reading metadata for {hostname}: {e}")

        return None

    def update_router_metadata(self, hostname: str, metadata: Dict) -> bool:
        """
        Update metadata for a specific router.

        Args:
            hostname: Router hostname
            metadata: Metadata dictionary to save

        Returns:
            True if successful, False otherwise
        """
        try:
            router_dir = self.create_router_structure(hostname)
            metadata_path = router_dir / "metadata.json"

            # Update last_updated timestamp
            metadata["last_updated"] = datetime.now().isoformat()

            with open(metadata_path, "w") as f:
                json.dump(metadata, f, indent=2)

            self.logger.debug(f"Updated metadata for {hostname}")
            return True

        except Exception as e:
            self.logger.error(f"Error updating metadata for {hostname}: {e}")
            return False

    def clean_router_directory(self, hostname: str) -> bool:
        """
        Clean all policy files from a router directory (keeps metadata).

        Args:
            hostname: Router hostname

        Returns:
            True if successful, False otherwise
        """
        try:
            router_dir = self.get_router_policy_dir(hostname)

            if router_dir.exists():
                # Remove only policy files, keep metadata
                for policy_file in router_dir.glob("*.txt"):
                    policy_file.unlink()
                    self.logger.debug(f"Removed policy file: {policy_file}")

                self.logger.info(f"Cleaned policy files for {hostname}")
                return True

            return False

        except Exception as e:
            self.logger.error(f"Error cleaning directory for {hostname}: {e}")
            return False

    def _sanitize_hostname(self, hostname: str) -> str:
        """
        Sanitize hostname for use as directory name.

        Args:
            hostname: Original hostname

        Returns:
            Sanitized hostname safe for filesystem
        """
        # Replace potentially problematic characters
        replacements = {
            "/": "-",
            "\\": "-",
            ":": "-",
            "*": "-",
            "?": "-",
            '"': "-",
            "<": "-",
            ">": "-",
            "|": "-",
            " ": "_",
        }

        safe_name = hostname
        for char, replacement in replacements.items():
            safe_name = safe_name.replace(char, replacement)

        # Ensure name is not empty or just dots
        if not safe_name or safe_name in (".", ".."):
            safe_name = f"router_{hash(hostname)}"

        return safe_name

    def get_summary_statistics(self) -> Dict:
        """
        Get summary statistics about the directory structure.

        Returns:
            Dictionary with statistics
        """
        stats = {
            "total_routers": len(self.list_router_directories()),
            "total_policies": 0,
            "total_size_mb": 0,
            "discovery_files": 0,
            "history_snapshots": 0,
        }

        # Count policy files
        if self.routers_dir.exists():
            for router_dir in self.routers_dir.iterdir():
                if router_dir.is_dir():
                    policy_files = list(router_dir.glob("*.txt"))
                    stats["total_policies"] += len(policy_files)

                    # Calculate size
                    for policy_file in policy_files:
                        stats["total_size_mb"] += policy_file.stat().st_size / (
                            1024 * 1024
                        )

        # Count discovery files
        if self.discovered_dir.exists():
            stats["discovery_files"] = len(
                list(self.discovered_dir.glob("*.yaml"))
            ) + len(list(self.discovered_dir.glob("*.json")))

        # Count history snapshots
        if self.history_dir.exists():
            stats["history_snapshots"] = len(list(self.history_dir.iterdir()))

        return stats

    def create_reports_directory(self) -> Path:
        """
        Ensure reports directory exists and return its path.

        Returns:
            Path to reports directory
        """
        if not self.reports_dir.exists():
            self.reports_dir.mkdir(parents=True, exist_ok=True)
            self.logger.debug(f"Created reports directory: {self.reports_dir}")

        return self.reports_dir

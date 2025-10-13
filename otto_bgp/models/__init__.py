"""
Otto BGP Data Models

This module contains the core data models for Otto BGP's router-aware architecture.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set


@dataclass
class RouterProfile:
    """
    Complete BGP profile for each router.

    This is the core data structure that maintains router identity
    throughout the entire pipeline from collection to policy application.
    """
    hostname: str                          # From enhanced CSV (e.g., "edge-router-01.nyc")
    ip_address: str                        # From CSV (e.g., "192.168.1.1")
    bgp_config: str = ""                  # Collected via SSH
    discovered_as_numbers: Set[int] = field(default_factory=set)  # Auto-discovered from config
    bgp_groups: Dict[str, List[int]] = field(default_factory=dict)  # BGP group -> AS numbers mapping
    metadata: Dict = field(default_factory=dict)  # Version, platform, collection timestamp, etc.

    def __post_init__(self):
        """Initialize metadata with default values if not provided."""
        if 'collected_at' not in self.metadata:
            self.metadata['collected_at'] = datetime.now().isoformat()
        if 'platform' not in self.metadata:
            self.metadata['platform'] = 'junos'  # Default to Juniper

    def add_as_number(self, as_number: int) -> None:
        """Add a discovered AS number to this router's profile."""
        if 0 <= as_number <= 4294967295:  # Valid 32-bit AS number range
            self.discovered_as_numbers.add(as_number)

    def add_bgp_group(self, group_name: str, as_numbers: List[int]) -> None:
        """Add or update a BGP group with its associated AS numbers."""
        self.bgp_groups[group_name] = as_numbers

    def to_dict(self) -> dict:
        """Convert RouterProfile to dictionary for JSON serialization."""
        return {
            'hostname': self.hostname,
            'ip_address': self.ip_address,
            'discovered_as_numbers': sorted(list(self.discovered_as_numbers)),
            'bgp_groups': self.bgp_groups,
            'metadata': self.metadata,
            'config_length': len(self.bgp_config)  # Don't include full config in serialization
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'RouterProfile':
        """Create RouterProfile from dictionary."""
        profile = cls(
            hostname=data['hostname'],
            ip_address=data['ip_address'],
            bgp_config="",  # Config not included in serialization
            discovered_as_numbers=set(data.get('discovered_as_numbers', [])),
            bgp_groups=data.get('bgp_groups', {}),
            metadata=data.get('metadata', {})
        )
        return profile


@dataclass
class PipelineResult:
    """
    Result of the router-aware pipeline execution.
    Contains all router profiles and summary statistics.
    """
    router_profiles: List[RouterProfile]
    success: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    statistics: Dict = field(default_factory=dict)

    def __post_init__(self):
        """Calculate statistics after initialization."""
        if not self.statistics:
            self.statistics = {
                'total_routers': len(self.router_profiles),
                'total_as_numbers': len(self.get_all_as_numbers()),
                'total_bgp_groups': sum(len(p.bgp_groups) for p in self.router_profiles),
                'execution_time': None  # Set by pipeline
            }

    def get_all_as_numbers(self) -> Set[int]:
        """Get all unique AS numbers across all routers."""
        all_as = set()
        for profile in self.router_profiles:
            all_as.update(profile.discovered_as_numbers)
        return all_as

    def get_router_by_hostname(self, hostname: str) -> Optional[RouterProfile]:
        """Find a router profile by hostname."""
        for profile in self.router_profiles:
            if profile.hostname == hostname:
                return profile
        return None

    def to_summary(self) -> str:
        """Generate a summary string of the pipeline result."""
        lines = [
            f"Pipeline {'succeeded' if self.success else 'failed'}",
            f"Routers processed: {self.statistics['total_routers']}",
            f"AS numbers discovered: {self.statistics['total_as_numbers']}",
            f"BGP groups found: {self.statistics['total_bgp_groups']}"
        ]

        if self.errors:
            lines.append(f"Errors: {len(self.errors)}")
            for error in self.errors[:3]:  # Show first 3 errors
                lines.append(f"  - {error}")

        if self.warnings:
            lines.append(f"Warnings: {len(self.warnings)}")

        return "\n".join(lines)


@dataclass
class DeviceInfo:
    """
    Enhanced device information for router-aware architecture.
    Now includes mandatory hostname field.
    """
    address: str
    hostname: str  # Required field
    username: Optional[str] = None
    password: Optional[str] = None
    port: int = 22
    role: Optional[str] = None  # Optional: edge, core, etc.
    region: Optional[str] = None  # Optional: us-east, eu-west, etc.

    def __post_init__(self):
        """Validate device information."""
        if not self.hostname:
            raise ValueError(f"Hostname is required for device {self.address}")

    @classmethod
    def from_csv_row(cls, row: dict) -> 'DeviceInfo':
        """
        Create DeviceInfo from CSV row.
        Requires both address and hostname columns.
        """
        return cls(
            address=row['address'],
            hostname=row['hostname'],  # Required field
            username=row.get('username'),
            password=row.get('password'),
            port=int(row.get('port', 22)),
            role=row.get('role'),
            region=row.get('region')
        )

    def to_router_profile(self) -> RouterProfile:
        """Convert DeviceInfo to RouterProfile."""
        return RouterProfile(
            hostname=self.hostname,
            ip_address=self.address,
            metadata={
                'port': self.port,
                'role': self.role,
                'region': self.region
            }
        )

"""
Deployment Matrix Generation for Router-Aware BGP Policies

This module creates comprehensive deployment matrices showing:
- Which routers handle which AS numbers
- BGP group to AS mappings
- Router interconnection relationships
- Policy distribution statistics
"""

import csv
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..models import RouterProfile


@dataclass
class MatrixStatistics:
    """Statistics for deployment matrix"""

    total_routers: int = 0
    total_as_numbers: int = 0
    total_bgp_groups: int = 0
    total_policies: int = 0
    average_as_per_router: float = 0.0
    max_as_per_router: int = 0
    min_as_per_router: int = 0
    routers_with_no_as: List[str] = field(default_factory=list)
    most_common_as: List[Tuple[int, int]] = field(default_factory=list)  # (AS, count)
    shared_as_numbers: Dict[int, List[str]] = field(
        default_factory=dict
    )  # AS -> [routers]


class DeploymentMatrix:
    """
    Generate deployment matrices and reports for router-aware BGP policies
    """

    def __init__(self, output_dir: str = "policies/reports"):
        """
        Initialize deployment matrix generator

        Args:
            output_dir: Directory to save report files
        """
        self.logger = logging.getLogger(__name__)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_router_as_matrix(self, profiles: List[RouterProfile]) -> Dict:
        """
        Generate router-to-AS mapping matrix

        Args:
            profiles: List of RouterProfile objects with discovered AS numbers

        Returns:
            Dictionary containing matrix data and statistics
        """
        self.logger.info(f"Generating deployment matrix for {len(profiles)} routers")

        # Build matrix data
        matrix = {
            "_metadata": {
                "generated": datetime.now().isoformat(),
                "version": "0.3.2",
                "total_routers": len(profiles),
            },
            "routers": {},
            "as_numbers": {},
            "bgp_groups": {},
            "relationships": [],
        }

        # Track AS number occurrences
        as_counter = {}
        all_groups = set()

        # Process each router profile
        for profile in profiles:
            router_data = {
                "hostname": profile.hostname,
                "ip_address": profile.ip_address,
                "site": profile.site or "unknown",
                "role": profile.role or "unknown",
                "as_numbers": sorted(list(profile.discovered_as_numbers))
                if profile.discovered_as_numbers
                else [],
                "as_count": len(profile.discovered_as_numbers)
                if profile.discovered_as_numbers
                else 0,
                "bgp_groups": profile.bgp_groups or {},
            }

            matrix["routers"][profile.hostname] = router_data

            # Track AS numbers
            if profile.discovered_as_numbers:
                for as_num in profile.discovered_as_numbers:
                    if as_num not in matrix["as_numbers"]:
                        matrix["as_numbers"][as_num] = {"routers": [], "groups": []}
                    matrix["as_numbers"][as_num]["routers"].append(profile.hostname)

                    # Count occurrences
                    as_counter[as_num] = as_counter.get(as_num, 0) + 1

            # Track BGP groups
            if profile.bgp_groups:
                for group_name, as_list in profile.bgp_groups.items():
                    all_groups.add(group_name)
                    if group_name not in matrix["bgp_groups"]:
                        matrix["bgp_groups"][group_name] = {
                            "routers": [],
                            "as_numbers": set(),
                        }
                    matrix["bgp_groups"][group_name]["routers"].append(profile.hostname)
                    matrix["bgp_groups"][group_name]["as_numbers"].update(as_list)

        # Convert sets to lists for JSON serialization
        for group_name in matrix["bgp_groups"]:
            matrix["bgp_groups"][group_name]["as_numbers"] = sorted(
                list(matrix["bgp_groups"][group_name]["as_numbers"])
            )

        # Calculate statistics
        stats = self._calculate_statistics(profiles, as_counter)
        matrix["statistics"] = self._stats_to_dict(stats)

        # Find relationships (routers sharing AS numbers)
        matrix["relationships"] = self._find_router_relationships(matrix["as_numbers"])

        self.logger.info(
            f"Matrix generated: {stats.total_routers} routers, {stats.total_as_numbers} AS numbers"
        )

        return matrix

    def _calculate_statistics(
        self, profiles: List[RouterProfile], as_counter: Dict[int, int]
    ) -> MatrixStatistics:
        """Calculate deployment statistics"""
        stats = MatrixStatistics()

        stats.total_routers = len(profiles)
        stats.total_as_numbers = len(as_counter)

        # Router AS counts
        as_counts = []
        for profile in profiles:
            count = (
                len(profile.discovered_as_numbers)
                if profile.discovered_as_numbers
                else 0
            )
            as_counts.append(count)
            if count == 0:
                stats.routers_with_no_as.append(profile.hostname)

        if as_counts:
            stats.average_as_per_router = sum(as_counts) / len(as_counts)
            stats.max_as_per_router = max(as_counts)
            stats.min_as_per_router = min(as_counts)

        # BGP groups
        all_groups = set()
        for profile in profiles:
            if profile.bgp_groups:
                all_groups.update(profile.bgp_groups.keys())
        stats.total_bgp_groups = len(all_groups)

        # Most common AS numbers
        if as_counter:
            sorted_as = sorted(as_counter.items(), key=lambda x: x[1], reverse=True)
            stats.most_common_as = sorted_as[:10]  # Top 10

        # Shared AS numbers (appearing on multiple routers)
        for as_num, count in as_counter.items():
            if count > 1:
                routers = []
                for profile in profiles:
                    if (
                        profile.discovered_as_numbers
                        and as_num in profile.discovered_as_numbers
                    ):
                        routers.append(profile.hostname)
                stats.shared_as_numbers[as_num] = routers

        return stats

    def _stats_to_dict(self, stats: MatrixStatistics) -> Dict:
        """Convert statistics to dictionary for JSON serialization"""
        return {
            "total_routers": stats.total_routers,
            "total_as_numbers": stats.total_as_numbers,
            "total_bgp_groups": stats.total_bgp_groups,
            "total_policies": stats.total_policies,
            "average_as_per_router": round(stats.average_as_per_router, 2),
            "max_as_per_router": stats.max_as_per_router,
            "min_as_per_router": stats.min_as_per_router,
            "routers_with_no_as": stats.routers_with_no_as,
            "most_common_as": [
                {"as_number": as_num, "count": count}
                for as_num, count in stats.most_common_as
            ],
            "shared_as_numbers": [
                {"as_number": as_num, "routers": routers}
                for as_num, routers in stats.shared_as_numbers.items()
            ],
        }

    def _find_router_relationships(self, as_numbers: Dict) -> List[Dict]:
        """Find relationships between routers based on shared AS numbers"""
        relationships = []

        # Find routers that share AS numbers
        for as_num, data in as_numbers.items():
            if len(data["routers"]) > 1:
                relationships.append(
                    {
                        "type": "shared_as",
                        "as_number": as_num,
                        "routers": data["routers"],
                        "description": f"AS{as_num} appears on {len(data['routers'])} routers",
                    }
                )

        return relationships

    def export_csv(self, matrix: Dict, output_path: Optional[Path] = None) -> Path:
        """
        Export matrix to CSV format

        Args:
            matrix: Deployment matrix dictionary
            output_path: Optional custom output path

        Returns:
            Path to created CSV file
        """
        if output_path is None:
            output_path = self.output_dir / "deployment-matrix.csv"

        with open(output_path, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)

            # Write header
            writer.writerow(
                [
                    "Router",
                    "IP Address",
                    "Site",
                    "Role",
                    "AS Count",
                    "AS Numbers",
                    "BGP Groups",
                ]
            )

            # Write router data
            for hostname, data in matrix["routers"].items():
                as_numbers_str = ", ".join(str(as_num) for as_num in data["as_numbers"])
                bgp_groups_str = (
                    ", ".join(data["bgp_groups"].keys()) if data["bgp_groups"] else ""
                )

                writer.writerow(
                    [
                        hostname,
                        data["ip_address"],
                        data["site"],
                        data["role"],
                        data["as_count"],
                        as_numbers_str,
                        bgp_groups_str,
                    ]
                )

        self.logger.info(f"Exported deployment matrix to CSV: {output_path}")
        return output_path

    def export_json(self, matrix: Dict, output_path: Optional[Path] = None) -> Path:
        """
        Export matrix to JSON format

        Args:
            matrix: Deployment matrix dictionary
            output_path: Optional custom output path

        Returns:
            Path to created JSON file
        """
        if output_path is None:
            output_path = self.output_dir / "deployment-matrix.json"

        with open(output_path, "w") as jsonfile:
            json.dump(matrix, jsonfile, indent=2)

        self.logger.info(f"Exported deployment matrix to JSON: {output_path}")
        return output_path

    def generate_summary_report(
        self, matrix: Dict, output_path: Optional[Path] = None
    ) -> Path:
        """
        Generate human-readable summary report

        Args:
            matrix: Deployment matrix dictionary
            output_path: Optional custom output path

        Returns:
            Path to created report file
        """
        if output_path is None:
            output_path = self.output_dir / "deployment-summary.txt"

        with open(output_path, "w") as report:
            report.write("=" * 80 + "\n")
            report.write("OTTO BGP DEPLOYMENT MATRIX SUMMARY\n")
            report.write("=" * 80 + "\n\n")

            # Metadata
            report.write(f"Generated: {matrix['_metadata']['generated']}\n")
            report.write(f"Version: {matrix['_metadata']['version']}\n\n")

            # Statistics
            stats = matrix["statistics"]
            report.write("STATISTICS\n")
            report.write("-" * 40 + "\n")
            report.write(f"Total Routers: {stats['total_routers']}\n")
            report.write(f"Total AS Numbers: {stats['total_as_numbers']}\n")
            report.write(f"Total BGP Groups: {stats['total_bgp_groups']}\n")
            report.write(f"Average AS per Router: {stats['average_as_per_router']}\n")
            report.write(f"Max AS per Router: {stats['max_as_per_router']}\n")
            report.write(f"Min AS per Router: {stats['min_as_per_router']}\n\n")

            # Router Details
            report.write("ROUTER DETAILS\n")
            report.write("-" * 40 + "\n")
            for hostname, data in matrix["routers"].items():
                report.write(f"\n{hostname} ({data['ip_address']})\n")
                report.write(f"  Site: {data['site']}\n")
                report.write(f"  Role: {data['role']}\n")
                report.write(f"  AS Count: {data['as_count']}\n")
                if data["as_numbers"]:
                    report.write(
                        f"  AS Numbers: {', '.join(str(as_num) for as_num in data['as_numbers'][:10])}"
                    )
                    if len(data["as_numbers"]) > 10:
                        report.write(f" ... and {len(data['as_numbers']) - 10} more")
                    report.write("\n")

            # Shared AS Numbers
            if stats["shared_as_numbers"]:
                report.write("\nSHARED AS NUMBERS\n")
                report.write("-" * 40 + "\n")
                for shared in stats["shared_as_numbers"]:
                    report.write(
                        f"AS{shared['as_number']}: {', '.join(shared['routers'])}\n"
                    )

            # BGP Groups
            if matrix["bgp_groups"]:
                report.write("\nBGP GROUPS\n")
                report.write("-" * 40 + "\n")
                for group_name, data in matrix["bgp_groups"].items():
                    report.write(f"\n{group_name}\n")
                    report.write(f"  Routers: {', '.join(data['routers'])}\n")
                    report.write(f"  AS Count: {len(data['as_numbers'])}\n")

        self.logger.info(f"Generated summary report: {output_path}")
        return output_path

    def generate_all_reports(self, profiles: List[RouterProfile]) -> Dict[str, Path]:
        """
        Generate all report formats

        Args:
            profiles: List of RouterProfile objects

        Returns:
            Dictionary mapping report type to file path
        """
        # Generate matrix
        matrix = self.generate_router_as_matrix(profiles)

        # Export all formats
        reports = {
            "csv": self.export_csv(matrix),
            "json": self.export_json(matrix),
            "summary": self.generate_summary_report(matrix),
        }

        self.logger.info(f"Generated all reports in {self.output_dir}")
        return reports


def generate_deployment_matrix(
    profiles: List[RouterProfile], output_dir: str = "policies/reports"
) -> Dict[str, Path]:
    """
    Convenience function to generate deployment matrix and reports

    Args:
        profiles: List of RouterProfile objects with discovered AS numbers
        output_dir: Directory for report output

    Returns:
        Dictionary mapping report type to file path
    """
    generator = DeploymentMatrix(output_dir)
    return generator.generate_all_reports(profiles)

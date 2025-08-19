"""
Tests for Otto BGP v0.3.0 Router Identity Foundation (Phase 1)

This module tests the router-aware architecture components:
- RouterProfile data model
- Enhanced CSV loading with hostname support
- DeviceInfo structure updates
- DirectoryManager functionality
- Backward compatibility with v0.2.0 CSV format
"""

import unittest
import tempfile
import csv
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Import modules to test
from otto_bgp.models import RouterProfile, DeviceInfo, PipelineResult
from otto_bgp.utils.directories import DirectoryManager
from otto_bgp.collectors.juniper_ssh import JuniperSSHCollector


class TestRouterProfile(unittest.TestCase):
    """Test the RouterProfile data model."""
    
    def test_router_profile_creation(self):
        """Test creating a RouterProfile with all fields."""
        profile = RouterProfile(
            hostname="edge-router-01.nyc",
            ip_address="192.168.1.1",
            bgp_config="show configuration protocols bgp",
            discovered_as_numbers={13335, 15169},
            bgp_groups={"external-peers": [13335, 15169]},
            metadata={"platform": "junos", "version": "21.4R1"}
        )
        
        self.assertEqual(profile.hostname, "edge-router-01.nyc")
        self.assertEqual(profile.ip_address, "192.168.1.1")
        self.assertEqual(len(profile.discovered_as_numbers), 2)
        self.assertIn(13335, profile.discovered_as_numbers)
        self.assertEqual(profile.bgp_groups["external-peers"], [13335, 15169])
    
    def test_router_profile_add_as_number(self):
        """Test adding AS numbers with validation."""
        profile = RouterProfile("test-router", "10.0.0.1")
        
        # Valid AS number
        profile.add_as_number(65001)
        self.assertIn(65001, profile.discovered_as_numbers)
        
        # Invalid AS number (out of range)
        profile.add_as_number(4294967296)  # Too large
        self.assertNotIn(4294967296, profile.discovered_as_numbers)
        
        # Invalid AS number (negative)
        profile.add_as_number(-1)
        self.assertNotIn(-1, profile.discovered_as_numbers)
    
    def test_router_profile_serialization(self):
        """Test converting RouterProfile to/from dictionary."""
        profile = RouterProfile(
            hostname="test-router",
            ip_address="10.0.0.1",
            discovered_as_numbers={65001, 65002},
            bgp_groups={"peers": [65001, 65002]}
        )
        
        # To dict
        data = profile.to_dict()
        self.assertEqual(data["hostname"], "test-router")
        self.assertEqual(data["ip_address"], "10.0.0.1")
        self.assertEqual(sorted(data["discovered_as_numbers"]), [65001, 65002])
        
        # From dict
        new_profile = RouterProfile.from_dict(data)
        self.assertEqual(new_profile.hostname, profile.hostname)
        self.assertEqual(new_profile.ip_address, profile.ip_address)
        self.assertEqual(new_profile.discovered_as_numbers, profile.discovered_as_numbers)


class TestDeviceInfo(unittest.TestCase):
    """Test the enhanced DeviceInfo structure."""
    
    def test_device_info_with_hostname(self):
        """Test DeviceInfo with explicit hostname."""
        device = DeviceInfo(
            address="192.168.1.1",
            hostname="edge-router-01.nyc"
        )
        
        self.assertEqual(device.address, "192.168.1.1")
        self.assertEqual(device.hostname, "edge-router-01.nyc")
    
    def test_device_info_auto_hostname(self):
        """Test DeviceInfo auto-generates hostname for backward compatibility."""
        device = DeviceInfo(
            address="192.168.1.1",
            hostname=""  # Empty hostname should auto-generate
        )
        
        self.assertEqual(device.hostname, "router-192-168-1-1")
    
    def test_device_info_from_csv_row(self):
        """Test creating DeviceInfo from CSV row data."""
        # v0.3.0 format with hostname
        row_v3 = {
            "address": "10.0.0.1",
            "hostname": "core-router-01",
            "role": "core",
            "region": "us-east"
        }
        device = DeviceInfo.from_csv_row(row_v3)
        
        self.assertEqual(device.address, "10.0.0.1")
        self.assertEqual(device.hostname, "core-router-01")
        self.assertEqual(device.role, "core")
        self.assertEqual(device.region, "us-east")
        
        # v0.2.0 format without hostname
        row_v2 = {"address": "10.0.0.2"}
        device_v2 = DeviceInfo.from_csv_row(row_v2)
        
        self.assertEqual(device_v2.address, "10.0.0.2")
        self.assertEqual(device_v2.hostname, "router-10-0-0-2")  # Auto-generated
    
    def test_device_to_router_profile(self):
        """Test converting DeviceInfo to RouterProfile."""
        device = DeviceInfo(
            address="10.0.0.1",
            hostname="test-router",
            role="edge",
            region="us-west"
        )
        
        profile = device.to_router_profile()
        
        self.assertEqual(profile.hostname, "test-router")
        self.assertEqual(profile.ip_address, "10.0.0.1")
        self.assertEqual(profile.metadata["role"], "edge")
        self.assertEqual(profile.metadata["region"], "us-west")


class TestCSVLoading(unittest.TestCase):
    """Test CSV loading with backward compatibility."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.collector = JuniperSSHCollector(
            ssh_username="test",
            ssh_password="test"
        )
    
    def test_load_v3_csv_with_hostname(self):
        """Test loading v0.3.0 CSV format with hostname column."""
        csv_path = Path(self.temp_dir) / "devices_v3.csv"
        
        # Create v0.3.0 format CSV
        with open(csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["address", "hostname", "role"])
            writer.writerow(["192.168.1.1", "edge-router-01.nyc", "edge"])
            writer.writerow(["192.168.1.2", "core-router-01.sjc", "core"])
        
        devices = self.collector.load_devices_from_csv(str(csv_path))
        
        self.assertEqual(len(devices), 2)
        self.assertEqual(devices[0].hostname, "edge-router-01.nyc")
        self.assertEqual(devices[1].hostname, "core-router-01.sjc")
    
    def test_load_v2_csv_without_hostname(self):
        """Test loading v0.2.0 CSV format (address only) with auto-generation."""
        csv_path = Path(self.temp_dir) / "devices_v2.csv"
        
        # Create v0.2.0 format CSV
        with open(csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["address"])
            writer.writerow(["10.0.0.1"])
            writer.writerow(["10.0.0.2"])
        
        devices = self.collector.load_devices_from_csv(str(csv_path))
        
        self.assertEqual(len(devices), 2)
        self.assertEqual(devices[0].hostname, "router-10-0-0-1")  # Auto-generated
        self.assertEqual(devices[1].hostname, "router-10-0-0-2")  # Auto-generated
    
    def test_duplicate_hostname_handling(self):
        """Test handling of duplicate hostnames in CSV."""
        csv_path = Path(self.temp_dir) / "devices_dup.csv"
        
        # Create CSV with duplicate hostnames
        with open(csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["address", "hostname"])
            writer.writerow(["192.168.1.1", "router-01"])
            writer.writerow(["192.168.1.2", "router-01"])  # Duplicate
        
        devices = self.collector.load_devices_from_csv(str(csv_path))
        
        self.assertEqual(len(devices), 2)
        self.assertEqual(devices[0].hostname, "router-01")
        self.assertNotEqual(devices[1].hostname, "router-01")  # Should be modified
        self.assertIn("router-01", devices[1].hostname)  # Should contain original


class TestDirectoryManager(unittest.TestCase):
    """Test DirectoryManager functionality."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.dir_manager = DirectoryManager(base_dir=self.temp_dir)
    
    def test_base_structure_creation(self):
        """Test that base directory structure is created on initialization."""
        expected_dirs = [
            Path(self.temp_dir) / "routers",
            Path(self.temp_dir) / "discovered",
            Path(self.temp_dir) / "discovered" / "history",
            Path(self.temp_dir) / "reports"
        ]
        
        for expected_dir in expected_dirs:
            self.assertTrue(expected_dir.exists(), f"Directory {expected_dir} not created")
    
    def test_create_router_structure(self):
        """Test creating router-specific directory structure."""
        hostname = "edge-router-01.nyc"
        router_dir = self.dir_manager.create_router_structure(hostname)
        
        self.assertTrue(router_dir.exists())
        self.assertEqual(router_dir.name, hostname)
        
        # Check metadata file was created
        metadata_file = router_dir / "metadata.json"
        self.assertTrue(metadata_file.exists())
        
        # Verify metadata content
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)
        
        self.assertEqual(metadata["hostname"], hostname)
        self.assertEqual(metadata["safe_hostname"], hostname)
        self.assertIn("created_at", metadata)
    
    def test_sanitize_hostname(self):
        """Test hostname sanitization for filesystem safety."""
        test_cases = [
            ("router/with/slashes", "router-with-slashes"),
            ("router:with:colons", "router-with-colons"),
            ("router with spaces", "router_with_spaces"),
            ("router?with*special<chars>", "router-with-special-chars-"),
        ]
        
        for unsafe, expected_pattern in test_cases:
            safe = self.dir_manager._sanitize_hostname(unsafe)
            # Check that unsafe characters are removed/replaced
            self.assertNotIn("/", safe)
            self.assertNotIn(":", safe)
            self.assertNotIn("?", safe)
            self.assertNotIn("*", safe)
    
    def test_router_metadata_operations(self):
        """Test reading and updating router metadata."""
        hostname = "test-router"
        self.dir_manager.create_router_structure(hostname)
        
        # Read initial metadata
        metadata = self.dir_manager.get_router_metadata(hostname)
        self.assertIsNotNone(metadata)
        self.assertEqual(metadata["hostname"], hostname)
        
        # Update metadata
        metadata["as_numbers"] = [65001, 65002]
        metadata["policies"] = ["AS65001_policy.txt", "AS65002_policy.txt"]
        
        success = self.dir_manager.update_router_metadata(hostname, metadata)
        self.assertTrue(success)
        
        # Read updated metadata
        updated = self.dir_manager.get_router_metadata(hostname)
        self.assertEqual(updated["as_numbers"], [65001, 65002])
        self.assertEqual(len(updated["policies"]), 2)
    
    def test_list_router_directories(self):
        """Test listing all router directories."""
        # Create multiple router directories
        routers = ["router-01", "router-02", "router-03"]
        for router in routers:
            self.dir_manager.create_router_structure(router)
        
        listed = self.dir_manager.list_router_directories()
        self.assertEqual(len(listed), 3)
        for router in routers:
            self.assertIn(router, listed)
    
    def test_clean_router_directory(self):
        """Test cleaning policy files while preserving metadata."""
        hostname = "test-router"
        router_dir = self.dir_manager.create_router_structure(hostname)
        
        # Create some policy files
        (router_dir / "AS65001_policy.txt").write_text("policy content")
        (router_dir / "AS65002_policy.txt").write_text("policy content")
        (router_dir / "combined_policies.txt").write_text("combined content")
        
        # Clean directory
        success = self.dir_manager.clean_router_directory(hostname)
        self.assertTrue(success)
        
        # Check that policy files are removed
        self.assertFalse((router_dir / "AS65001_policy.txt").exists())
        self.assertFalse((router_dir / "AS65002_policy.txt").exists())
        self.assertFalse((router_dir / "combined_policies.txt").exists())
        
        # Check that metadata is preserved
        self.assertTrue((router_dir / "metadata.json").exists())
    
    def test_get_summary_statistics(self):
        """Test getting summary statistics."""
        # Create some test data
        self.dir_manager.create_router_structure("router-01")
        self.dir_manager.create_router_structure("router-02")
        
        stats = self.dir_manager.get_summary_statistics()
        
        self.assertEqual(stats["total_routers"], 2)
        self.assertIn("total_policies", stats)
        self.assertIn("total_size_mb", stats)
        self.assertIn("discovery_files", stats)
        self.assertIn("history_snapshots", stats)


class TestPipelineResult(unittest.TestCase):
    """Test PipelineResult data structure."""
    
    def test_pipeline_result_creation(self):
        """Test creating PipelineResult with router profiles."""
        profiles = [
            RouterProfile("router-01", "10.0.0.1", discovered_as_numbers={65001}),
            RouterProfile("router-02", "10.0.0.2", discovered_as_numbers={65002, 65003})
        ]
        
        result = PipelineResult(router_profiles=profiles)
        
        self.assertTrue(result.success)
        self.assertEqual(len(result.router_profiles), 2)
        self.assertEqual(result.statistics["total_routers"], 2)
        self.assertEqual(result.statistics["total_as_numbers"], 3)
    
    def test_get_all_as_numbers(self):
        """Test getting all unique AS numbers across routers."""
        profiles = [
            RouterProfile("router-01", "10.0.0.1", discovered_as_numbers={65001, 65002}),
            RouterProfile("router-02", "10.0.0.2", discovered_as_numbers={65002, 65003})
        ]
        
        result = PipelineResult(router_profiles=profiles)
        all_as = result.get_all_as_numbers()
        
        self.assertEqual(len(all_as), 3)
        self.assertIn(65001, all_as)
        self.assertIn(65002, all_as)
        self.assertIn(65003, all_as)
    
    def test_get_router_by_hostname(self):
        """Test finding router profile by hostname."""
        profiles = [
            RouterProfile("router-01", "10.0.0.1"),
            RouterProfile("router-02", "10.0.0.2")
        ]
        
        result = PipelineResult(router_profiles=profiles)
        
        router = result.get_router_by_hostname("router-01")
        self.assertIsNotNone(router)
        self.assertEqual(router.ip_address, "10.0.0.1")
        
        missing = result.get_router_by_hostname("router-99")
        self.assertIsNone(missing)
    
    def test_pipeline_result_summary(self):
        """Test generating pipeline result summary."""
        profiles = [
            RouterProfile("router-01", "10.0.0.1", discovered_as_numbers={65001})
        ]
        
        result = PipelineResult(
            router_profiles=profiles,
            errors=["Error 1", "Error 2"],
            warnings=["Warning 1"]
        )
        
        summary = result.to_summary()
        
        self.assertIn("Pipeline succeeded", summary)
        self.assertIn("Routers processed: 1", summary)
        self.assertIn("AS numbers discovered: 1", summary)
        self.assertIn("Errors: 2", summary)
        self.assertIn("Warnings: 1", summary)


if __name__ == "__main__":
    unittest.main()
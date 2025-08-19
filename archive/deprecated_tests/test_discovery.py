"""
Tests for Otto BGP v0.3.0 Discovery Engine (Phase 2)

This module tests the discovery functionality:
- RouterInspector for BGP configuration analysis
- BGPConfigParser for Juniper config parsing  
- YAMLGenerator for auto-generated mappings
- Discovery CLI commands
"""

import unittest
import tempfile
import json
import yaml
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Import modules to test
from otto_bgp.discovery import RouterInspector, BGPConfigParser, YAMLGenerator
from otto_bgp.discovery.inspector import DiscoveryResult
from otto_bgp.discovery.parser import BGPGroup, BGPNeighbor
from otto_bgp.models import RouterProfile


class TestRouterInspector(unittest.TestCase):
    """Test the RouterInspector discovery functionality."""
    
    def setUp(self):
        """Set up test environment."""
        self.inspector = RouterInspector()
        
        # Sample Juniper BGP configuration
        self.sample_bgp_config = """
protocols {
    bgp {
        group external-peers {
            type external;
            neighbor 10.0.0.1 {
                peer-as 65001;
                description "ISP-A";
            }
            neighbor 10.0.0.2 {
                peer-as 65002;
                description "ISP-B";
            }
        }
        group cdn-peers {
            type external;
            neighbor 192.168.1.1 {
                peer-as 13335;
                description "Cloudflare";
            }
            neighbor 192.168.1.2 {
                peer-as 15169;
                description "Google";
            }
        }
        group internal-peers {
            type internal;
            neighbor 172.16.0.1 {
                peer-as 64512;
            }
        }
    }
}
"""
    
    def test_discover_bgp_groups(self):
        """Test discovering BGP groups from configuration."""
        groups = self.inspector.discover_bgp_groups(self.sample_bgp_config)
        
        self.assertEqual(len(groups), 3)
        self.assertIn("external-peers", groups)
        self.assertIn("cdn-peers", groups)
        self.assertIn("internal-peers", groups)
        
        # Check AS numbers in groups
        self.assertEqual(groups["external-peers"], [65001, 65002])
        self.assertEqual(groups["cdn-peers"], [13335, 15169])
        self.assertEqual(groups["internal-peers"], [64512])
    
    def test_extract_peer_relationships(self):
        """Test extracting peer AS relationships."""
        relationships = self.inspector.extract_peer_relationships(self.sample_bgp_config)
        
        self.assertEqual(len(relationships), 5)
        self.assertEqual(relationships[65001], "external-peers")
        self.assertEqual(relationships[65002], "external-peers")
        self.assertEqual(relationships[13335], "cdn-peers")
        self.assertEqual(relationships[15169], "cdn-peers")
        self.assertEqual(relationships[64512], "internal-peers")
    
    def test_identify_bgp_version(self):
        """Test identifying BGP configuration version."""
        version = self.inspector.identify_bgp_version(self.sample_bgp_config)
        self.assertEqual(version, "junos")
        
        # Test with evolved version
        evolved_config = self.sample_bgp_config + "\njunos:changed"
        version = self.inspector.identify_bgp_version(evolved_config)
        self.assertEqual(version, "junos-evolved")
        
        # Test unknown version
        unknown_config = "some random configuration"
        version = self.inspector.identify_bgp_version(unknown_config)
        self.assertEqual(version, "unknown")
    
    def test_inspect_router(self):
        """Test complete router inspection."""
        profile = RouterProfile(
            hostname="test-router",
            ip_address="10.0.0.1",
            bgp_config=self.sample_bgp_config
        )
        
        result = self.inspector.inspect_router(profile)
        
        self.assertEqual(result.hostname, "test-router")
        self.assertEqual(len(result.bgp_groups), 3)
        self.assertEqual(result.total_as_numbers, 5)
        self.assertEqual(result.bgp_version, "junos")
        self.assertEqual(len(result.errors), 0)
        
        # Check that profile was updated
        self.assertEqual(len(profile.discovered_as_numbers), 5)
        self.assertEqual(len(profile.bgp_groups), 3)
    
    def test_inspect_router_no_config(self):
        """Test inspection with no BGP configuration."""
        profile = RouterProfile(
            hostname="test-router",
            ip_address="10.0.0.1",
            bgp_config=""
        )
        
        result = self.inspector.inspect_router(profile)
        
        self.assertFalse(result.bgp_groups)
        self.assertEqual(result.total_as_numbers, 0)
        self.assertEqual(len(result.errors), 1)
        self.assertIn("No BGP configuration", result.errors[0])
    
    def test_merge_discovery_results(self):
        """Test merging results from multiple routers."""
        results = [
            DiscoveryResult(
                hostname="router-01",
                bgp_groups={"external": [65001, 65002]},
                peer_relationships={65001: "external", 65002: "external"},
                total_as_numbers=2
            ),
            DiscoveryResult(
                hostname="router-02",
                bgp_groups={"external": [65002, 65003], "internal": [64512]},
                peer_relationships={65002: "external", 65003: "external", 64512: "internal"},
                total_as_numbers=3
            )
        ]
        
        merged = self.inspector.merge_discovery_results(results)
        
        self.assertEqual(merged["total_routers"], 2)
        self.assertEqual(merged["total_groups"], 2)  # external, internal
        self.assertEqual(merged["total_as_numbers"], 4)  # 65001, 65002, 65003, 64512
        
        # Check group mappings
        self.assertEqual(merged["group_as_mappings"]["external"], [65001, 65002, 65003])
        self.assertEqual(merged["group_as_mappings"]["internal"], [64512])
        
        # Check router associations
        self.assertIn("router-01", merged["all_groups"]["external"])
        self.assertIn("router-02", merged["all_groups"]["external"])
        self.assertIn("router-02", merged["all_groups"]["internal"])


class TestBGPConfigParser(unittest.TestCase):
    """Test the BGP configuration parser."""
    
    def setUp(self):
        """Set up test environment."""
        self.parser = BGPConfigParser()
        
        self.sample_config = """
        autonomous-system 65000;
        group external-peers {
            type external;
            import [ ACCEPT-ALL FILTER-BOGONS ];
            export [ ANNOUNCE-PREFIXES ];
            neighbor 10.0.0.1 {
                peer-as 65001;
                description "ISP Provider";
                import [ CUSTOMER-IN ];
                export [ CUSTOMER-OUT ];
            }
            neighbor 10.0.0.2 {
                peer-as 65002;
            }
        }
        """
    
    def test_parse_bgp_groups(self):
        """Test parsing BGP groups."""
        groups = self.parser.parse_bgp_groups(self.sample_config)
        
        self.assertEqual(len(groups), 1)
        group = groups[0]
        
        self.assertEqual(group.name, "external-peers")
        self.assertEqual(group.type, "external")
        self.assertEqual(len(group.neighbors), 2)
        self.assertEqual(group.peer_as_list, [65001, 65002])
    
    def test_parse_neighbors(self):
        """Test parsing neighbor configurations."""
        groups = self.parser.parse_bgp_groups(self.sample_config)
        neighbors = groups[0].neighbors
        
        self.assertEqual(len(neighbors), 2)
        
        # First neighbor
        n1 = neighbors[0]
        self.assertEqual(n1.address, "10.0.0.1")
        self.assertEqual(n1.peer_as, 65001)
        self.assertEqual(n1.description, "ISP Provider")
        self.assertEqual(n1.import_policy, ["CUSTOMER-IN"])
        self.assertEqual(n1.export_policy, ["CUSTOMER-OUT"])
        
        # Second neighbor
        n2 = neighbors[1]
        self.assertEqual(n2.address, "10.0.0.2")
        self.assertEqual(n2.peer_as, 65002)
    
    def test_extract_local_as(self):
        """Test extracting local AS number."""
        local_as = self.parser._extract_local_as(self.sample_config)
        self.assertEqual(local_as, 65000)
        
        # Test with local-as statement
        config_local_as = "local-as 64999;"
        local_as = self.parser._extract_local_as(config_local_as)
        self.assertEqual(local_as, 64999)
    
    def test_extract_as_numbers(self):
        """Test extracting all AS numbers."""
        as_numbers = self.parser.extract_as_numbers(self.sample_config)
        
        self.assertIn(65000, as_numbers)  # Local AS
        self.assertIn(65001, as_numbers)  # Peer AS
        self.assertIn(65002, as_numbers)  # Peer AS
    
    def test_extract_policies(self):
        """Test extracting import/export policies."""
        policies = self.parser.extract_policies(self.sample_config)
        
        # Group-level policies
        self.assertIn("ACCEPT-ALL", policies["import"])
        self.assertIn("FILTER-BOGONS", policies["import"])
        self.assertIn("ANNOUNCE-PREFIXES", policies["export"])
        
        # Neighbor-level policies
        self.assertIn("CUSTOMER-IN", policies["import"])
        self.assertIn("CUSTOMER-OUT", policies["export"])
    
    def test_identify_address_families(self):
        """Test identifying address families."""
        # IPv4 only config
        ipv4_config = "family inet { unicast; }"
        families = self.parser.identify_address_families(ipv4_config)
        self.assertIn("inet", families)
        
        # IPv6 config
        ipv6_config = "family inet6 { unicast; }"
        families = self.parser.identify_address_families(ipv6_config)
        self.assertIn("inet6", families)
        
        # Both families
        both_config = "family inet { unicast; } family inet6 { unicast; }"
        families = self.parser.identify_address_families(both_config)
        self.assertIn("inet", families)
        self.assertIn("inet6", families)


class TestYAMLGenerator(unittest.TestCase):
    """Test the YAML generator functionality."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.yaml_gen = YAMLGenerator(output_dir=self.temp_dir)
        
        # Create test router profiles
        self.profiles = [
            RouterProfile(
                hostname="router-01",
                ip_address="10.0.0.1",
                discovered_as_numbers={65001, 65002},
                bgp_groups={"external": [65001, 65002]}
            ),
            RouterProfile(
                hostname="router-02",
                ip_address="10.0.0.2",
                discovered_as_numbers={65002, 65003, 13335},
                bgp_groups={"external": [65002, 65003], "cdn": [13335]}
            )
        ]
    
    def test_generate_mappings(self):
        """Test generating YAML mappings from profiles."""
        mappings = self.yaml_gen.generate_mappings(self.profiles)
        
        # Check metadata
        self.assertEqual(mappings["_metadata"]["total_routers"], 2)
        self.assertEqual(mappings["_metadata"]["total_bgp_groups"], 2)
        self.assertEqual(mappings["_metadata"]["total_as_numbers"], 4)
        
        # Check routers
        self.assertIn("router-01", mappings["routers"])
        self.assertIn("router-02", mappings["routers"])
        
        # Check BGP groups
        self.assertIn("external", mappings["bgp_groups"])
        self.assertIn("cdn", mappings["bgp_groups"])
        
        # Check AS numbers
        self.assertIn(65001, mappings["as_numbers"])
        self.assertIn(13335, mappings["as_numbers"])
        
        # Check group to AS mapping
        self.assertEqual(mappings["group_to_as_mapping"]["external"], [65001, 65002, 65003])
        self.assertEqual(mappings["group_to_as_mapping"]["cdn"], [13335])
    
    def test_save_with_history(self):
        """Test saving mappings with history snapshot."""
        mappings = self.yaml_gen.generate_mappings(self.profiles)
        
        # Save mappings
        yaml_file = self.yaml_gen.save_with_history(mappings)
        
        self.assertTrue(yaml_file.exists())
        self.assertEqual(yaml_file.name, "bgp-mappings.yaml")
        
        # Check JSON file also created
        json_file = Path(self.temp_dir) / "bgp-mappings.json"
        self.assertTrue(json_file.exists())
        
        # Verify content
        with open(yaml_file, 'r') as f:
            content = f.read()
            self.assertIn("AUTO-GENERATED FILE", content)
            loaded = yaml.safe_load(f)
            self.assertEqual(loaded["_metadata"]["total_routers"], 2)
    
    def test_save_router_inventory(self):
        """Test saving router inventory."""
        inventory_file = self.yaml_gen.save_router_inventory(self.profiles)
        
        self.assertTrue(inventory_file.exists())
        self.assertEqual(inventory_file.name, "router-inventory.json")
        
        # Load and verify
        with open(inventory_file, 'r') as f:
            inventory = json.load(f)
        
        self.assertEqual(inventory["_metadata"]["total_routers"], 2)
        self.assertEqual(len(inventory["routers"]), 2)
        
        # Check router data
        router_01 = inventory["routers"][0]
        self.assertEqual(router_01["hostname"], "router-01")
        self.assertEqual(router_01["discovered_as_numbers"], [65001, 65002])
    
    def test_diff_mappings(self):
        """Test calculating differences between mappings."""
        old_mappings = {
            "routers": {
                "router-01": {"discovered_as_numbers": [65001]},
                "router-02": {"discovered_as_numbers": [65002]}
            },
            "bgp_groups": {
                "external": {"as_numbers": [65001, 65002]}
            },
            "as_numbers": {
                65001: {"routers": ["router-01"]},
                65002: {"routers": ["router-02"]}
            }
        }
        
        new_mappings = {
            "routers": {
                "router-01": {"discovered_as_numbers": [65001, 65003]},  # Added 65003
                "router-03": {"discovered_as_numbers": [65004]}  # New router
            },
            "bgp_groups": {
                "external": {"as_numbers": [65001, 65003]},  # Changed
                "internal": {"as_numbers": [65004]}  # New group
            },
            "as_numbers": {
                65001: {"routers": ["router-01"]},
                65003: {"routers": ["router-01"]},  # New AS
                65004: {"routers": ["router-03"]}   # New AS
            }
        }
        
        diff = self.yaml_gen.diff_mappings(old_mappings, new_mappings)
        
        # Check added items
        self.assertEqual(diff["added"]["routers"], ["router-03"])
        self.assertEqual(diff["added"]["groups"], ["internal"])
        self.assertEqual(diff["added"]["as_numbers"], [65003, 65004])
        
        # Check removed items
        self.assertEqual(diff["removed"]["routers"], ["router-02"])
        self.assertEqual(diff["removed"]["as_numbers"], [65002])
        
        # Check modified items
        self.assertIn("router-01", diff["modified"]["routers"])
        self.assertEqual(diff["modified"]["routers"]["router-01"]["added_as"], [65003])
        
        self.assertIn("Changes detected", diff["summary"])
    
    def test_history_snapshot_creation(self):
        """Test that history snapshots are created."""
        mappings = self.yaml_gen.generate_mappings(self.profiles)
        
        # Save twice to trigger history
        self.yaml_gen.save_with_history(mappings)
        self.yaml_gen.save_with_history(mappings)
        
        # Check history directory
        history_dir = Path(self.temp_dir) / "history"
        self.assertTrue(history_dir.exists())
        
        # Should have at least one snapshot
        snapshots = list(history_dir.glob("bgp-mappings_*.yaml"))
        self.assertGreater(len(snapshots), 0)
    
    def test_load_previous_mappings(self):
        """Test loading previous mappings."""
        # Initially no mappings
        previous = self.yaml_gen.load_previous_mappings()
        self.assertIsNone(previous)
        
        # Save mappings
        mappings = self.yaml_gen.generate_mappings(self.profiles)
        self.yaml_gen.save_with_history(mappings)
        
        # Now should load
        previous = self.yaml_gen.load_previous_mappings()
        self.assertIsNotNone(previous)
        self.assertEqual(previous["_metadata"]["total_routers"], 2)


class TestDiscoveryIntegration(unittest.TestCase):
    """Integration tests for discovery functionality."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        
    def test_end_to_end_discovery(self):
        """Test complete discovery workflow."""
        # Create components
        inspector = RouterInspector()
        yaml_gen = YAMLGenerator(output_dir=self.temp_dir)
        
        # Sample BGP configuration
        bgp_config = """
        protocols bgp {
            group peers {
                neighbor 10.0.0.1 {
                    peer-as 65001;
                }
            }
        }
        """
        
        # Create router profile
        profile = RouterProfile(
            hostname="test-router",
            ip_address="192.168.1.1",
            bgp_config=bgp_config
        )
        
        # Perform discovery
        result = inspector.inspect_router(profile)
        
        self.assertEqual(len(result.bgp_groups), 1)
        self.assertEqual(result.total_as_numbers, 1)
        
        # Generate and save mappings
        mappings = yaml_gen.generate_mappings([profile])
        yaml_file = yaml_gen.save_with_history(mappings)
        
        self.assertTrue(yaml_file.exists())
        
        # Verify generated files
        with open(yaml_file, 'r') as f:
            loaded = yaml.safe_load(f)
            self.assertEqual(loaded["_metadata"]["total_routers"], 1)
            self.assertIn("test-router", loaded["routers"])


if __name__ == "__main__":
    unittest.main()
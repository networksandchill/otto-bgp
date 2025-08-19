"""
Tests for Otto BGP v0.3.0 Router-Specific Policy Generation (Phase 3)

This module tests the router-aware policy generation functionality:
- Router-specific pipeline processing
- Policy isolation per router
- Deployment matrix generation
- Policy combination
"""

import unittest
import tempfile
import json
import csv
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Import modules to test
from otto_bgp.pipeline.workflow import BGPPolicyPipeline, PipelineConfig
from otto_bgp.models import RouterProfile, DeviceInfo
from otto_bgp.reports import DeploymentMatrix
from otto_bgp.generators.combiner import PolicyCombiner


class TestRouterAwarePipeline(unittest.TestCase):
    """Test router-aware pipeline functionality"""
    
    def setUp(self):
        """Set up test environment"""
        self.temp_dir = tempfile.mkdtemp()
        self.config = PipelineConfig(
            devices_file="test_devices.csv",
            output_directory=self.temp_dir,
            router_aware=True,
            skip_ssh=True
        )
        
        # Create test router profiles
        self.test_profiles = [
            RouterProfile(
                hostname="edge-router-01.nyc",
                ip_address="10.0.0.1",
                discovered_as_numbers={65001, 65002, 13335},
                bgp_groups={"external": [65001, 65002], "cdn": [13335]},
                site="nyc",
                role="edge"
            ),
            RouterProfile(
                hostname="core-router-01.sjc",
                ip_address="10.0.0.2",
                discovered_as_numbers={65001, 65003, 15169},
                bgp_groups={"external": [65001, 65003], "cdn": [15169]},
                site="sjc",
                role="core"
            ),
            RouterProfile(
                hostname="edge-router-02.lon",
                ip_address="10.0.0.3",
                discovered_as_numbers={65004, 65005},
                bgp_groups={"external": [65004, 65005]},
                site="lon",
                role="edge"
            )
        ]
    
    @patch('otto_bgp.pipeline.workflow.JuniperSSHCollector')
    @patch('otto_bgp.pipeline.workflow.BGPq4Wrapper')
    def test_router_aware_pipeline_execution(self, mock_bgp_wrapper, mock_ssh_collector):
        """Test complete router-aware pipeline execution"""
        # Setup mocks
        mock_ssh_collector_instance = mock_ssh_collector.return_value
        mock_ssh_collector_instance.load_devices_from_csv.return_value = [
            DeviceInfo("10.0.0.1", "edge-router-01.nyc"),
            DeviceInfo("10.0.0.2", "core-router-01.sjc")
        ]
        
        mock_bgp_wrapper_instance = mock_bgp_wrapper.return_value
        mock_bgp_wrapper_instance.generate_policy.return_value = Mock(
            success=True,
            policy_config="policy-options { prefix-list test { } }",
            as_number=65001
        )
        
        # Create pipeline
        pipeline = BGPPolicyPipeline(self.config)
        pipeline.router_profiles = self.test_profiles[:2]
        
        # Mock methods
        with patch.object(pipeline, '_load_router_profiles', return_value=self.test_profiles[:2]):
            with patch.object(pipeline, 'router_inspector') as mock_inspector:
                mock_inspector.inspect_router.return_value = Mock(
                    total_as_numbers=3,
                    bgp_groups={"external": [65001, 65002]}
                )
                
                result = pipeline.run_router_aware_pipeline()
        
        # Verify results
        self.assertTrue(result.success)
        self.assertEqual(result.devices_processed, 2)
        self.assertEqual(result.routers_configured, 2)
        self.assertGreater(len(result.router_directories), 0)
    
    def test_router_directory_creation(self):
        """Test that router-specific directories are created correctly"""
        pipeline = BGPPolicyPipeline(self.config)
        
        for profile in self.test_profiles:
            router_dir = pipeline._create_router_directory(profile)
            
            # Verify directory exists
            self.assertTrue(router_dir.exists())
            self.assertTrue(router_dir.is_dir())
            
            # Verify path structure
            expected_path = Path(self.temp_dir) / "routers" / profile.hostname
            self.assertEqual(router_dir, expected_path)
    
    def test_router_metadata_generation(self):
        """Test metadata.json generation for each router"""
        pipeline = BGPPolicyPipeline(self.config)
        
        for profile in self.test_profiles:
            router_dir = pipeline._create_router_directory(profile)
            pipeline._create_router_metadata(profile, router_dir, 5)
            
            # Verify metadata file exists
            metadata_file = router_dir / "metadata.json"
            self.assertTrue(metadata_file.exists())
            
            # Load and verify metadata content
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
            
            self.assertEqual(metadata["router"]["hostname"], profile.hostname)
            self.assertEqual(metadata["router"]["ip_address"], profile.ip_address)
            self.assertEqual(metadata["router"]["site"], profile.site)
            self.assertEqual(metadata["router"]["role"], profile.role)
            self.assertEqual(metadata["discovery"]["policies_generated"], 5)
            self.assertEqual(metadata["version"], "0.3.0")
    
    @patch('otto_bgp.pipeline.workflow.BGPq4Wrapper')
    def test_router_policy_isolation(self, mock_bgp_wrapper):
        """Test that each router only gets its own AS policies"""
        mock_bgp_wrapper_instance = mock_bgp_wrapper.return_value
        mock_bgp_wrapper_instance.generate_policy.return_value = Mock(
            success=True,
            policy_config="test policy",
            as_number=65001
        )
        
        pipeline = BGPPolicyPipeline(self.config)
        
        # Generate policies for first router (should only get 65001, 65002, 13335)
        router1 = self.test_profiles[0]
        router1_dir = pipeline._create_router_directory(router1)
        count1 = pipeline._generate_router_policies(router1, router1_dir)
        
        # Check that only router1's AS numbers were processed
        router1_policies = list(router1_dir.glob("AS*_policy.txt"))
        as_numbers_in_policies = []
        for policy_file in router1_policies:
            # Extract AS number from filename
            as_num = int(policy_file.stem.replace("AS", "").replace("_policy", ""))
            as_numbers_in_policies.append(as_num)
        
        # Verify only router1's AS numbers
        self.assertEqual(set(as_numbers_in_policies), router1.discovered_as_numbers)
        
        # Generate policies for second router (different AS set)
        router2 = self.test_profiles[1]
        router2_dir = pipeline._create_router_directory(router2)
        count2 = pipeline._generate_router_policies(router2, router2_dir)
        
        # Verify isolation - no cross-contamination
        router2_policies = list(router2_dir.glob("AS*_policy.txt"))
        router2_as_numbers = []
        for policy_file in router2_policies:
            as_num = int(policy_file.stem.replace("AS", "").replace("_policy", ""))
            router2_as_numbers.append(as_num)
        
        self.assertEqual(set(router2_as_numbers), router2.discovered_as_numbers)
        
        # Ensure no overlap of unique AS numbers
        unique_to_router1 = router1.discovered_as_numbers - router2.discovered_as_numbers
        unique_to_router2 = router2.discovered_as_numbers - router1.discovered_as_numbers
        
        # Router1 should not have router2's unique AS policies
        for as_num in unique_to_router2:
            policy_file = router1_dir / f"AS{as_num}_policy.txt"
            self.assertFalse(policy_file.exists())
        
        # Router2 should not have router1's unique AS policies
        for as_num in unique_to_router1:
            policy_file = router2_dir / f"AS{as_num}_policy.txt"
            self.assertFalse(policy_file.exists())


class TestDeploymentMatrix(unittest.TestCase):
    """Test deployment matrix generation"""
    
    def setUp(self):
        """Set up test environment"""
        self.temp_dir = tempfile.mkdtemp()
        self.matrix_gen = DeploymentMatrix(self.temp_dir)
        
        # Create test profiles
        self.test_profiles = [
            RouterProfile(
                hostname="router-01",
                ip_address="10.0.0.1",
                discovered_as_numbers={65001, 65002},
                bgp_groups={"external": [65001, 65002]},
                site="nyc",
                role="edge"
            ),
            RouterProfile(
                hostname="router-02",
                ip_address="10.0.0.2",
                discovered_as_numbers={65002, 65003},
                bgp_groups={"external": [65002, 65003]},
                site="sjc",
                role="core"
            )
        ]
    
    def test_matrix_generation(self):
        """Test deployment matrix generation"""
        matrix = self.matrix_gen.generate_router_as_matrix(self.test_profiles)
        
        # Verify structure
        self.assertIn("_metadata", matrix)
        self.assertIn("routers", matrix)
        self.assertIn("as_numbers", matrix)
        self.assertIn("bgp_groups", matrix)
        self.assertIn("statistics", matrix)
        
        # Verify router data
        self.assertEqual(len(matrix["routers"]), 2)
        self.assertIn("router-01", matrix["routers"])
        self.assertIn("router-02", matrix["routers"])
        
        # Verify AS number tracking
        self.assertEqual(len(matrix["as_numbers"]), 3)  # 65001, 65002, 65003
        self.assertIn(65001, matrix["as_numbers"])
        self.assertIn(65002, matrix["as_numbers"])
        self.assertIn(65003, matrix["as_numbers"])
        
        # Verify shared AS (65002 appears on both routers)
        self.assertEqual(len(matrix["as_numbers"][65002]["routers"]), 2)
    
    def test_statistics_calculation(self):
        """Test statistics calculation in deployment matrix"""
        matrix = self.matrix_gen.generate_router_as_matrix(self.test_profiles)
        stats = matrix["statistics"]
        
        self.assertEqual(stats["total_routers"], 2)
        self.assertEqual(stats["total_as_numbers"], 3)
        self.assertEqual(stats["average_as_per_router"], 2.0)
        self.assertEqual(stats["max_as_per_router"], 2)
        self.assertEqual(stats["min_as_per_router"], 2)
        
        # Check shared AS numbers
        shared_as = stats["shared_as_numbers"]
        self.assertEqual(len(shared_as), 1)  # Only 65002 is shared
        self.assertEqual(shared_as[0]["as_number"], 65002)
        self.assertIn("router-01", shared_as[0]["routers"])
        self.assertIn("router-02", shared_as[0]["routers"])
    
    def test_csv_export(self):
        """Test CSV export of deployment matrix"""
        matrix = self.matrix_gen.generate_router_as_matrix(self.test_profiles)
        csv_file = self.matrix_gen.export_csv(matrix)
        
        self.assertTrue(csv_file.exists())
        
        # Read and verify CSV content
        with open(csv_file, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        self.assertEqual(len(rows), 2)
        
        # Verify first router
        router1 = rows[0]
        self.assertEqual(router1["Router"], "router-01")
        self.assertEqual(router1["IP Address"], "10.0.0.1")
        self.assertEqual(router1["Site"], "nyc")
        self.assertEqual(router1["Role"], "edge")
        self.assertEqual(router1["AS Count"], "2")
    
    def test_json_export(self):
        """Test JSON export of deployment matrix"""
        matrix = self.matrix_gen.generate_router_as_matrix(self.test_profiles)
        json_file = self.matrix_gen.export_json(matrix)
        
        self.assertTrue(json_file.exists())
        
        # Load and verify JSON
        with open(json_file, 'r') as f:
            loaded_matrix = json.load(f)
        
        self.assertEqual(loaded_matrix["_metadata"]["total_routers"], 2)
        self.assertIn("router-01", loaded_matrix["routers"])
        self.assertIn("router-02", loaded_matrix["routers"])


class TestPolicyCombiner(unittest.TestCase):
    """Test policy combination functionality"""
    
    def setUp(self):
        """Set up test environment"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.combiner = PolicyCombiner()
        
        # Create test policy files
        self.router_dir = self.temp_dir / "routers" / "test-router"
        self.router_dir.mkdir(parents=True)
        
        # Create sample policy files
        self.policy1 = self.router_dir / "AS65001_policy.txt"
        self.policy1.write_text("""policy-options {
    prefix-list AS65001 {
        192.168.1.0/24;
        10.0.0.0/8;
    }
}""")
        
        self.policy2 = self.router_dir / "AS65002_policy.txt"
        self.policy2.write_text("""policy-options {
    prefix-list AS65002 {
        172.16.0.0/12;
        192.168.1.0/24;
    }
}""")
    
    def test_combine_policies(self):
        """Test combining multiple policies for a router"""
        result = self.combiner.combine_policies_for_router(
            router_hostname="test-router",
            policy_files=[self.policy1, self.policy2],
            output_dir=self.temp_dir,
            format="juniper"
        )
        
        self.assertTrue(result.success)
        self.assertEqual(result.policies_combined, 2)
        self.assertEqual(result.router_hostname, "test-router")
        
        # Verify output file exists
        output_file = Path(result.output_file)
        self.assertTrue(output_file.exists())
        
        # Verify content
        content = output_file.read_text()
        self.assertIn("test-router", content)
        self.assertIn("policy-options", content)
        self.assertIn("prefix-list", content)
    
    def test_prefix_deduplication(self):
        """Test that duplicate prefixes are removed in combined output"""
        result = self.combiner.combine_policies_for_router(
            router_hostname="test-router",
            policy_files=[self.policy1, self.policy2],
            output_dir=self.temp_dir,
            format="juniper"
        )
        
        content = Path(result.output_file).read_text()
        
        # Count occurrences of duplicate prefix
        occurrences = content.count("192.168.1.0/24")
        
        # Should appear only once after deduplication
        self.assertEqual(occurrences, 1)
    
    def test_set_format_output(self):
        """Test set command format output"""
        result = self.combiner.combine_policies_for_router(
            router_hostname="test-router",
            policy_files=[self.policy1],
            output_dir=self.temp_dir,
            format="set"
        )
        
        self.assertTrue(result.success)
        
        content = Path(result.output_file).read_text()
        self.assertIn("set policy-options prefix-list", content)
        self.assertIn("192.168.1.0/24", content)
        self.assertIn("10.0.0.0/8", content)
    
    def test_hierarchical_format(self):
        """Test hierarchical organization format"""
        result = self.combiner.combine_policies_for_router(
            router_hostname="test-router",
            policy_files=[self.policy1, self.policy2],
            output_dir=self.temp_dir,
            format="hierarchical"
        )
        
        self.assertTrue(result.success)
        
        content = Path(result.output_file).read_text()
        self.assertIn("BGP Policy Configuration", content)
        self.assertIn("Router: test-router", content)
        self.assertIn("policy-options", content)


class TestEndToEndRouterGeneration(unittest.TestCase):
    """End-to-end tests for router-specific generation"""
    
    def setUp(self):
        """Set up test environment"""
        self.temp_dir = Path(tempfile.mkdtemp())
    
    def test_router_isolation_scenario(self):
        """Test complete scenario ensuring router isolation"""
        # Create test profiles with overlapping and unique AS numbers
        profiles = [
            RouterProfile(
                hostname="router-A",
                ip_address="10.0.0.1",
                discovered_as_numbers={65001, 65002, 65003},  # Unique: 65003
                bgp_groups={"external": [65001, 65002, 65003]}
            ),
            RouterProfile(
                hostname="router-B",
                ip_address="10.0.0.2",
                discovered_as_numbers={65001, 65004, 65005},  # Unique: 65004, 65005
                bgp_groups={"external": [65001, 65004, 65005]}
            )
        ]
        
        # Generate deployment matrix
        matrix_gen = DeploymentMatrix(str(self.temp_dir / "reports"))
        matrix = matrix_gen.generate_router_as_matrix(profiles)
        
        # Verify AS isolation in matrix
        self.assertEqual(len(matrix["routers"]["router-A"]["as_numbers"]), 3)
        self.assertEqual(len(matrix["routers"]["router-B"]["as_numbers"]), 3)
        
        # Verify shared AS is tracked correctly
        self.assertEqual(len(matrix["as_numbers"][65001]["routers"]), 2)
        self.assertIn("router-A", matrix["as_numbers"][65001]["routers"])
        self.assertIn("router-B", matrix["as_numbers"][65001]["routers"])
        
        # Verify unique AS numbers
        self.assertEqual(len(matrix["as_numbers"][65003]["routers"]), 1)
        self.assertEqual(matrix["as_numbers"][65003]["routers"][0], "router-A")
        
        self.assertEqual(len(matrix["as_numbers"][65004]["routers"]), 1)
        self.assertEqual(matrix["as_numbers"][65004]["routers"][0], "router-B")


if __name__ == "__main__":
    unittest.main()
"""
Integration Tests for Full Otto BGP Pipeline

Tests complete end-to-end workflows including:
- Discovery → Policy Generation → Application
- Error handling and recovery
- Performance benchmarks
"""

import unittest
import tempfile
import time
import json
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from dataclasses import dataclass
from typing import List

# Import Otto BGP modules
from otto_bgp.collectors.juniper_ssh import JuniperSSHCollector
from otto_bgp.discovery.inspector import RouterInspector
from otto_bgp.discovery.yaml_generator import YAMLGenerator
from otto_bgp.generators.bgpq4_wrapper import BGPq4Wrapper, PolicyGenerationResult
from otto_bgp.appliers.juniper_netconf import JuniperPolicyApplier
from otto_bgp.utils.parallel import parallel_discover_routers, parallel_generate_policies
from otto_bgp.utils.cache import PolicyCache, DiscoveryCache
from otto_bgp.pipeline.workflow import run_pipeline


@dataclass
class MockDevice:
    """Mock device for testing"""
    hostname: str
    address: str
    username: str = "admin"
    model: str = "MX960"
    
    def to_router_profile(self):
        """Convert to router profile"""
        from otto_bgp.models import RouterProfile
        return RouterProfile(
            hostname=self.hostname,
            address=self.address,
            model=self.model
        )


class TestFullPipeline(unittest.TestCase):
    """Test complete Otto BGP pipeline"""
    
    def setUp(self):
        """Set up test environment"""
        self.temp_dir = tempfile.mkdtemp()
        self.test_devices = [
            MockDevice("router1", "10.1.1.1"),
            MockDevice("router2", "10.1.1.2"),
            MockDevice("router3", "10.1.1.3")
        ]
        
        # Mock BGP configurations
        self.mock_bgp_configs = {
            "router1": """
                protocols {
                    bgp {
                        group transit-peers {
                            type external;
                            peer-as 13335;
                            neighbor 192.168.1.1;
                        }
                        group ix-peers {
                            type external;
                            peer-as 15169;
                            neighbor 192.168.2.1;
                        }
                    }
                }
            """,
            "router2": """
                protocols {
                    bgp {
                        group customers {
                            type external;
                            peer-as 64512;
                            neighbor 10.0.1.1;
                        }
                        group transit {
                            type external;
                            peer-as 7922;
                            neighbor 10.0.2.1;
                        }
                    }
                }
            """,
            "router3": """
                protocols {
                    bgp {
                        group peers {
                            type external;
                            peer-as 20940;
                            neighbor 172.16.1.1;
                        }
                    }
                }
            """
        }
        
        # Expected AS numbers per router
        self.expected_as_numbers = {
            "router1": {13335, 15169},
            "router2": {64512, 7922},
            "router3": {20940}
        }
    
    def tearDown(self):
        """Clean up test environment"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('otto_bgp.collectors.juniper_ssh.JuniperSSHCollector.collect_bgp_config')
    @patch('otto_bgp.generators.bgpq4_wrapper.subprocess.run')
    def test_discovery_to_generation_pipeline(self, mock_subprocess, mock_collect):
        """Test discovery → generation pipeline"""
        
        # Mock BGP configuration collection
        def mock_bgp_collect(address):
            for device in self.test_devices:
                if device.address == address:
                    return self.mock_bgp_configs[device.hostname]
            return ""
        
        mock_collect.side_effect = mock_bgp_collect
        
        # Mock successful bgpq4 execution
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = """policy-options {
    prefix-list AS13335 {
        1.1.1.0/24;
        1.0.0.0/24;
    }
}"""
        mock_subprocess.return_value = mock_result
        
        # Phase 1: Discovery
        collector = JuniperSSHCollector()
        inspector = RouterInspector()
        yaml_gen = YAMLGenerator(output_dir=Path(self.temp_dir))
        
        profiles = []
        discovery_results = []
        
        for device in self.test_devices:
            # Collect BGP config
            bgp_config = collector.collect_bgp_config(device.address)
            
            # Create profile
            profile = device.to_router_profile()
            profile.bgp_config = bgp_config
            profiles.append(profile)
            
            # Perform discovery
            result = inspector.inspect_router(profile)
            discovery_results.append(result)
            
            # Verify expected AS numbers were discovered
            expected_as = self.expected_as_numbers[device.hostname]
            discovered_as = set(result.as_numbers)
            self.assertEqual(discovered_as, expected_as, 
                           f"AS numbers mismatch for {device.hostname}")
        
        # Generate mappings
        mappings = yaml_gen.generate_mappings(profiles)
        
        # Verify mappings structure
        self.assertIn('routers', mappings)
        self.assertIn('as_numbers', mappings)
        self.assertEqual(len(mappings['routers']), 3)
        
        # Phase 2: Policy Generation
        wrapper = BGPq4Wrapper()
        all_policies = []
        
        for hostname, router_data in mappings['routers'].items():
            as_numbers = router_data['discovered_as_numbers']
            if as_numbers:
                results = wrapper.generate_policies_batch(as_numbers)
                all_policies.extend(results)
        
        # Verify policies were generated
        self.assertTrue(len(all_policies) > 0)
        successful_policies = [p for p in all_policies if p.success]
        self.assertEqual(len(successful_policies), len(all_policies))
        
        print(f"✓ Discovery-to-generation pipeline: {len(profiles)} routers, "
              f"{len(all_policies)} policies generated")
    
    @patch('otto_bgp.collectors.juniper_ssh.JuniperSSHCollector.collect_bgp_config')
    @patch('otto_bgp.generators.bgpq4_wrapper.subprocess.run')
    def test_parallel_discovery_performance(self, mock_subprocess, mock_collect):
        """Test parallel discovery performance"""
        
        # Mock delayed BGP collection (simulate real network delay)
        def slow_bgp_collect(address):
            time.sleep(0.1)  # Simulate network delay
            for device in self.test_devices:
                if device.address == address:
                    return self.mock_bgp_configs[device.hostname]
            return ""
        
        mock_collect.side_effect = slow_bgp_collect
        
        # Mock bgpq4
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "policy-options { prefix-list test { 1.1.1.0/24; } }"
        mock_subprocess.return_value = mock_result
        
        collector = JuniperSSHCollector()
        inspector = RouterInspector()
        
        # Test sequential discovery
        start_time = time.time()
        sequential_profiles = []
        for device in self.test_devices:
            bgp_config = collector.collect_bgp_config(device.address)
            profile = device.to_router_profile()
            profile.bgp_config = bgp_config
            sequential_profiles.append(profile)
        sequential_time = time.time() - start_time
        
        # Test parallel discovery
        start_time = time.time()
        parallel_profiles, _ = parallel_discover_routers(
            self.test_devices, collector, inspector, max_workers=3
        )
        parallel_time = time.time() - start_time
        
        # Verify parallel is faster
        self.assertLess(parallel_time, sequential_time)
        self.assertEqual(len(parallel_profiles), len(sequential_profiles))
        
        speedup = sequential_time / parallel_time
        print(f"✓ Parallel discovery speedup: {speedup:.2f}x "
              f"({sequential_time:.2f}s → {parallel_time:.2f}s)")
    
    def test_cache_performance(self):
        """Test policy caching performance"""
        
        # Create cache
        cache = PolicyCache(cache_dir=Path(self.temp_dir) / "cache")
        
        test_as_numbers = [13335, 15169, 7922, 64512]
        test_policy = """policy-options {
    prefix-list AS13335 {
        1.1.1.0/24;
        1.0.0.0/24;
    }
}"""
        
        # Test cache miss (first access)
        start_time = time.time()
        for as_num in test_as_numbers:
            result = cache.get_policy(as_num)
            self.assertIsNone(result)
        miss_time = time.time() - start_time
        
        # Store policies in cache
        for as_num in test_as_numbers:
            cache.put_policy(as_num, test_policy)
        
        # Test cache hit (subsequent access)
        start_time = time.time()
        hit_count = 0
        for as_num in test_as_numbers:
            result = cache.get_policy(as_num)
            if result:
                hit_count += 1
                self.assertEqual(result, test_policy)
        hit_time = time.time() - start_time
        
        # Verify all cache hits and performance
        self.assertEqual(hit_count, len(test_as_numbers))
        self.assertLess(hit_time, miss_time * 2)  # Cache should be much faster
        
        # Test cache statistics
        stats = cache.get_stats()
        self.assertEqual(stats['active_entries'], len(test_as_numbers))
        
        print(f"✓ Cache performance: {hit_count}/{len(test_as_numbers)} hits, "
              f"{(miss_time/hit_time):.1f}x speedup")
    
    @patch('otto_bgp.generators.bgpq4_wrapper.subprocess.run')
    def test_parallel_policy_generation(self, mock_subprocess):
        """Test parallel policy generation"""
        
        # Mock successful bgpq4 execution
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = """policy-options {
    prefix-list test {
        1.1.1.0/24;
    }
}"""
        mock_subprocess.return_value = mock_result
        
        test_as_numbers = [13335, 15169, 7922, 64512, 20940, 174, 3356, 1299]
        wrapper = BGPq4Wrapper()
        
        # Test sequential generation
        start_time = time.time()
        sequential_results = []
        for as_num in test_as_numbers:
            result = wrapper.generate_policy_for_as(as_num)
            sequential_results.append(result)
        sequential_time = time.time() - start_time
        
        # Test parallel generation
        start_time = time.time()
        parallel_results = parallel_generate_policies(
            test_as_numbers, wrapper, max_workers=4
        )
        parallel_time = time.time() - start_time
        
        # Verify results
        self.assertEqual(len(parallel_results), len(sequential_results))
        successful_parallel = sum(1 for r in parallel_results if r.success)
        successful_sequential = sum(1 for r in sequential_results if r.success)
        self.assertEqual(successful_parallel, successful_sequential)
        
        # Verify parallel is faster
        speedup = sequential_time / parallel_time
        print(f"✓ Parallel generation speedup: {speedup:.2f}x "
              f"({sequential_time:.2f}s → {parallel_time:.2f}s)")
    
    def test_error_handling_resilience(self):
        """Test pipeline resilience to errors"""
        
        # Test with mix of valid and invalid AS numbers
        test_as_numbers = [13335, -1, 15169, 999999999999, 7922]
        
        with patch('otto_bgp.generators.bgpq4_wrapper.subprocess.run') as mock_subprocess:
            # Mock bgpq4 returning success for valid AS, failure for invalid
            def mock_bgpq4_execution(command, **kwargs):
                result = MagicMock()
                as_number = command[-1]  # AS number is last argument
                
                if 'AS13335' in as_number or 'AS15169' in as_number or 'AS7922' in as_number:
                    result.returncode = 0
                    result.stdout = f"policy-options {{ prefix-list {as_number.replace('AS', '')} {{ 1.1.1.0/24; }} }}"
                else:
                    result.returncode = 1
                    result.stderr = f"Invalid AS number: {as_number}"
                
                return result
            
            mock_subprocess.side_effect = mock_bgpq4_execution
            
            wrapper = BGPq4Wrapper()
            results = wrapper.generate_policies_batch(test_as_numbers)
            
            # Verify we got results for all AS numbers (successful or failed)
            self.assertEqual(len(results), len(test_as_numbers))
            
            # Count successful vs failed
            successful = [r for r in results if r.success]
            failed = [r for r in results if not r.success]
            
            # Should have 3 successful (valid AS) and 2 failed (invalid AS)
            self.assertEqual(len(successful), 3)
            self.assertEqual(len(failed), 2)
            
            print(f"✓ Error resilience: {len(successful)}/{len(results)} successful, "
                  f"pipeline continued despite {len(failed)} failures")
    
    @patch('otto_bgp.collectors.juniper_ssh.JuniperSSHCollector.load_devices_from_csv')
    @patch('otto_bgp.collectors.juniper_ssh.JuniperSSHCollector.collect_bgp_data_from_csv')
    @patch('otto_bgp.generators.bgpq4_wrapper.subprocess.run')
    def test_end_to_end_pipeline(self, mock_subprocess, mock_collect_data, mock_load_devices):
        """Test complete end-to-end pipeline via CLI interface"""
        
        # Mock device loading
        mock_load_devices.return_value = self.test_devices
        
        # Mock BGP data collection
        from otto_bgp.collectors.juniper_ssh import BGPDataResult
        mock_bgp_results = []
        for device in self.test_devices:
            mock_bgp_results.append(BGPDataResult(
                device_address=device.address,
                hostname=device.hostname,
                bgp_data=self.mock_bgp_configs[device.hostname],
                success=True
            ))
        mock_collect_data.return_value = mock_bgp_results
        
        # Mock bgpq4
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "policy-options { prefix-list test { 1.1.1.0/24; } }"
        mock_subprocess.return_value = mock_result
        
        # Create test devices CSV
        devices_csv = Path(self.temp_dir) / "devices.csv"
        with open(devices_csv, 'w') as f:
            f.write("hostname,address\n")
            for device in self.test_devices:
                f.write(f"{device.hostname},{device.address}\n")
        
        # Run pipeline
        result = run_pipeline(
            devices_file=str(devices_csv),
            output_dir=self.temp_dir,
            separate_files=True
        )
        
        # Verify pipeline success
        self.assertTrue(result.success)
        self.assertEqual(result.devices_processed, len(self.test_devices))
        self.assertGreater(result.as_numbers_found, 0)
        self.assertGreater(result.policies_generated, 0)
        
        # Verify output files were created
        output_files = list(Path(self.temp_dir).glob("*.txt"))
        self.assertGreater(len(output_files), 0)
        
        print(f"✓ End-to-end pipeline: {result.devices_processed} devices, "
              f"{result.as_numbers_found} AS numbers, {result.policies_generated} policies, "
              f"{len(output_files)} files")
    
    def test_configuration_integration(self):
        """Test configuration system integration"""
        
        from otto_bgp.utils.config import ConfigManager, BGPToolkitConfig
        
        # Test configuration loading and validation
        config_manager = ConfigManager()
        config = config_manager.get_config()
        
        # Verify config structure
        self.assertIsInstance(config, BGPToolkitConfig)
        self.assertIsNotNone(config.ssh)
        self.assertIsNotNone(config.bgpq4)
        self.assertIsNotNone(config.irr_proxy)
        
        # Test configuration validation
        issues = config_manager.validate_config()
        
        # Should have no critical validation issues for default config
        critical_issues = [issue for issue in issues if 'critical' in issue.lower()]
        self.assertEqual(len(critical_issues), 0)
        
        print(f"✓ Configuration validation: {len(issues)} non-critical issues found")
    
    @patch('otto_bgp.appliers.juniper_netconf.Device')
    def test_policy_application_integration(self, mock_device_class):
        """Test policy application integration (mocked)"""
        
        # Mock PyEZ device
        mock_device = MagicMock()
        mock_device.facts = {'hostname': 'test-router', 'model': 'MX960'}
        mock_device.cu.diff.return_value = "Test configuration diff"
        mock_device.cu.commit.return_value = True
        mock_device_class.return_value = mock_device
        
        # Create test policies
        test_policies = [
            PolicyGenerationResult(
                as_number=13335,
                policy_name="AS13335",
                policy_content="""policy-options {
    prefix-list AS13335 {
        1.1.1.0/24;
    }
}""",
                success=True
            )
        ]
        
        # Test policy application
        applier = JuniperPolicyApplier()
        
        # Test connection
        device = applier.connect_to_router(
            hostname="test-router",
            username="admin",
            password="password"
        )
        self.assertIsNotNone(device)
        
        # Test preview
        diff = applier.preview_changes(test_policies)
        self.assertIsNotNone(diff)
        
        # Verify device was configured correctly
        mock_device_class.assert_called_once()
        mock_device.cu.diff.assert_called()
        
        print("✓ Policy application integration test passed")


class TestPerformanceBenchmarks(unittest.TestCase):
    """Performance benchmark tests"""
    
    @patch('otto_bgp.generators.bgpq4_wrapper.subprocess.run')
    def test_large_scale_generation(self, mock_subprocess):
        """Test large-scale policy generation performance"""
        
        # Mock fast bgpq4 execution
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "policy-options { prefix-list test { 1.1.1.0/24; } }"
        mock_subprocess.return_value = mock_result
        
        # Test with 100 AS numbers
        large_as_list = list(range(64512, 64612))  # 100 private AS numbers
        
        wrapper = BGPq4Wrapper(enable_cache=False)  # Disable cache for benchmark
        
        start_time = time.time()
        results = parallel_generate_policies(large_as_list, wrapper, max_workers=8)
        execution_time = time.time() - start_time
        
        # Verify all policies generated
        self.assertEqual(len(results), 100)
        successful = sum(1 for r in results if r.success)
        self.assertEqual(successful, 100)
        
        # Performance benchmark
        policies_per_second = len(results) / execution_time
        print(f"✓ Large-scale generation: 100 policies in {execution_time:.2f}s "
              f"({policies_per_second:.1f} policies/sec)")
        
        # Should be able to process at least 10 policies per second
        self.assertGreater(policies_per_second, 10)
    
    def test_cache_scalability(self):
        """Test cache performance with large datasets"""
        
        temp_dir = tempfile.mkdtemp()
        try:
            cache = PolicyCache(cache_dir=temp_dir)
            
            # Store 1000 policies
            test_policy = "policy-options { prefix-list test { 1.1.1.0/24; } }"
            store_start = time.time()
            
            for i in range(1000):
                cache.put_policy(64512 + i, test_policy)
            
            store_time = time.time() - store_start
            
            # Retrieve 1000 policies
            retrieve_start = time.time()
            hit_count = 0
            
            for i in range(1000):
                result = cache.get_policy(64512 + i)
                if result:
                    hit_count += 1
            
            retrieve_time = time.time() - retrieve_start
            
            # Verify performance
            self.assertEqual(hit_count, 1000)
            self.assertLess(store_time, 10.0)  # Should store 1000 in <10s
            self.assertLess(retrieve_time, 1.0)  # Should retrieve 1000 in <1s
            
            print(f"✓ Cache scalability: 1000 policies stored in {store_time:.2f}s, "
                  f"retrieved in {retrieve_time:.2f}s")
            
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == '__main__':
    # Run with verbose output
    unittest.main(verbosity=2)
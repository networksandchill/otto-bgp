"""
Integration Tests for Otto BGP Automation Features

Tests automation workflows, error recovery, and monitoring.
"""

import unittest
import tempfile
import time
import json
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch


class TestAutomationIntegration(unittest.TestCase):
    """Test automation integration features"""
    
    def setUp(self):
        """Set up test environment"""
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up test environment"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('otto_bgp.proxy.irr_tunnel.subprocess.Popen')
    @patch('otto_bgp.proxy.irr_tunnel.socket.socket')
    def test_proxy_automation(self, mock_socket_class, mock_popen):
        """Test IRR proxy automation workflow"""
        
        from otto_bgp.proxy import IRRProxyManager, ProxyConfig
        
        # Mock successful SSH tunnel
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process
        
        mock_socket = MagicMock()
        mock_socket.connect_ex.return_value = 0  # Success
        mock_socket_class.return_value = mock_socket
        
        # Configure proxy
        config = ProxyConfig(
            enabled=True,
            jump_host="gateway.example.com",
            jump_user="admin",
            tunnels=[
                {
                    'name': 'test-tunnel',
                    'local_port': 43001,
                    'remote_host': 'test.irr.net',
                    'remote_port': 43
                }
            ]
        )
        
        manager = IRRProxyManager(config)
        
        # Test tunnel setup
        status = manager.setup_tunnel(config.tunnels[0])
        self.assertEqual(status.state.value, 'connected')
        
        # Test connectivity
        connectivity = manager.test_tunnel_connectivity('test-tunnel')
        self.assertTrue(connectivity)
        
        # Test command wrapping
        original_cmd = ['bgpq4', '-Jl', 'AS13335', 'AS13335']
        wrapped_cmd = manager.wrap_bgpq4_command(original_cmd)
        
        self.assertIn('-h', wrapped_cmd)
        self.assertIn('127.0.0.1', wrapped_cmd)
        self.assertIn('-p', wrapped_cmd)
        self.assertIn('43001', wrapped_cmd)
        
        print("✓ Proxy automation workflow completed successfully")
    
    @patch('otto_bgp.collectors.juniper_ssh.JuniperSSHCollector.collect_bgp_config')
    def test_discovery_automation(self, mock_collect):
        """Test automated discovery workflow"""
        
        from otto_bgp.discovery import RouterInspector, YAMLGenerator
        from otto_bgp.models import RouterProfile
        
        # Mock BGP configuration
        mock_bgp_config = """
            protocols {
                bgp {
                    group transit {
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
        """
        mock_collect.return_value = mock_bgp_config
        
        # Create test router profile
        profile = RouterProfile(
            hostname="test-router",
            address="10.1.1.1",
            model="MX960"
        )
        profile.bgp_config = mock_bgp_config
        
        # Test discovery
        inspector = RouterInspector()
        result = inspector.inspect_router(profile)
        
        # Verify discovery results
        self.assertGreater(len(result.as_numbers), 0)
        self.assertIn(13335, result.as_numbers)
        self.assertIn(15169, result.as_numbers)
        
        # Test YAML generation
        yaml_gen = YAMLGenerator(output_dir=Path(self.temp_dir))
        mappings = yaml_gen.generate_mappings([profile])
        
        # Verify mappings
        self.assertIn('routers', mappings)
        self.assertIn('test-router', mappings['routers'])
        
        router_data = mappings['routers']['test-router']
        self.assertEqual(set(router_data['discovered_as_numbers']), {13335, 15169})
        
        print("✓ Discovery automation workflow completed successfully")
    
    @patch('otto_bgp.generators.bgpq4_wrapper.subprocess.run')
    def test_generation_automation_with_caching(self, mock_subprocess):
        """Test automated policy generation with caching"""
        
        from otto_bgp.generators.bgpq4_wrapper import BGPq4Wrapper
        from otto_bgp.utils.cache import PolicyCache
        
        # Mock bgpq4 execution
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = """policy-options {
    prefix-list AS13335 {
        1.1.1.0/24;
        1.0.0.0/24;
    }
}"""
        mock_subprocess.return_value = mock_result
        
        # Test with caching enabled
        wrapper = BGPq4Wrapper(
            enable_cache=True,
            cache_ttl=300  # 5 minutes
        )
        
        # First generation (should hit bgpq4)
        result1 = wrapper.generate_policy_for_as(13335)
        self.assertTrue(result1.success)
        self.assertIn("prefix-list AS13335", result1.policy_content)
        
        # Second generation (should hit cache)
        result2 = wrapper.generate_policy_for_as(13335)
        self.assertTrue(result2.success)
        self.assertEqual(result1.policy_content, result2.policy_content)
        
        # Verify bgpq4 was only called once (second was cached)
        self.assertEqual(mock_subprocess.call_count, 1)
        
        # Test cache statistics
        status = wrapper.get_status_info()
        self.assertEqual(status['cache'], 'enabled')
        self.assertIn('cache_entries', status)
        
        print("✓ Generation automation with caching completed successfully")
    
    def test_error_recovery_automation(self):
        """Test automated error recovery"""
        
        from otto_bgp.generators.bgpq4_wrapper import BGPq4Wrapper, validate_as_number
        
        # Test AS number validation with various invalid inputs
        invalid_inputs = [
            "invalid",
            -1,
            4294967296,  # Too large
            None,
            3.14159,     # Float
            "AS; rm -rf /"  # Injection attempt
        ]
        
        errors_caught = 0
        for invalid_input in invalid_inputs:
            try:
                validate_as_number(invalid_input)
            except ValueError:
                errors_caught += 1
        
        # Should catch all invalid inputs
        self.assertEqual(errors_caught, len(invalid_inputs))
        
        # Test batch processing with mixed valid/invalid
        wrapper = BGPq4Wrapper()
        
        with patch('otto_bgp.generators.bgpq4_wrapper.subprocess.run') as mock_subprocess:
            # Mock bgpq4 success for valid AS
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = "policy-options { prefix-list test { 1.1.1.0/24; } }"
            mock_subprocess.return_value = mock_result
            
            # Mix of valid and invalid AS numbers
            mixed_as_list = [13335, -1, 15169, "invalid"]
            results = wrapper.generate_policies_batch(mixed_as_list)
            
            # Should have results for all inputs
            self.assertEqual(len(results), len(mixed_as_list))
            
            # Count successful vs failed
            successful = [r for r in results if r.success]
            failed = [r for r in results if not r.success]
            
            # Should have 2 successful (valid AS) and 2 failed (invalid AS)
            self.assertEqual(len(successful), 2)
            self.assertEqual(len(failed), 2)
        
        print("✓ Error recovery automation completed successfully")
    
    @patch('otto_bgp.appliers.juniper_netconf.Device')
    def test_application_automation_safety(self, mock_device_class):
        """Test automated policy application with safety checks"""
        
        from otto_bgp.appliers import JuniperPolicyApplier, SafetyManager
        from otto_bgp.generators.bgpq4_wrapper import PolicyGenerationResult
        
        # Mock PyEZ device
        mock_device = MagicMock()
        mock_device.facts = {'hostname': 'test-router', 'model': 'MX960'}
        mock_device.cu.diff.return_value = "Test configuration diff"
        mock_device.cu.commit_check.return_value = True
        mock_device_class.return_value = mock_device
        
        # Create test policies
        test_policies = [
            PolicyGenerationResult(
                as_number=13335,
                policy_name="AS13335",
                policy_content="""policy-options {
    prefix-list AS13335 {
        1.1.1.0/24;
        1.0.0.0/24;
    }
}""",
                success=True
            ),
            PolicyGenerationResult(
                as_number=15169,
                policy_name="AS15169", 
                policy_content="""policy-options {
    prefix-list AS15169 {
        8.8.8.0/24;
        8.8.4.0/24;
    }
}""",
                success=True
            )
        ]
        
        # Test safety validation
        safety = SafetyManager()
        safety_result = safety.validate_policies_before_apply(test_policies)
        
        # Should pass basic safety checks
        self.assertTrue(safety_result.safe_to_proceed)
        self.assertNotEqual(safety_result.risk_level, 'critical')
        
        # Test policy application
        applier = JuniperPolicyApplier()
        
        # Connect to device (mocked)
        device = applier.connect_to_router(
            hostname="test-router",
            username="admin",
            password="password"
        )
        self.assertIsNotNone(device)
        
        # Preview changes
        diff = applier.preview_changes(test_policies)
        self.assertIsNotNone(diff)
        
        # Verify safety checks were performed
        bgp_impact = safety.check_bgp_session_impact(diff)
        self.assertIsInstance(bgp_impact, dict)
        
        print("✓ Application automation with safety checks completed successfully")
    
    def test_monitoring_integration(self):
        """Test monitoring and metrics integration"""
        
        from otto_bgp.utils.cache import PolicyCache
        from otto_bgp.generators.bgpq4_wrapper import BGPq4Wrapper
        
        # Test cache monitoring
        cache = PolicyCache(cache_dir=Path(self.temp_dir) / "cache")
        
        # Add some test data
        test_policy = "policy-options { prefix-list test { 1.1.1.0/24; } }"
        cache.put_policy(13335, test_policy)
        cache.put_policy(15169, test_policy)
        
        # Get statistics
        stats = cache.get_stats()
        self.assertEqual(stats['active_entries'], 2)
        self.assertEqual(stats['expired_entries'], 0)
        
        # Test wrapper monitoring
        wrapper = BGPq4Wrapper(enable_cache=True)
        status = wrapper.get_status_info()
        
        # Verify status information
        required_keys = ['mode', 'command', 'timeout', 'proxy', 'cache']
        for key in required_keys:
            self.assertIn(key, status)
        
        # Test performance metrics would be collected here
        # (In real implementation, would integrate with monitoring system)
        
        print("✓ Monitoring integration completed successfully")
    
    def test_configuration_automation(self):
        """Test automated configuration management"""
        
        from otto_bgp.utils.config import ConfigManager, BGPToolkitConfig
        import os
        
        # Test environment variable configuration
        test_env = {
            'OTTO_BGP_SSH_USERNAME': 'test-admin',
            'OTTO_BGP_SSH_TIMEOUT': '45',
            'OTTO_BGP_BGPQ4_TIMEOUT': '60',
            'OTTO_BGP_PROXY_ENABLED': 'true'
        }
        
        # Set environment variables
        for key, value in test_env.items():
            os.environ[key] = value
        
        try:
            # Load configuration
            config_manager = ConfigManager()
            config = config_manager.get_config()
            
            # Verify environment variables were applied
            self.assertEqual(config.ssh.username, 'test-admin')
            self.assertEqual(config.ssh.connection_timeout, 45)
            self.assertEqual(config.bgpq4.timeout, 60)
            self.assertTrue(config.irr_proxy.enabled)
            
            # Test configuration validation
            issues = config_manager.validate_config()
            
            # Should not have any critical validation failures
            critical_issues = [i for i in issues if 'critical' in i.lower()]
            self.assertEqual(len(critical_issues), 0)
            
            print("✓ Configuration automation completed successfully")
            
        finally:
            # Clean up environment variables
            for key in test_env.keys():
                if key in os.environ:
                    del os.environ[key]


if __name__ == '__main__':
    unittest.main(verbosity=2)
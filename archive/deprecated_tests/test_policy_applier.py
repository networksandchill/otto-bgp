"""
Tests for Policy Application Module (Phase 4)

Tests NETCONF/PyEZ integration, safety mechanisms, and policy adaptation.
"""

import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call
from dataclasses import dataclass

# Import modules to test
from otto_bgp.appliers import (
    JuniperPolicyApplier,
    PolicyAdapter,
    SafetyManager,
    ApplicationResult,
    AdaptationResult,
    SafetyCheckResult
)


class TestJuniperPolicyApplier(unittest.TestCase):
    """Test NETCONF policy application"""
    
    def setUp(self):
        """Set up test environment"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.applier = JuniperPolicyApplier()
        
        # Create test policies
        self.test_policies = [
            {
                'as_number': 65001,
                'filename': 'AS65001_policy.txt',
                'content': """policy-options {
    prefix-list AS65001 {
        192.168.1.0/24;
        10.0.0.0/8;
    }
}""",
                'path': str(self.temp_dir / 'AS65001_policy.txt')
            },
            {
                'as_number': 65002,
                'filename': 'AS65002_policy.txt',
                'content': """policy-options {
    prefix-list AS65002 {
        172.16.0.0/12;
    }
}""",
                'path': str(self.temp_dir / 'AS65002_policy.txt')
            }
        ]
    
    @patch('otto_bgp.appliers.juniper_netconf.Device')
    def test_connect_to_router(self, mock_device_class):
        """Test router connection establishment"""
        # Setup mock device
        mock_device = MagicMock()
        mock_device.facts = {'hostname': 'test-router', 'model': 'MX960', 'version': '21.4R1'}
        mock_device_class.return_value = mock_device
        
        # Test connection
        device = self.applier.connect_to_router(
            hostname='test-router',
            username='testuser',
            password='testpass'
        )
        
        # Verify connection
        self.assertIsNotNone(device)
        mock_device.open.assert_called_once()
        self.assertTrue(self.applier.connected)
        self.assertEqual(self.applier.device, mock_device)
    
    def test_load_router_policies(self):
        """Test loading policies from directory"""
        # Create test policy files
        policy_dir = self.temp_dir / 'routers' / 'test-router'
        policy_dir.mkdir(parents=True)
        
        for policy in self.test_policies:
            policy_file = policy_dir / policy['filename']
            policy_file.write_text(policy['content'])
        
        # Load policies
        loaded_policies = self.applier.load_router_policies(policy_dir)
        
        # Verify loading
        self.assertEqual(len(loaded_policies), 2)
        self.assertEqual(loaded_policies[0]['as_number'], 65001)
        self.assertEqual(loaded_policies[1]['as_number'], 65002)
    
    @patch('otto_bgp.appliers.juniper_netconf.Config')
    @patch('otto_bgp.appliers.juniper_netconf.Device')
    def test_preview_changes(self, mock_device_class, mock_config_class):
        """Test configuration preview generation"""
        # Setup mocks
        mock_device = MagicMock()
        mock_config = MagicMock()
        mock_config.diff.return_value = """
[edit policy-options]
+    prefix-list AS65001 {
+        192.168.1.0/24;
+        10.0.0.0/8;
+    }"""
        
        self.applier.device = mock_device
        self.applier.config = mock_config
        self.applier.connected = True
        
        # Generate preview
        diff = self.applier.preview_changes(self.test_policies)
        
        # Verify preview
        self.assertIn('prefix-list AS65001', diff)
        self.assertIn('192.168.1.0/24', diff)
        mock_config.load.assert_called_once()
        mock_config.diff.assert_called_once()
    
    @patch('otto_bgp.appliers.juniper_netconf.Config')
    @patch('otto_bgp.appliers.juniper_netconf.Device')
    def test_apply_with_confirmation(self, mock_device_class, mock_config_class):
        """Test policy application with confirmation"""
        # Setup mocks
        mock_device = MagicMock()
        mock_device.hostname = 'test-router'
        mock_config = MagicMock()
        mock_config.diff.return_value = "test diff"
        mock_config.commit.return_value = MagicMock(commit_id='12345')
        
        self.applier.device = mock_device
        self.applier.config = mock_config
        self.applier.connected = True
        
        # Apply policies
        result = self.applier.apply_with_confirmation(
            policies=self.test_policies,
            confirm_timeout=120,
            comment="Test application"
        )
        
        # Verify application
        self.assertTrue(result.success)
        self.assertEqual(result.policies_applied, 2)
        self.assertEqual(result.commit_id, '12345')
        mock_config.commit.assert_called_with(
            comment="Test application",
            confirm=120
        )
    
    @patch('otto_bgp.appliers.juniper_netconf.Config')
    @patch('otto_bgp.appliers.juniper_netconf.Device')
    def test_rollback_changes(self, mock_device_class, mock_config_class):
        """Test configuration rollback"""
        # Setup mocks
        mock_device = MagicMock()
        mock_config = MagicMock()
        
        self.applier.device = mock_device
        self.applier.config = mock_config
        self.applier.connected = True
        
        # Test rollback
        success = self.applier.rollback_changes(rollback_id=1)
        
        # Verify rollback
        self.assertTrue(success)
        mock_config.rollback.assert_called_with(1)
        mock_config.commit.assert_called_once()
    
    def test_no_pyez_handling(self):
        """Test handling when PyEZ is not installed"""
        with patch('otto_bgp.appliers.juniper_netconf.PYEZ_AVAILABLE', False):
            applier = JuniperPolicyApplier()
            
            # Test connection attempt without PyEZ
            with self.assertRaises(Exception) as context:
                applier.connect_to_router('test-router')
            
            self.assertIn("PyEZ not installed", str(context.exception))


class TestPolicyAdapter(unittest.TestCase):
    """Test policy adaptation layer"""
    
    def setUp(self):
        """Set up test environment"""
        self.adapter = PolicyAdapter()
        self.test_policies = [
            {
                'as_number': 65001,
                'content': """policy-options {
    prefix-list AS65001 {
        192.168.1.0/24;
    }
}"""
            },
            {
                'as_number': 65002,
                'content': """policy-options {
    prefix-list AS65002 {
        172.16.0.0/12;
    }
}"""
            }
        ]
        
        self.bgp_groups = {
            'external': [65001, 65002],
            'cdn': [13335],
            'transit': [65003]
        }
    
    def test_adapt_policies_prefix_list(self):
        """Test prefix-list style adaptation"""
        result = self.adapter.adapt_policies_for_router(
            router_hostname='test-router',
            policies=self.test_policies,
            bgp_groups=self.bgp_groups,
            policy_style='prefix-list'
        )
        
        # Verify adaptation
        self.assertTrue(result.success)
        self.assertEqual(result.policies_adapted, 2)
        self.assertIn('external', result.bgp_groups_configured)
        self.assertIn('prefix-list AS65001', result.configuration)
        self.assertIn('group external', result.configuration)
    
    def test_adapt_policies_policy_statement(self):
        """Test policy-statement style adaptation"""
        result = self.adapter.adapt_policies_for_router(
            router_hostname='test-router',
            policies=self.test_policies,
            bgp_groups=self.bgp_groups,
            policy_style='policy-statement'
        )
        
        # Verify adaptation
        self.assertTrue(result.success)
        self.assertIn('policy-statement IMPORT-AS65001', result.configuration)
        self.assertIn('from prefix-list AS65001', result.configuration)
        self.assertIn('then accept', result.configuration)
    
    def test_create_bgp_import_chain(self):
        """Test BGP import policy chain creation"""
        chain = self.adapter.create_bgp_import_chain(
            group_name='external',
            as_numbers=[65001, 65002],
            existing_policies=['BASE-POLICY']
        )
        
        # Verify chain
        self.assertIn('import [', chain)
        self.assertIn('BASE-POLICY', chain)
        self.assertIn('IMPORT-AS65001', chain)
        self.assertIn('IMPORT-AS65002', chain)
    
    def test_validate_adapted_config(self):
        """Test configuration validation"""
        # Test valid config
        valid_config = """policy-options {
    prefix-list AS65001 {
        192.168.1.0/24;
    }
}"""
        issues = self.adapter.validate_adapted_config(valid_config)
        self.assertEqual(len(issues), 0)
        
        # Test empty prefix-list
        invalid_config = """policy-options {
    prefix-list AS65001 {
    }
}"""
        issues = self.adapter.validate_adapted_config(invalid_config)
        self.assertIn("Empty prefix-list: AS65001", issues)
    
    def test_merge_strategies(self):
        """Test configuration merge strategies"""
        new_config = "prefix-list NEW { 10.0.0.0/8; }"
        existing_config = "prefix-list OLD { 192.168.0.0/16; }"
        
        # Test replace strategy
        merged = self.adapter.merge_with_existing(
            new_config, existing_config, 'replace'
        )
        self.assertEqual(merged, new_config)
        
        # Test append strategy
        merged = self.adapter.merge_with_existing(
            new_config, existing_config, 'append'
        )
        self.assertIn(new_config, merged)
        self.assertIn(existing_config, merged)


class TestSafetyManager(unittest.TestCase):
    """Test safety validation mechanisms"""
    
    def setUp(self):
        """Set up test environment"""
        self.safety = SafetyManager()
        
        self.valid_policies = [
            {
                'as_number': 65001,
                'content': """policy-options {
    prefix-list AS65001 {
        1.2.3.0/24;
        4.5.6.0/24;
    }
}"""
            }
        ]
        
        self.dangerous_policies = [
            {
                'as_number': 65002,
                'content': """policy-options {
    prefix-list AS65002 {
        192.168.0.0/16;
        10.0.0.0/8;
        0.0.0.0/0;
    }
}"""
            }
        ]
    
    def test_validate_safe_policies(self):
        """Test validation of safe policies"""
        result = self.safety.validate_policies_before_apply(self.valid_policies)
        
        # Verify validation
        self.assertTrue(result.safe_to_proceed)
        self.assertEqual(result.risk_level, 'low')
        self.assertEqual(len(result.errors), 0)
    
    def test_validate_dangerous_policies(self):
        """Test detection of dangerous policies"""
        result = self.safety.validate_policies_before_apply(self.dangerous_policies)
        
        # Verify detection
        self.assertFalse(result.safe_to_proceed)
        self.assertIn('high', result.risk_level)
        self.assertTrue(len(result.warnings) > 0)
        
        # Check for bogon detection
        warning_text = ' '.join(result.warnings)
        self.assertIn('Bogon', warning_text)
        self.assertIn('192.168', warning_text)
    
    def test_check_bgp_session_impact(self):
        """Test BGP session impact analysis"""
        diff = """
delete protocols bgp group external
replace protocols bgp group transit import NEW-POLICY
delete protocols bgp neighbor 10.0.0.1
"""
        
        impact = self.safety.check_bgp_session_impact(diff)
        
        # Verify impact analysis
        self.assertIn('external', impact)
        self.assertIn('deletion', impact['external'])
        self.assertIn('policy', impact)
        self.assertIn('10.0.0.1', impact)
    
    def test_create_rollback_checkpoint(self):
        """Test rollback checkpoint creation"""
        checkpoint_id = self.safety.create_rollback_checkpoint('test-router')
        
        # Verify checkpoint
        self.assertIsNotNone(checkpoint_id)
        self.assertIn('otto_bgp', checkpoint_id)
        self.assertEqual(len(self.safety.checkpoints), 1)
    
    def test_monitor_post_application(self):
        """Test post-application monitoring"""
        # Test healthy metrics
        current_metrics = {
            'bgp_sessions_established': 10,
            'total_routes': 50000,
            'cpu_utilization': 20,
            'memory_utilization': 60
        }
        
        baseline_metrics = {
            'bgp_sessions_established': 10,
            'total_routes': 48000
        }
        
        healthy = self.safety.monitor_post_application(current_metrics, baseline_metrics)
        self.assertTrue(healthy)
        
        # Test unhealthy metrics (session loss)
        current_metrics['bgp_sessions_established'] = 5
        healthy = self.safety.monitor_post_application(current_metrics, baseline_metrics)
        self.assertFalse(healthy)
    
    def test_safety_report_generation(self):
        """Test safety report generation"""
        check_result = SafetyCheckResult(
            safe_to_proceed=False,
            risk_level='high',
            warnings=['Test warning 1', 'Test warning 2'],
            errors=['Test error'],
            bgp_impact={'session1': 'will reset'},
            recommended_action='Do not proceed'
        )
        
        report = self.safety.generate_safety_report(check_result)
        
        # Verify report content
        self.assertIn('SAFETY REPORT', report)
        self.assertIn('Risk Level: HIGH', report)
        self.assertIn('Test warning 1', report)
        self.assertIn('Test error', report)
        self.assertIn('session1: will reset', report)
    
    def test_prefix_count_validation(self):
        """Test prefix count threshold validation"""
        # Create policy with too many prefixes
        large_policy = {
            'as_number': 65003,
            'content': 'prefix-list AS65003 {\n' + 
                      '\n'.join([f'    {i}.0.0.0/24;' for i in range(200000)]) + 
                      '\n}'
        }
        
        result = self.safety.validate_policies_before_apply([large_policy])
        
        # Verify warning about prefix count
        self.assertTrue(any('exceeds safe limit' in w for w in result.warnings))
    
    def test_as_number_validation(self):
        """Test AS number range validation"""
        # Test reserved AS number
        reserved_policy = {
            'as_number': 64500,  # Reserved for documentation
            'content': 'prefix-list AS64500 { 1.2.3.0/24; }'
        }
        
        result = self.safety.validate_policies_before_apply([reserved_policy])
        
        # Verify warning about reserved AS
        self.assertTrue(any('reserved' in w.lower() for w in result.warnings))


class TestEndToEndApplication(unittest.TestCase):
    """End-to-end policy application tests"""
    
    def setUp(self):
        """Set up test environment"""
        self.temp_dir = Path(tempfile.mkdtemp())
    
    @patch('otto_bgp.appliers.juniper_netconf.Device')
    @patch('otto_bgp.appliers.juniper_netconf.Config')
    def test_complete_application_workflow(self, mock_config_class, mock_device_class):
        """Test complete policy application workflow"""
        # Setup mocks
        mock_device = MagicMock()
        mock_device.hostname = 'test-router'
        mock_device.facts = {'model': 'MX960'}
        
        mock_config = MagicMock()
        mock_config.diff.return_value = "test diff"
        mock_config.commit.return_value = MagicMock(commit_id='12345')
        
        mock_device_class.return_value = mock_device
        mock_config_class.return_value = mock_config
        
        # Initialize components
        applier = JuniperPolicyApplier()
        adapter = PolicyAdapter()
        safety = SafetyManager()
        
        # Create test policies
        policies = [
            {
                'as_number': 65001,
                'content': 'prefix-list AS65001 { 1.2.3.0/24; }'
            }
        ]
        
        bgp_groups = {'external': [65001]}
        
        # Step 1: Adapt policies
        adapt_result = adapter.adapt_policies_for_router(
            'test-router', policies, bgp_groups
        )
        self.assertTrue(adapt_result.success)
        
        # Step 2: Safety validation
        safety_result = safety.validate_policies_before_apply(policies)
        self.assertTrue(safety_result.safe_to_proceed)
        
        # Step 3: Connect to router
        device = applier.connect_to_router('test-router')
        self.assertIsNotNone(device)
        
        # Step 4: Preview changes
        applier.config = mock_config
        diff = applier.preview_changes(policies)
        self.assertIsNotNone(diff)
        
        # Step 5: Apply with confirmation
        result = applier.apply_with_confirmation(policies, confirm_timeout=120)
        self.assertTrue(result.success)
        self.assertEqual(result.policies_applied, 1)
        
        # Step 6: Disconnect
        applier.disconnect()
        mock_device.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
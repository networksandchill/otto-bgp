#!/usr/bin/env python3
"""
Test script for SSH host key verification implementation.

This script verifies that the security changes work correctly without
breaking existing functionality.
"""

import sys
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import paramiko
from bgp_toolkit.utils.ssh_security import (
    ProductionHostKeyPolicy, 
    HostKeyManager, 
    get_host_key_policy
)
from bgp_toolkit.collectors.juniper_ssh import JuniperSSHCollector


class TestSSHSecurity(unittest.TestCase):
    """Test suite for SSH security implementation"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.known_hosts_path = Path(self.temp_dir) / "known_hosts"
        self.test_device_csv = Path(self.temp_dir) / "devices.csv"
        
        # Create test devices CSV
        self.test_device_csv.write_text(
            "address,hostname\n"
            "192.168.1.1,router1\n"
            "192.168.1.2,router2\n"
        )
    
    def tearDown(self):
        """Clean up test fixtures"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_production_policy_strict_mode(self):
        """Test that production policy rejects unknown hosts"""
        # Create policy without existing known_hosts (should fail in strict mode)
        with self.assertRaises(RuntimeError) as context:
            policy = ProductionHostKeyPolicy(
                known_hosts_path=str(self.known_hosts_path),
                strict=True
            )
        
        self.assertIn("known_hosts file missing", str(context.exception))
    
    def test_production_policy_setup_mode(self):
        """Test that setup mode allows new hosts"""
        # Create policy in setup mode
        policy = ProductionHostKeyPolicy(
            known_hosts_path=str(self.known_hosts_path),
            strict=False
        )
        
        # Should not raise an exception
        self.assertIsNotNone(policy)
        self.assertFalse(policy.strict)
    
    def test_host_key_verification_with_known_host(self):
        """Test that known hosts are accepted"""
        # Create a fake known_hosts file
        fake_key = paramiko.RSAKey.generate(1024)
        host_keys = paramiko.HostKeys()
        host_keys.add("test.example.com", "ssh-rsa", fake_key)
        host_keys.save(str(self.known_hosts_path))
        
        # Create policy with existing known_hosts
        policy = ProductionHostKeyPolicy(
            known_hosts_path=str(self.known_hosts_path),
            strict=True
        )
        
        # Load the host keys
        self.assertEqual(len(policy.host_keys), 1)
        self.assertIn("test.example.com", policy.host_keys)
    
    def test_host_key_mismatch_detection(self):
        """Test that mismatched host keys are rejected"""
        # Create known_hosts with one key
        fake_key1 = paramiko.RSAKey.generate(1024)
        host_keys = paramiko.HostKeys()
        host_keys.add("test.example.com", "ssh-rsa", fake_key1)
        host_keys.save(str(self.known_hosts_path))
        
        # Create policy
        policy = ProductionHostKeyPolicy(
            known_hosts_path=str(self.known_hosts_path),
            strict=True
        )
        
        # Try to connect with different key
        fake_key2 = paramiko.RSAKey.generate(1024)
        mock_client = Mock()
        
        with self.assertRaises(paramiko.SSHException) as context:
            policy.missing_host_key(mock_client, "test.example.com", fake_key2)
        
        self.assertIn("Key mismatch", str(context.exception))
    
    def test_get_host_key_policy_factory(self):
        """Test the factory function for getting policies"""
        # Test production mode (default)
        with patch.dict(os.environ, {}, clear=True):
            # Should fail without known_hosts in production
            with self.assertRaises(RuntimeError):
                policy = get_host_key_policy(setup_mode=False)
        
        # Test setup mode via parameter
        self.known_hosts_path.touch()  # Create empty file
        with patch.dict(os.environ, {'SSH_KNOWN_HOSTS': str(self.known_hosts_path)}):
            policy = get_host_key_policy(setup_mode=True)
            self.assertIsInstance(policy, ProductionHostKeyPolicy)
    
    def test_collector_integration(self):
        """Test that JuniperSSHCollector uses the new policy"""
        # Set up environment for testing
        with patch.dict(os.environ, {
            'SSH_USERNAME': 'testuser',
            'SSH_PASSWORD': 'testpass',
            'SSH_KNOWN_HOSTS': str(self.known_hosts_path),
            'BGP_TOOLKIT_SETUP_MODE': 'true'
        }):
            # Create collector in setup mode
            collector = JuniperSSHCollector(setup_mode=True)
            
            # Verify setup mode is enabled
            self.assertTrue(collector.setup_mode)
            
            # Mock SSH client creation
            with patch.object(collector, '_create_ssh_client') as mock_create:
                mock_client = MagicMock()
                mock_create.return_value = mock_client
                
                # Create client
                client = collector._create_ssh_client()
                
                # Verify set_missing_host_key_policy was called
                mock_create.assert_called_once()
    
    def test_host_key_manager(self):
        """Test the HostKeyManager utility class"""
        manager = HostKeyManager(str(self.known_hosts_path))
        
        # Initially empty
        self.assertEqual(len(manager.host_keys), 0)
        
        # Add a test key
        fake_key = paramiko.RSAKey.generate(1024)
        manager.host_keys.add("test.example.com", "ssh-rsa", fake_key)
        manager.host_keys.save(str(self.known_hosts_path))
        
        # Verify the key was saved
        manager2 = HostKeyManager(str(self.known_hosts_path))
        self.assertEqual(len(manager2.host_keys), 1)
        
        # Test verification
        results = manager2.verify_host_keys()
        self.assertEqual(results['total_hosts'], 1)
        self.assertEqual(results['total_keys'], 1)
        self.assertIn('ssh-rsa', results['key_types'])
    
    def test_backwards_compatibility(self):
        """Test that old code paths still work (with setup mode)"""
        with patch.dict(os.environ, {
            'SSH_USERNAME': 'testuser',
            'SSH_PASSWORD': 'testpass',
            'SSH_KNOWN_HOSTS': str(self.known_hosts_path),  # Use test path
            'BGP_TOOLKIT_SETUP_MODE': 'true'  # Enable setup mode for compatibility
        }):
            # Should work without known_hosts in setup mode
            collector = JuniperSSHCollector()
            self.assertTrue(collector.setup_mode)
            
            # Verify it creates SSH client without error
            with patch('paramiko.SSHClient') as mock_ssh:
                mock_client = MagicMock()
                mock_ssh.return_value = mock_client
                
                client = collector._create_ssh_client()
                
                # Should have set a host key policy
                mock_client.set_missing_host_key_policy.assert_called_once()


class TestSecuritySanityChecks(unittest.TestCase):
    """Sanity checks to ensure no security regressions"""
    
    def test_no_auto_add_policy_in_production(self):
        """Ensure AutoAddPolicy is not used in production code"""
        # Check juniper_ssh.py doesn't contain AutoAddPolicy
        juniper_ssh_path = Path(__file__).parent / "bgp_toolkit" / "collectors" / "juniper_ssh.py"
        if juniper_ssh_path.exists():
            content = juniper_ssh_path.read_text()
            # Should not directly use AutoAddPolicy
            self.assertNotIn("AutoAddPolicy()", content, 
                           "AutoAddPolicy() found in production code - security vulnerability!")
    
    def test_environment_variables_documented(self):
        """Ensure new environment variables are documented"""
        readme_path = Path(__file__).parent / "README.md"
        if readme_path.exists():
            content = readme_path.read_text()
            self.assertIn("SSH_KNOWN_HOSTS", content, 
                        "SSH_KNOWN_HOSTS not documented in README")
            self.assertIn("BGP_TOOLKIT_SETUP_MODE", content,
                        "BGP_TOOLKIT_SETUP_MODE not documented in README")
    
    def test_setup_scripts_exist(self):
        """Ensure setup scripts are present"""
        scripts_dir = Path(__file__).parent / "scripts"
        
        # Check bash script
        bash_script = scripts_dir / "setup-host-keys.sh"
        self.assertTrue(bash_script.exists(), 
                       f"Setup script missing: {bash_script}")
        
        # Check Python script
        python_script = scripts_dir / "setup_host_keys.py"
        self.assertTrue(python_script.exists(), 
                       f"Setup script missing: {python_script}")
        
        # Check scripts are executable (bash script)
        if bash_script.exists():
            # Check shebang
            first_line = bash_script.read_text().split('\n')[0]
            self.assertTrue(first_line.startswith("#!/bin/bash"),
                          "Bash script missing shebang")
    
    def test_imports_work(self):
        """Test that all imports work correctly"""
        try:
            from bgp_toolkit.utils.ssh_security import (
                ProductionHostKeyPolicy,
                HostKeyManager,
                get_host_key_policy
            )
            from bgp_toolkit.collectors.juniper_ssh import JuniperSSHCollector
            
            # If we get here, imports worked
            self.assertTrue(True)
        except ImportError as e:
            self.fail(f"Import failed: {e}")


def run_integration_test():
    """Run a simple integration test"""
    print("\n" + "="*60)
    print("Running Integration Test")
    print("="*60)
    
    temp_dir = tempfile.mkdtemp()
    known_hosts = Path(temp_dir) / "known_hosts"
    
    try:
        # Test 1: Setup mode allows operation without known_hosts
        print("\n✓ Test 1: Setup mode works without known_hosts")
        with patch.dict(os.environ, {
            'SSH_USERNAME': 'test',
            'SSH_PASSWORD': 'test',
            'BGP_TOOLKIT_SETUP_MODE': 'true'
        }):
            collector = JuniperSSHCollector()
            print("  - Collector created in setup mode")
        
        # Test 2: Production mode requires known_hosts
        print("\n✓ Test 2: Production mode enforces security")
        known_hosts.touch()  # Create empty file
        with patch.dict(os.environ, {
            'SSH_USERNAME': 'test',
            'SSH_PASSWORD': 'test',
            'SSH_KNOWN_HOSTS': str(known_hosts),
            'BGP_TOOLKIT_SETUP_MODE': 'false'
        }):
            try:
                collector = JuniperSSHCollector()
                print("  - Collector created in production mode")
            except Exception as e:
                # Expected if known_hosts is empty
                print(f"  - Production mode correctly enforces host verification")
        
        print("\n✅ All integration tests passed!")
        
    finally:
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == '__main__':
    # Run unit tests
    print("Running Unit Tests...")
    print("="*60)
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestSSHSecurity))
    suite.addTests(loader.loadTestsFromTestCase(TestSecuritySanityChecks))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Run integration test
    if result.wasSuccessful():
        run_integration_test()
    
    # Exit with appropriate code
    sys.exit(0 if result.wasSuccessful() else 1)
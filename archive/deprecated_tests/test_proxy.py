"""
Tests for IRR Proxy Module (Phase 5)

Tests SSH tunnel management, configuration, and BGPq4 integration.
"""

import unittest
import tempfile
import socket
import subprocess
import time
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call
from dataclasses import dataclass

# Import modules to test
from otto_bgp.proxy import IRRProxyManager, ProxyConfig, TunnelStatus, TunnelState
from otto_bgp.generators.bgpq4_wrapper import BGPq4Wrapper


class TestProxyConfig(unittest.TestCase):
    """Test proxy configuration handling"""
    
    def test_default_configuration(self):
        """Test default proxy configuration"""
        config = ProxyConfig()
        
        self.assertFalse(config.enabled)
        self.assertEqual(config.method, "ssh_tunnel")
        self.assertEqual(config.connection_timeout, 10)
        self.assertEqual(len(config.tunnels), 0)
    
    def test_configuration_with_tunnels(self):
        """Test configuration with tunnel definitions"""
        tunnels = [
            {
                'name': 'ntt',
                'local_port': 43001,
                'remote_host': 'rr.ntt.net',
                'remote_port': 43
            }
        ]
        
        config = ProxyConfig(
            enabled=True,
            jump_host='gateway.example.com',
            jump_user='testuser',
            tunnels=tunnels
        )
        
        self.assertTrue(config.enabled)
        self.assertEqual(config.jump_host, 'gateway.example.com')
        self.assertEqual(config.jump_user, 'testuser')
        self.assertEqual(len(config.tunnels), 1)
        self.assertEqual(config.tunnels[0]['name'], 'ntt')


class TestIRRProxyManager(unittest.TestCase):
    """Test IRR proxy manager functionality"""
    
    def setUp(self):
        """Set up test environment"""
        self.config = ProxyConfig(
            enabled=True,
            jump_host='test.gateway.com',
            jump_user='testuser',
            ssh_key_file='/tmp/test_key',
            connection_timeout=5,
            tunnels=[
                {
                    'name': 'test-tunnel',
                    'local_port': 43001,
                    'remote_host': 'test.irr.net',
                    'remote_port': 43
                }
            ]
        )
        
        self.proxy_manager = IRRProxyManager(self.config)
    
    def test_initialization(self):
        """Test proxy manager initialization"""
        self.assertEqual(self.proxy_manager.config, self.config)
        self.assertEqual(len(self.proxy_manager.tunnels), 0)
        self.assertEqual(len(self.proxy_manager.processes), 0)
        self.assertEqual(len(self.proxy_manager.allocated_ports), 0)
    
    def test_build_ssh_command(self):
        """Test SSH command construction"""
        cmd = self.proxy_manager._build_ssh_command(43001, 'test.irr.net', 43)
        
        # Check essential security options
        self.assertIn('-o', cmd)
        self.assertIn('StrictHostKeyChecking=yes', cmd)
        self.assertIn('BatchMode=yes', cmd)
        self.assertIn('-L', cmd)
        self.assertIn('43001:test.irr.net:43', cmd)
        self.assertIn('testuser@test.gateway.com', cmd)
    
    def test_is_port_available(self):
        """Test port availability checking"""
        # Test with a port that should be available
        available = self.proxy_manager._is_port_available(45000)
        self.assertTrue(available)
        
        # Test with a port in use (create a socket to bind it)
        test_port = 45001
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(('127.0.0.1', test_port))
            unavailable = self.proxy_manager._is_port_available(test_port)
            self.assertFalse(unavailable)
        finally:
            sock.close()
    
    def test_allocate_port(self):
        """Test port allocation"""
        port = self.proxy_manager._allocate_port(45100, 45200)
        self.assertGreaterEqual(port, 45100)
        self.assertLessEqual(port, 45200)
        
        # Allocate the same port and verify we get a different one
        self.proxy_manager.allocated_ports.add(port)
        next_port = self.proxy_manager._allocate_port(45100, 45200)
        self.assertNotEqual(port, next_port)
    
    @patch('otto_bgp.proxy.irr_tunnel.subprocess.Popen')
    @patch('otto_bgp.proxy.irr_tunnel.socket.socket')
    def test_setup_tunnel_success(self, mock_socket_class, mock_popen):
        """Test successful tunnel setup"""
        # Mock successful process
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process
        
        # Mock successful connection test
        mock_socket = MagicMock()
        mock_socket.connect_ex.return_value = 0  # Success
        mock_socket_class.return_value = mock_socket
        
        tunnel_config = {
            'name': 'test-tunnel',
            'local_port': 43001,
            'remote_host': 'test.irr.net',
            'remote_port': 43
        }
        
        status = self.proxy_manager.setup_tunnel(tunnel_config)
        
        # Verify tunnel status
        self.assertEqual(status.name, 'test-tunnel')
        self.assertEqual(status.state, TunnelState.CONNECTED)
        self.assertEqual(status.process_id, 12345)
        self.assertIsNotNone(status.established_at)
        
        # Verify tunnel was registered
        self.assertIn('test-tunnel', self.proxy_manager.tunnels)
        self.assertIn('test-tunnel', self.proxy_manager.processes)
        self.assertIn(43001, self.proxy_manager.allocated_ports)
    
    @patch('otto_bgp.proxy.irr_tunnel.subprocess.Popen')
    @patch('otto_bgp.proxy.irr_tunnel.socket.socket')
    def test_setup_tunnel_failure(self, mock_socket_class, mock_popen):
        """Test tunnel setup failure"""
        # Mock process
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        
        # Mock failed connection test
        mock_socket = MagicMock()
        mock_socket.connect_ex.return_value = 1  # Connection refused
        mock_socket_class.return_value = mock_socket
        
        tunnel_config = {
            'name': 'failing-tunnel',
            'local_port': 43002,
            'remote_host': 'nonexistent.irr.net',
            'remote_port': 43
        }
        
        status = self.proxy_manager.setup_tunnel(tunnel_config)
        
        # Verify tunnel status
        self.assertEqual(status.name, 'failing-tunnel')
        self.assertEqual(status.state, TunnelState.FAILED)
        self.assertIsNotNone(status.error_message)
        
        # Verify cleanup was called
        mock_process.terminate.assert_called_once()
    
    def test_test_tunnel_connectivity(self):
        """Test tunnel connectivity testing"""
        # Create mock tunnel
        tunnel_status = TunnelStatus(
            name='test-tunnel',
            state=TunnelState.CONNECTED,
            local_port=43001,
            remote_host='test.irr.net',
            remote_port=43
        )
        self.proxy_manager.tunnels['test-tunnel'] = tunnel_status
        
        with patch('otto_bgp.proxy.irr_tunnel.socket.socket') as mock_socket_class:
            mock_socket = MagicMock()
            mock_socket.connect_ex.return_value = 0  # Success
            mock_socket_class.return_value = mock_socket
            
            result = self.proxy_manager.test_tunnel_connectivity('test-tunnel')
            self.assertTrue(result)
            
            # Test failure
            mock_socket.connect_ex.return_value = 1  # Failure
            result = self.proxy_manager.test_tunnel_connectivity('test-tunnel')
            self.assertFalse(result)
    
    def test_wrap_bgpq4_command(self):
        """Test bgpq4 command wrapping for proxy"""
        # Set up a mock tunnel
        tunnel_status = TunnelStatus(
            name='test-tunnel',
            state=TunnelState.CONNECTED,
            local_port=43001,
            remote_host='test.irr.net',
            remote_port=43
        )
        self.proxy_manager.tunnels['test-tunnel'] = tunnel_status
        
        original_cmd = ['bgpq4', '-Jl', 'AS7922', 'AS7922']
        wrapped_cmd = self.proxy_manager.wrap_bgpq4_command(original_cmd)
        
        # Should add host and port options
        self.assertIn('-h', wrapped_cmd)
        self.assertIn('127.0.0.1', wrapped_cmd)
        self.assertIn('-p', wrapped_cmd)
        self.assertIn('43001', wrapped_cmd)
    
    def test_cleanup_tunnel(self):
        """Test tunnel cleanup"""
        # Set up mock tunnel and process
        mock_process = MagicMock()
        self.proxy_manager.processes['test-tunnel'] = mock_process
        
        tunnel_status = TunnelStatus(
            name='test-tunnel',
            state=TunnelState.CONNECTED,
            local_port=43001,
            remote_host='test.irr.net',
            remote_port=43
        )
        self.proxy_manager.tunnels['test-tunnel'] = tunnel_status
        self.proxy_manager.allocated_ports.add(43001)
        
        # Cleanup
        success = self.proxy_manager.cleanup_tunnel('test-tunnel')
        
        self.assertTrue(success)
        mock_process.terminate.assert_called_once()
        self.assertNotIn('test-tunnel', self.proxy_manager.tunnels)
        self.assertNotIn('test-tunnel', self.proxy_manager.processes)
        self.assertNotIn(43001, self.proxy_manager.allocated_ports)


class TestBGPq4ProxyIntegration(unittest.TestCase):
    """Test BGPq4Wrapper integration with proxy"""
    
    def test_wrapper_with_proxy_manager(self):
        """Test BGPq4Wrapper with proxy manager"""
        # Create mock proxy manager
        mock_proxy = MagicMock()
        mock_proxy.wrap_bgpq4_command.return_value = [
            'bgpq4', '-h', '127.0.0.1', '-p', '43001', '-Jl', 'AS7922', 'AS7922'
        ]
        
        with patch('otto_bgp.generators.bgpq4_wrapper.shutil.which') as mock_which:
            mock_which.return_value = '/usr/bin/bgpq4'
            
            wrapper = BGPq4Wrapper(proxy_manager=mock_proxy)
            
            # Build command and verify proxy was applied
            cmd = wrapper._build_bgpq4_command(7922, 'TEST_POLICY')
            
            mock_proxy.wrap_bgpq4_command.assert_called_once()
            self.assertIn('-h', cmd)
            self.assertIn('127.0.0.1', cmd)
    
    @patch('otto_bgp.generators.bgpq4_wrapper.subprocess.run')
    @patch('otto_bgp.generators.bgpq4_wrapper.shutil.which')
    def test_proxy_policy_generation(self, mock_which, mock_subprocess):
        """Test policy generation through proxy"""
        mock_which.return_value = '/usr/bin/bgpq4'
        
        # Mock successful subprocess result
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = """policy-options {
    prefix-list AS7922 {
        1.2.3.0/24;
        4.5.6.0/24;
    }
}"""
        mock_subprocess.return_value = mock_result
        
        # Create mock proxy manager
        mock_proxy = MagicMock()
        mock_proxy.wrap_bgpq4_command.return_value = [
            'bgpq4', '-h', '127.0.0.1', '-p', '43001', '-Jl', 'AS7922', 'AS7922'
        ]
        
        wrapper = BGPq4Wrapper(proxy_manager=mock_proxy)
        result = wrapper.generate_policy_for_as(7922)
        
        self.assertTrue(result.success)
        self.assertIn('prefix-list AS7922', result.policy_content)
        mock_proxy.wrap_bgpq4_command.assert_called_once()
    
    def test_create_with_proxy_class_method(self):
        """Test BGPq4Wrapper.create_with_proxy class method"""
        from otto_bgp.utils.config import IRRProxyConfig
        
        # Create test proxy config
        proxy_config = IRRProxyConfig(
            enabled=True,
            jump_host='test.gateway.com',
            jump_user='testuser',
            tunnels=[
                {
                    'name': 'test-tunnel',
                    'local_port': 43001,
                    'remote_host': 'test.irr.net',
                    'remote_port': 43
                }
            ]
        )
        
        with patch('otto_bgp.generators.bgpq4_wrapper.shutil.which') as mock_which:
            mock_which.return_value = '/usr/bin/bgpq4'
            
            with patch('otto_bgp.proxy.irr_tunnel.IRRProxyManager') as mock_manager_class:
                mock_manager = MagicMock()
                mock_manager_class.return_value = mock_manager
                
                wrapper = BGPq4Wrapper.create_with_proxy(proxy_config)
                
                self.assertIsNotNone(wrapper.proxy_manager)
                mock_manager_class.assert_called_once()


class TestProxyConfigValidation(unittest.TestCase):
    """Test proxy configuration validation"""
    
    def test_config_validation_enabled_missing_fields(self):
        """Test validation with enabled proxy but missing fields"""
        from otto_bgp.utils.config import ConfigManager, BGPToolkitConfig, IRRProxyConfig
        
        # Create config with enabled proxy but missing jump_host
        proxy_config = IRRProxyConfig(
            enabled=True,
            jump_user='testuser'
            # jump_host missing
        )
        
        config = BGPToolkitConfig(irr_proxy=proxy_config)
        manager = ConfigManager()
        manager.config = config
        
        issues = manager.validate_config()
        
        # Should have validation error for missing jump_host
        proxy_issues = [issue for issue in issues if 'jump_host' in issue]
        self.assertTrue(len(proxy_issues) > 0)
    
    def test_config_validation_ssh_key_missing(self):
        """Test validation with missing SSH key file"""
        from otto_bgp.utils.config import ConfigManager, BGPToolkitConfig, IRRProxyConfig
        
        # Create config with SSH key that doesn't exist
        proxy_config = IRRProxyConfig(
            enabled=True,
            jump_host='test.gateway.com',
            jump_user='testuser',
            ssh_key_file='/nonexistent/key'
        )
        
        config = BGPToolkitConfig(irr_proxy=proxy_config)
        manager = ConfigManager()
        manager.config = config
        
        issues = manager.validate_config()
        
        # Should have validation error for missing SSH key
        key_issues = [issue for issue in issues if 'SSH key not found' in issue]
        self.assertTrue(len(key_issues) > 0)


class TestProxySecurityFeatures(unittest.TestCase):
    """Test security features of proxy implementation"""
    
    def test_ssh_command_security_options(self):
        """Test that SSH commands include required security options"""
        config = ProxyConfig(
            enabled=True,
            jump_host='test.gateway.com',
            jump_user='testuser',
            known_hosts_file='/test/known_hosts'
        )
        
        manager = IRRProxyManager(config)
        cmd = manager._build_ssh_command(43001, 'test.irr.net', 43)
        
        # Check security options
        self.assertIn('StrictHostKeyChecking=yes', ' '.join(cmd))
        self.assertIn('BatchMode=yes', ' '.join(cmd))
        self.assertIn('UserKnownHostsFile=/test/known_hosts', ' '.join(cmd))
    
    def test_signal_handler_registration(self):
        """Test that signal handlers are registered for cleanup"""
        config = ProxyConfig(enabled=True)
        
        with patch('otto_bgp.proxy.irr_tunnel.signal.signal') as mock_signal:
            with patch('otto_bgp.proxy.irr_tunnel.atexit.register') as mock_atexit:
                manager = IRRProxyManager(config)
                
                # Verify signal handlers registered
                mock_signal.assert_any_call(unittest.mock.ANY, manager._signal_handler)
                mock_atexit.assert_called_with(manager.cleanup_all_tunnels)
    
    def test_process_cleanup_on_failure(self):
        """Test that failed processes are properly cleaned up"""
        config = ProxyConfig(
            enabled=True,
            jump_host='test.gateway.com',
            jump_user='testuser'
        )
        
        manager = IRRProxyManager(config)
        
        with patch('otto_bgp.proxy.irr_tunnel.subprocess.Popen') as mock_popen:
            with patch('otto_bgp.proxy.irr_tunnel.socket.socket') as mock_socket_class:
                # Mock process and failed connection
                mock_process = MagicMock()
                mock_process.pid = 12345
                mock_popen.return_value = mock_process
                
                mock_socket = MagicMock()
                mock_socket.connect_ex.return_value = 1  # Connection failed
                mock_socket_class.return_value = mock_socket
                
                tunnel_config = {
                    'name': 'test-tunnel',
                    'local_port': 43001,
                    'remote_host': 'test.irr.net',
                    'remote_port': 43
                }
                
                status = manager.setup_tunnel(tunnel_config)
                
                # Verify process was terminated on failure
                self.assertEqual(status.state, TunnelState.FAILED)
                mock_process.terminate.assert_called_once()


if __name__ == '__main__':
    unittest.main()
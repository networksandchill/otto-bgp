"""
Juniper NETCONF Policy Applier - Automated BGP Policy Application

Uses PyEZ (Junos Python Extension) for NETCONF-based policy application.
Implements safety mechanisms including preview, confirmation, and rollback.

CRITICAL: Test in lab environment before production use.
"""

import logging
import time
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime

# Unified safety manager for NETCONF event notifications and guardrails
from otto_bgp.appliers.safety import UnifiedSafetyManager

# PyEZ imports with fallback for environments without PyEZ
try:
    from jnpr.junos import Device
    from jnpr.junos.utils.config import Config
    from jnpr.junos.exception import (
        ConnectError,
        ConfigLoadError,
        CommitError,
        RpcError
    )
    PYEZ_AVAILABLE = True
except ImportError:
    PYEZ_AVAILABLE = False
    # Create dummy classes for type hints
    Device = Any
    Config = Any
    ConnectError = Exception
    ConfigLoadError = Exception
    CommitError = Exception
    RpcError = Exception


@dataclass
class ApplicationResult:
    """Result of policy application operation"""
    success: bool
    hostname: str
    policies_applied: int
    diff_preview: Optional[str] = None
    commit_id: Optional[str] = None
    rollback_id: Optional[str] = None
    error_message: Optional[str] = None
    timestamp: Optional[str] = None


class ConnectionError(Exception):
    """Raised when unable to connect to router"""
    pass


class ApplicationError(Exception):
    """Raised when policy application fails"""
    pass


class JuniperPolicyApplier:
    """
    Apply BGP policies to Juniper routers via NETCONF/PyEZ
    
    Provides safe policy application with:
    - Preview/diff generation
    - Confirmed commit with automatic rollback
    - Validation and safety checks
    - Detailed logging and error handling
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None, 
                 safety_manager: Optional[UnifiedSafetyManager] = None):
        """
        Initialize the policy applier
        
        Args:
            logger: Optional logger instance
            safety_manager: Optional unified safety manager for autonomous mode notifications and guardrails
        """
        self.logger = logger or logging.getLogger(__name__)
        self.safety_manager = safety_manager or UnifiedSafetyManager(logger=self.logger)
        
        if not PYEZ_AVAILABLE:
            self.logger.warning("PyEZ not available - applier functionality limited")
            self.logger.warning("Install with: pip install junos-eznc")
        
        self.device = None
        self.config = None
        self.connected = False
        self.autonomous_mode = False  # Will be set based on configuration
        
    def _check_autonomous_mode(self) -> bool:
        """Check if autonomous mode is enabled and notifications should be sent"""
        try:
            from otto_bgp.utils.config import get_config_manager
            config_manager = get_config_manager()
            config = config_manager.get_config()
            return config.autonomous_mode.enabled and config.autonomous_mode.notifications.email.enabled
        except Exception as e:
            self.logger.debug(f"Could not check autonomous mode: {e}")
            return False
        
    def connect_to_router(self, 
                         hostname: str,
                         username: Optional[str] = None,
                         password: Optional[str] = None,
                         port: int = 830,
                         timeout: int = 30) -> Device:
        """
        Establish NETCONF connection to Juniper router
        
        Args:
            hostname: Router hostname or IP address
            username: SSH username (uses SSH config if not provided)
            password: SSH password (uses SSH key if not provided)
            port: NETCONF port (default 830)
            timeout: Connection timeout in seconds
            
        Returns:
            Connected Device object
            
        Raises:
            ConnectionError: If connection fails
        """
        if not PYEZ_AVAILABLE:
            raise ConnectionError("PyEZ not installed - cannot connect to router")
        
        self.logger.info(f"Connecting to router: {hostname}")
        
        try:
            # Create device connection
            device_params = {
                'host': hostname,
                'port': port,
                'gather_facts': True,
                'auto_probe': timeout
            }
            
            if username:
                device_params['user'] = username
            if password:
                device_params['password'] = password
            
            self.device = Device(**device_params)
            self.device.open()
            
            # Bind configuration handler
            self.config = Config(self.device)
            
            self.connected = True
            self.autonomous_mode = self._check_autonomous_mode()
            
            self.logger.info(f"Connected to {hostname} - {self.device.facts.get('model', 'Unknown')}")
            
            # SUCCESS - send notification if in autonomous mode
            if self.autonomous_mode:
                self.safety_manager.send_netconf_event_notification(
                    'connect', hostname, True, {}
                )
            
            return self.device
            
        except ConnectError as e:
            self.logger.error(f"Failed to connect to {hostname}: {e}")
            
            # FAILURE - send notification if possible
            try:
                if self._check_autonomous_mode():
                    self.safety_manager.send_netconf_event_notification(
                        'connect', hostname, False, {'error': str(e)}
                    )
            except Exception:
                pass  # Don't let notification failure mask the original error
            
            raise ConnectionError(f"Cannot connect to {hostname}: {str(e)}")
        except Exception as e:
            self.logger.error(f"Unexpected error connecting to {hostname}: {e}")
            
            # FAILURE - send notification if possible
            try:
                if self._check_autonomous_mode():
                    self.safety_manager.send_netconf_event_notification(
                        'connect', hostname, False, {'error': str(e)}
                    )
            except Exception:
                pass  # Don't let notification failure mask the original error
            
            raise ConnectionError(f"Connection failed: {str(e)}")
    
    def load_router_policies(self, policies_dir: Path) -> List[Dict[str, str]]:
        """
        Load BGP policies from router's policy directory
        
        Args:
            policies_dir: Directory containing policy files
            
        Returns:
            List of policy dictionaries with content and metadata
        """
        policies = []
        
        if not policies_dir.exists():
            self.logger.warning(f"Policies directory not found: {policies_dir}")
            return policies
        
        # Load all policy files
        policy_files = sorted(policies_dir.glob("AS*_policy.txt"))
        
        for policy_file in policy_files:
            try:
                content = policy_file.read_text()
                as_number = self._extract_as_number(policy_file.name)
                
                policies.append({
                    'as_number': as_number,
                    'filename': policy_file.name,
                    'content': content,
                    'path': str(policy_file)
                })
                
                self.logger.debug(f"Loaded policy: {policy_file.name}")
                
            except Exception as e:
                self.logger.error(f"Failed to load {policy_file}: {e}")
        
        self.logger.info(f"Loaded {len(policies)} policies from {policies_dir}")
        return policies
    
    def preview_changes(self, 
                       policies: List[Dict[str, str]],
                       format: str = "text") -> str:
        """
        Preview configuration changes without applying
        
        Args:
            policies: List of policies to apply
            format: Diff format (text, set, xml)
            
        Returns:
            Configuration diff as string
            
        Raises:
            ApplicationError: If preview generation fails
        """
        if not self.connected or not self.config:
            raise ApplicationError("Not connected to router")
        
        self.logger.info("Generating configuration preview")
        
        try:
            # Combine all policies into single configuration
            combined_config = self._combine_policies_for_load(policies)
            
            # Load configuration in merge mode (don't replace)
            self.config.load(combined_config, format='text', merge=True)
            
            # Get diff
            if format == "set":
                diff = self.config.diff(format='set')
            elif format == "xml":
                diff = self.config.diff(format='xml')
            else:
                diff = self.config.diff()
            
            if not diff:
                self.logger.info("No configuration changes required")
                diff = "No changes required - policies already configured"
            else:
                self.logger.info(f"Generated diff with {len(diff.splitlines())} lines")
            
            # SUCCESS - send notification if in autonomous mode
            if self.autonomous_mode:
                self.safety_manager.send_netconf_event_notification(
                    'preview', self.device.hostname, True, {'diff': diff}
                )
            
            return diff
            
        except ConfigLoadError as e:
            self.logger.error(f"Failed to load configuration: {e}")
            # Rollback any loaded changes
            self.config.rollback()
            
            # FAILURE - send notification if in autonomous mode
            if self.autonomous_mode:
                self.safety_manager.send_netconf_event_notification(
                    'preview', self.device.hostname, False, {'error': str(e)}
                )
            
            raise ApplicationError(f"Configuration load failed: {str(e)}")
        except Exception as e:
            self.logger.error(f"Preview generation failed: {e}")
            self.config.rollback()
            
            # FAILURE - send notification if in autonomous mode
            if self.autonomous_mode:
                self.safety_manager.send_netconf_event_notification(
                    'preview', self.device.hostname, False, {'error': str(e)}
                )
            
            raise ApplicationError(f"Preview failed: {str(e)}")
    
    def apply_with_confirmation(self,
                               policies: List[Dict[str, str]],
                               confirm_timeout: int = 120,
                               comment: Optional[str] = None) -> ApplicationResult:
        """
        Apply policies with mode-aware finalization
        
        Args:
            policies: List of policies to apply
            confirm_timeout: Seconds to wait for confirmation (default 120)
            comment: Commit comment
            
        Returns:
            ApplicationResult with operation details
        """
        if not self.connected or not self.config:
            return ApplicationResult(
                success=False,
                hostname=self.device.hostname if self.device else "unknown",
                policies_applied=0,
                error_message="Not connected to router"
            )
        
        hostname = self.device.hostname
        self.logger.info(f"Applying {len(policies)} policies to {hostname}")
        
        # Import mode manager for finalization strategy
        import os
        from otto_bgp.appliers.mode_manager import ModeManager, CommitInfo, HealthResult
        
        try:
            # Detect mode and get finalization strategy
            mode = os.getenv('OTTO_BGP_MODE', 'system').lower()
            mode_manager = ModeManager(mode)
            finalization_strategy = mode_manager.get_finalization_strategy()
            
            self.logger.info(f"Using {mode_manager.get_mode_description()} mode")
            
            # Generate diff first
            diff = self.preview_changes(policies)
            
            if "No changes required" in diff:
                return ApplicationResult(
                    success=True,
                    hostname=hostname,
                    policies_applied=0,
                    diff_preview=diff,
                    timestamp=datetime.now().isoformat()
                )
            
            # Create commit comment
            if not comment:
                comment = f"Otto BGP - Applied {len(policies)} policies"
            
            # Perform confirmed commit
            self.logger.info(f"Initiating confirmed commit (timeout: {confirm_timeout}s)")
            
            commit_result = self.config.commit(
                comment=comment,
                confirm=confirm_timeout
            )
            
            # Get commit ID
            commit_id = None
            if hasattr(commit_result, 'commit_id'):
                commit_id = str(commit_result.commit_id)
            
            self.logger.info(f"Policies applied with confirmation pending (ID: {commit_id})")
            
            # SUCCESS - send notification if in autonomous mode
            if self.autonomous_mode:
                self.safety_manager.send_netconf_event_notification(
                    'commit', hostname, True, {
                        'commit_id': commit_id,
                        'policies': policies,
                        'diff': diff
                    }
                )
            
            # NEW: Mode-aware finalization
            commit_info = CommitInfo(
                commit_id=commit_id or "unknown",
                timestamp=datetime.now().isoformat(),
                success=True
            )
            
            # Run health checks
            health_result = self._run_health_checks()
            
            # Apply finalization strategy based on mode
            finalization_strategy.execute(self.config, commit_info, health_result)
            
            # Create successful result
            result = ApplicationResult(
                success=True,
                hostname=hostname,
                policies_applied=len(policies),
                diff_preview=diff,
                commit_id=commit_id,
                timestamp=datetime.now().isoformat()
            )
            
            return result
            
        except CommitError as e:
            self.logger.error(f"Commit failed: {e}")
            self.config.rollback()
            
            # FAILURE - send notification if in autonomous mode
            if self.autonomous_mode:
                self.safety_manager.send_netconf_event_notification(
                    'commit', hostname, False, {
                        'error': str(e),
                        'policies': policies,
                        'rollback_status': 'Automatic rollback attempted'
                    }
                )
            
            return ApplicationResult(
                success=False,
                hostname=hostname,
                policies_applied=0,
                error_message=f"Commit failed: {str(e)}"
            )
        except Exception as e:
            self.logger.error(f"Application failed: {e}")
            self.config.rollback()
            
            # FAILURE - send notification if in autonomous mode
            if self.autonomous_mode:
                self.safety_manager.send_netconf_event_notification(
                    'commit', hostname, False, {
                        'error': str(e),
                        'policies': policies,
                        'rollback_status': 'Automatic rollback attempted'
                    }
                )
            
            return ApplicationResult(
                success=False,
                hostname=hostname,
                policies_applied=0,
                error_message=f"Application failed: {str(e)}"
            )
    
    def confirm_commit(self) -> bool:
        """
        Confirm a pending confirmed commit
        
        Returns:
            True if confirmation successful
        """
        if not self.connected or not self.config:
            return False
        
        try:
            self.logger.info("Confirming commit")
            self.config.commit(comment="Otto BGP - Commit confirmed")
            self.logger.info("Commit confirmed successfully")
            return True
        except Exception as e:
            self.logger.error(f"Failed to confirm commit: {e}")
            return False
    
    def rollback_changes(self, rollback_id: Optional[int] = None) -> bool:
        """
        Rollback configuration changes
        
        Args:
            rollback_id: Specific rollback ID (0 = last change)
            
        Returns:
            True if rollback successful
        """
        if not self.connected or not self.config:
            return False
        
        try:
            rollback_id = rollback_id or 0
            self.logger.info(f"Rolling back to configuration {rollback_id}")
            
            self.config.rollback(rollback_id)
            self.config.commit(comment=f"Otto BGP - Rollback to {rollback_id}")
            
            # SUCCESS - send notification if in autonomous mode
            if self.autonomous_mode:
                self.safety_manager.send_netconf_event_notification(
                    'rollback', self.device.hostname, True, {'rollback_id': rollback_id}
                )
            
            self.logger.info("Rollback completed successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Rollback failed: {e}")
            
            # FAILURE - send notification if in autonomous mode
            if self.autonomous_mode:
                self.safety_manager.send_netconf_event_notification(
                    'rollback', self.device.hostname, False, {'error': str(e)}
                )
            
            return False
    
    def _run_health_checks(self, timeout: int = 30):
        """
        Execute post-commit health validation
        
        Args:
            timeout: Health check timeout
            
        Returns:
            HealthResult with validation details
        """
        from otto_bgp.appliers.mode_manager import HealthResult
        
        if not self.connected or not self.device:
            return HealthResult(success=False, details=[], error="Device not connected")
        
        checks = []
        try:
            # Management interface check
            mgmt_info = self.device.rpc.get_interface_information(interface_name='fxp0')
            checks.append("Management interface: OK")
            
            # BGP neighbor check
            bgp_info = self.device.rpc.get_bgp_neighbor_information()
            established = len(bgp_info.xpath('.//bgp-peer[peer-state="Established"]'))
            checks.append(f"BGP neighbors established: {established}")
            
            self.logger.info(f"Health checks passed: {checks}")
            return HealthResult(success=True, details=checks)
            
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return HealthResult(success=False, details=[], error=str(e))
    
    def disconnect(self):
        """Close connection to router"""
        if self.device and self.connected:
            hostname = self.device.hostname
            try:
                # Send disconnection notification if in autonomous mode
                if self.autonomous_mode:
                    self.safety_manager.send_netconf_event_notification(
                        'disconnect', hostname, True, {}
                    )
                
                self.device.close()
                self.connected = False
                self.logger.info("Disconnected from router")
            except Exception as e:
                self.logger.error(f"Error during disconnect: {e}")
    
    def _combine_policies_for_load(self, policies: List[Dict[str, str]]) -> str:
        """
        Combine multiple policies into single configuration load
        
        Args:
            policies: List of policy dictionaries
            
        Returns:
            Combined configuration string
        """
        combined = []
        combined.append("policy-options {")
        
        for policy in policies:
            # Add policy content (already in correct format)
            content = policy['content']
            
            # Extract just the prefix-list content
            import re
            match = re.search(r'prefix-list\s+(\S+)\s*{([^}]*)}', content, re.DOTALL)
            if match:
                list_name = match.group(1)
                list_content = match.group(2)
                
                combined.append(f"    replace: prefix-list {list_name} {{")
                for line in list_content.strip().split('\n'):
                    if line.strip():
                        combined.append(f"        {line.strip()}")
                combined.append("    }")
        
        combined.append("}")
        
        return '\n'.join(combined)
    
    def _extract_as_number(self, filename: str) -> int:
        """Extract AS number from filename"""
        import re
        match = re.search(r'AS(\d+)', filename)
        return int(match.group(1)) if match else 0
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensure disconnect"""
        self.disconnect()
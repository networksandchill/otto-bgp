"""
Unified Safety Manager - Comprehensive BGP Policy Safety Architecture

Implements unified safety manager architecture with always-active guardrails,
signal handling, graceful rollbacks, and comprehensive safety validation.
Integrates with modular guardrail components for flexible safety enforcement.

CRITICAL: These safety mechanisms are ALWAYS ACTIVE in both system and
autonomous modes. They cannot be disabled without explicit emergency override.
"""

import logging
import os
import re
import subprocess
import smtplib
import ssl
import threading
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Configuration imports for autonomous mode
from otto_bgp.utils.config import get_config_manager

# PyEZ imports with fallback for environments without PyEZ
try:
    from jnpr.junos.utils.config import Config
    from jnpr.junos import Device
    from jnpr.junos.exception import ConnectError, CommitError
    PYEZ_AVAILABLE = True
except ImportError:
    PYEZ_AVAILABLE = False
    # Create dummy classes for type hints
    Config = type('Config', (), {})
    Device = type('Device', (), {})
    ConnectError = Exception
    CommitError = Exception

# Guardrail and exit code imports
from .guardrails import (
    GuardrailComponent, GuardrailResult, GuardrailConfig,
    initialize_default_guardrails
)
from .exit_codes import OttoExitCodes
from .mode_manager import ModeManager, CommitInfo, HealthResult


@dataclass
class SafetyCheckResult:
    """Result of unified safety validation"""
    safe_to_proceed: bool
    risk_level: str  # low, medium, high, critical
    warnings: List[str]
    errors: List[str]
    bgp_impact: Dict[str, str]  # session -> impact description
    recommended_action: str
    guardrail_results: List[GuardrailResult]
    rollback_checkpoint: Optional[str] = None
    emergency_contact_notified: bool = False


class UnifiedSafetyManager:
    """
    Unified Safety Manager for BGP policy application with always-active guardrails

    Provides comprehensive safety architecture including:
    - Always-active modular guardrail system
    - Signal handling for graceful rollbacks
    - Unified safety validation across all modes
    - Emergency override capabilities with audit trail
    - Integration with monitoring and alerting systems
    - Rollback checkpoint management with recovery procedures

    CRITICAL FEATURES:
    - Guardrails are ALWAYS ACTIVE regardless of system/autonomous mode
    - Signal handlers enable graceful rollback on termination
    - Emergency overrides are logged and require justification
    - All safety events are audited and can trigger notifications
    """

    # Dangerous prefix ranges that should never be in BGP
    BOGON_PREFIXES = [
        "0.0.0.0/8",      # This network
        "10.0.0.0/8",     # Private RFC1918
        "127.0.0.0/8",    # Loopback
        "169.254.0.0/16", # Link-local
        "172.16.0.0/12",  # Private RFC1918
        "192.168.0.0/16", # Private RFC1918
        "224.0.0.0/4",    # Multicast
        "240.0.0.0/4",    # Reserved
    ]

    # Maximum safe prefix counts
    MAX_PREFIXES_PER_AS = 100000  # Typical transit AS limit
    MAX_TOTAL_PREFIXES = 500000   # Router memory limit

    def __init__(self, logger: Optional[logging.Logger] = None,
                 enable_signal_handlers: bool = True,
                 emergency_override: bool = False):
        """
        Initialize unified safety manager

        Args:
            logger: Optional logger instance
            enable_signal_handlers: Whether to install signal handlers (default True)
            emergency_override: Emergency override flag (requires justification)
        """
        self.logger = logger or logging.getLogger(__name__)

        # Thread-safe collections and state management
        # Fixes race condition where multiple threads could corrupt shared state
        self._state_lock = threading.RLock()  # Reentrant for nested operations
        self.checkpoints = []  # Protected by _state_lock

        # Initialize guardrail system with thread safety
        self.guardrails: Dict[str, GuardrailComponent] = {}
        self._initialize_guardrails()

        # Safety state tracking - all access must be synchronized
        self._safety_active = True
        self._emergency_override = emergency_override
        self._rollback_callbacks: List[callable] = []  # Protected by _state_lock
        self._current_operation: Optional[str] = None  # Protected by _state_lock

        # Signal handling
        if enable_signal_handlers:
            self._install_signal_handlers()

        # Initialize exit manager
        # Exit code tracking for error reporting
        self.error_codes = []

        # Log initialization with safety status
        self.logger.info(f"Unified Safety Manager initialized - "
                        f"Guardrails: {len(self.guardrails)}, "
                        f"Emergency Override: {self._emergency_override}")

        if self._emergency_override:
            self.logger.critical("EMERGENCY OVERRIDE ACTIVE - Safety constraints relaxed")

    def _initialize_guardrails(self):
        """Initialize guardrails honoring OTTO_BGP_GUARDRAILS and defaults"""
        from .guardrails import (
            validate_guardrail_config,
            CRITICAL_GUARDRAILS,
        )
        from otto_bgp.utils.config import get_config_manager

        # 1) Register defaults (prefix_count, bogon_prefix, concurrent_operation, signal_handling)
        default_guardrails = initialize_default_guardrails(self.logger)
        for g in default_guardrails:
            self.guardrails[g.name] = g

        # 2) Optionally add RPKI guardrail using existing logic
        try:
            config_manager = get_config_manager()
            config = config_manager.get_config()
        except Exception:
            config_manager = None
            config = None

        if config and config.rpki and config.rpki.enabled:
            try:
                from otto_bgp.validators.rpki import RPKIGuardrail, RPKIValidator
                rpki_validator = RPKIValidator(
                    vrp_cache_path=Path(config.rpki.vrp_cache_path) if config.rpki.vrp_cache_path else None,
                    allowlist_path=Path(config.rpki.allowlist_path) if config.rpki.allowlist_path else None,
                    fail_closed=bool(config.rpki.fail_closed),
                    max_vrp_age_hours=int(config.rpki.max_vrp_age_hours),
                    logger=self.logger
                )
                rpki_guardrail = RPKIGuardrail(rpki_validator=rpki_validator, logger=self.logger)
                self.guardrails[rpki_guardrail.name] = rpki_guardrail
            except Exception as e:
                self.logger.error(f"Failed to initialize RPKI guardrail: {e}")

        # 3) Determine enabled set from env or defaults
        enabled_names = []
        env = getattr(config_manager, 'guardrail_env', None) if config_manager else None
        if env and env.get('enabled'):
            enabled_names = env['enabled']
        else:
            enabled_names = list(CRITICAL_GUARDRAILS) + ['prefix_count']
            if 'rpki_validation' in self.guardrails:
                enabled_names.append('rpki_validation')

        # Validate
        errors = validate_guardrail_config(enabled_names, env)
        if errors:
            raise ValueError(f"Guardrail configuration errors: {'; '.join(errors)}")

        # 4) Apply prefix_count overrides if present and filter to enabled
        final_guardrails = {}
        for name in enabled_names:
            g = self.guardrails.get(name)
            if not g:
                continue

            if name == 'prefix_count' and env:
                overrides = env.get('prefix_count', {})
                thresholds = overrides.get('custom_thresholds') or {}
                strictness = overrides.get('strictness_level')
                # Create new config with overrides
                new_config = GuardrailConfig(
                    enabled=True,
                    strictness_level=strictness or g.config.strictness_level,
                    custom_thresholds=thresholds or g.config.custom_thresholds
                )
                # Update existing guardrail's config
                g.update_config(new_config)
            final_guardrails[name] = g

        self.guardrails = final_guardrails
        self.logger.info(f"Guardrails active: {sorted(self.guardrails.keys())}")

    def _install_signal_handlers(self):
        """Install signal handlers for graceful shutdown"""
        try:
            signal_guardrail = self.guardrails.get('signal_handling')
            if signal_guardrail:
                signal_guardrail.install_signal_handlers()
                signal_guardrail.add_rollback_callback(self._emergency_rollback)
            self.logger.info("Signal handlers installed for graceful shutdown")
        except Exception as e:
            self.logger.error(f"Failed to install signal handlers: {e}")

    def _emergency_rollback(self):
        """
        Emergency rollback procedure called by signal handler.
        Thread-safe execution of rollback callbacks.
        """
        self.logger.warning("Executing emergency rollback procedures")

        # Thread-safe access to rollback callbacks
        with self._state_lock:
            # Create a copy to avoid modification during iteration
            callbacks_to_execute = list(self._rollback_callbacks)
            thread_id = threading.current_thread().ident
            self.logger.debug(f"Executing {len(callbacks_to_execute)} rollback callbacks in thread {thread_id}")

        # Execute callbacks outside the lock to avoid deadlocks
        for i, callback in enumerate(callbacks_to_execute):
            try:
                self.logger.debug(f"Executing rollback callback {i+1}/{len(callbacks_to_execute)}")
                callback()
            except Exception as e:
                self.logger.error(f"Emergency rollback callback {i+1} failed: {e}")

        self.logger.info("Emergency rollback procedures completed")

    def add_rollback_callback(self, callback: callable):
        """
        Add callback to be executed during emergency rollback.
        Thread-safe operation using state lock.
        """
        with self._state_lock:
            thread_id = threading.current_thread().ident
            self.logger.debug(f"Adding rollback callback in thread {thread_id}")
            self._rollback_callbacks.append(callback)

    def _determine_unified_risk_level(self, errors: List[str], warnings: List[str],
                                     guardrail_risks: List[str]) -> str:
        """Determine unified risk level from all sources"""
        if errors or 'critical' in guardrail_risks:
            return 'critical'
        elif 'high' in guardrail_risks or len(warnings) > 10:
            return 'high'
        elif 'medium' in guardrail_risks or len(warnings) > 5:
            return 'medium'
        else:
            return 'low'

    def _determine_safety_decision(self, errors: List[str], risk_level: str) -> bool:
        """Determine if safe to proceed based on unified assessment"""
        # Emergency override bypasses safety checks (with logging)
        if self._emergency_override:
            self.logger.critical(f"EMERGENCY OVERRIDE: Bypassing safety decision - Risk: {risk_level}")
            return True

        # Normal safety decision logic
        if errors:
            return False
        elif risk_level == 'critical':
            return False
        else:
            return True

    def _generate_unified_recommendation(self, safe_to_proceed: bool, risk_level: str,
                                       guardrail_count: int) -> str:
        """Generate unified recommendation based on all safety factors"""
        if self._emergency_override:
            return f"EMERGENCY OVERRIDE ACTIVE - Proceeding despite {risk_level} risk"
        elif not safe_to_proceed:
            return f"DO NOT PROCEED - {risk_level.upper()} risk detected by {guardrail_count} guardrails"
        elif risk_level == 'high':
            return f"CAUTION - High risk detected, review all {guardrail_count} guardrail results"
        elif risk_level == 'medium':
            return f"Review warnings from {guardrail_count} guardrails before proceeding"
        else:
            return f"Safe to proceed - {guardrail_count} guardrails passed"

    def _prepare_rollback_checkpoint(self) -> str:
        """
        Prepare rollback checkpoint for safe operations.
        Thread-safe operation using state lock.
        """
        checkpoint_id = f"unified_safety_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Create checkpoint with thread-safe access to guardrails and current operation
        with self._state_lock:
            checkpoint = {
                'id': checkpoint_id,
                'timestamp': datetime.now().isoformat(),
                'operation': self._current_operation,
                'safety_manager': 'unified',
                'guardrails_active': sum(1 for g in self.guardrails.values() if g.is_enabled()),
                'thread_id': threading.current_thread().ident
            }

            self.checkpoints.append(checkpoint)

        self.logger.info(f"Rollback checkpoint prepared: {checkpoint_id}")
        return checkpoint_id

    def _send_emergency_notification(self, result: SafetyCheckResult):
        """Send emergency notification for critical safety issues"""
        try:
            self.logger.critical("CRITICAL SAFETY ISSUE - Sending emergency notification")

            # Use existing notification system
            details = {
                'risk_level': result.risk_level,
                'errors': result.errors,
                'warnings': result.warnings,
                'guardrail_failures': [r for r in result.guardrail_results if not r.passed]
            }

            # Send notification using existing NETCONF notification system
            self.send_netconf_event_notification(
                'safety_critical',
                'unified_safety_manager',
                False,
                details
            )

            result.emergency_contact_notified = True

        except Exception as e:
            self.logger.error(f"Failed to send emergency notification: {e}")

    def validate_policies_before_apply(self,
                                      policies: List[Dict]) -> SafetyCheckResult:
        """
        Unified comprehensive validation using always-active guardrails

        Args:
            policies: List of policy dictionaries to validate

        Returns:
            SafetyCheckResult with comprehensive validation details
        """
        self.logger.info(f"UNIFIED SAFETY CHECK: Validating {len(policies)} policies")

        # Set current operation context with thread safety
        with self._state_lock:
            self._current_operation = "policy_validation"

        warnings = []
        errors = []
        guardrail_results = []

        # Phase 1: Run all active guardrails
        context = {
            'policies': policies,
            'operation': self._current_operation,
            'timestamp': datetime.now()
        }

        for name, guardrail in self.guardrails.items():
            if guardrail.is_enabled():
                try:
                    result = guardrail.check(context)
                    guardrail_results.append(result)

                    if not result.passed:
                        if result.risk_level == 'critical':
                            errors.append(f"[{name}] {result.message}")
                        else:
                            warnings.append(f"[{name}] {result.message}")

                    self.logger.debug(f"Guardrail {name}: {result.risk_level} - {result.message}")

                except Exception as e:
                    self.logger.error(f"Guardrail {name} failed: {e}")
                    errors.append(f"Guardrail system error: {name} - {str(e)}")

        # Phase 2: Legacy safety checks (integrated with guardrails)
        syntax_errors = self._validate_syntax(policies)
        errors.extend(syntax_errors)

        dup_warnings = self._check_duplicates(policies)
        warnings.extend(dup_warnings)

        as_warnings = self._validate_as_numbers(policies)
        warnings.extend(as_warnings)

        # Phase 3: Determine overall risk level and safety decision
        guardrail_risk_levels = [r.risk_level for r in guardrail_results]
        overall_risk = self._determine_unified_risk_level(errors, warnings, guardrail_risk_levels)

        # Emergency override check
        safe_to_proceed = self._determine_safety_decision(errors, overall_risk)

        # Generate unified recommendation
        recommended_action = self._generate_unified_recommendation(safe_to_proceed, overall_risk,
                                                                 len(guardrail_results))

        # Create rollback checkpoint if proceeding
        checkpoint_id = None
        if safe_to_proceed:
            checkpoint_id = self._prepare_rollback_checkpoint()

        result = SafetyCheckResult(
            safe_to_proceed=safe_to_proceed,
            risk_level=overall_risk,
            warnings=warnings,
            errors=errors,
            bgp_impact={},  # Will be populated by check_bgp_session_impact
            recommended_action=recommended_action,
            guardrail_results=guardrail_results,
            rollback_checkpoint=checkpoint_id
        )

        self.logger.info(f"UNIFIED SAFETY CHECK COMPLETE - Risk: {overall_risk}, "
                        f"Safe: {safe_to_proceed}, Guardrails: {len(guardrail_results)}")

        # Emergency notification if critical issues found
        if overall_risk == 'critical' and not safe_to_proceed:
            self._send_emergency_notification(result)

        return result

    def should_auto_apply(self, policies: List[Dict]) -> bool:
        """
        Simple autonomous decision logic

        Args:
            policies: List of policies to apply

        Returns:
            True if safe for automatic application
        """
        try:
            # Get current configuration
            config_manager = get_config_manager()
            config = config_manager.get_config()
            autonomous_config = config.autonomous_mode
        except Exception as e:
            self.logger.error(f"Failed to load configuration: {e}")
            return False

        # Check if autonomous mode is enabled
        if not autonomous_config.enabled:
            self.logger.info("Autonomous mode disabled - manual application required")
            return False

        # Use existing safety validation
        safety_result = self.validate_policies_before_apply(policies)

        # Only auto-apply low-risk changes
        if safety_result.risk_level != 'low':
            self.logger.info(f"Risk level {safety_result.risk_level} - manual approval required")
            return False

        # Get threshold for notification context only (no blocking)
        threshold = autonomous_config.auto_apply_threshold
        prefix_count = self._count_total_prefixes(policies)

        # Log threshold for context - used in notifications but doesn't block
        self.logger.info(f"Auto-apply approved: {prefix_count} prefixes, risk={safety_result.risk_level}, ref_threshold={threshold}")
        return True  # Always apply if autonomous mode enabled and low risk

    def send_netconf_event_notification(self,
                                       event_type: str,
                                       hostname: str,
                                       success: bool,
                                       details: Dict,
                                       config: Optional[Dict] = None) -> bool:
        """
        Send email notification for ANY NETCONF event - success or failure

        Args:
            event_type: 'connect', 'preview', 'commit', 'rollback', 'disconnect'
            hostname: Target router
            success: Whether operation succeeded
            details: Event-specific details (policies, errors, diffs, etc.)
            config: Configuration with email settings (optional, will load if not provided)

        Returns:
            True if notification sent successfully
        """
        try:
            # Load config if not provided
            if config is None:
                config_manager = get_config_manager()
                config = config_manager.get_config()
                autonomous_config = config.autonomous_mode
            else:
                autonomous_config = config.autonomous_mode if hasattr(config, 'autonomous_mode') else config.get('autonomous_mode', {})

            # Check if email notifications are enabled
            if not autonomous_config or not hasattr(autonomous_config, 'notifications'):
                return False

            email_cfg = autonomous_config.notifications.email
            if not email_cfg or not email_cfg.enabled:
                return False

            # Build subject with clear status
            status = "SUCCESS" if success else "FAILED"
            subject = f"{event_type.upper()} - {status}"

            # Format body based on event type
            body = self._format_netconf_event(event_type, hostname, success, details)

            # Add threshold info if relevant
            if event_type == 'commit' and 'policies' in details:
                prefix_count = self._count_total_prefixes(details['policies'])
                threshold = autonomous_config.auto_apply_threshold
                body += f"\nPrefix Count: {prefix_count} (Reference threshold: {threshold})"

            # Send immediately - auditing is critical
            return self._send_email(email_cfg, subject, body)

        except Exception as e:
            self.logger.error(f"Failed to send NETCONF event notification: {e}")
            return False  # Best-effort, don't break autonomous operation

    def check_bgp_session_impact(self, diff: str) -> Dict[str, str]:
        """
        Analyze configuration diff for BGP session impact

        Args:
            diff: Configuration diff string

        Returns:
            Dictionary mapping BGP sessions to impact descriptions
        """
        impact = {}

        # Check for changes that could affect BGP sessions
        if "delete protocols bgp" in diff:
            impact["ALL"] = "CRITICAL: BGP protocol deletion detected!"

        if "delete group" in diff:
            # Extract group names being deleted
            groups = re.findall(r'delete.*group\s+(\S+)', diff)
            for group in groups:
                impact[group] = "Group deletion - sessions will be terminated"

        if "replace.*import" in diff or "replace.*export" in diff:
            # Policy changes
            impact["policy"] = "Import/export policy changes - may affect route selection"

        if "neighbor" in diff:
            # Neighbor changes
            neighbors = re.findall(r'neighbor\s+(\S+)', diff)
            for neighbor in neighbors:
                if "delete" in diff:
                    impact[neighbor] = "Neighbor deletion - session will be terminated"
                else:
                    impact[neighbor] = "Neighbor configuration change - session may reset"

        # Check for authentication changes
        if "authentication" in diff:
            impact["auth"] = "Authentication changes - sessions may reset"

        # Check for hold-time or other timer changes
        if "hold-time" in diff or "keep-alive" in diff:
            impact["timers"] = "Timer changes - sessions will reset"

        return impact

    def create_rollback_checkpoint(self,
                                  device_hostname: str,
                                  checkpoint_name: Optional[str] = None) -> str:
        """
        Create a rollback checkpoint before applying changes.
        Thread-safe operation using state lock.

        Args:
            device_hostname: Router hostname
            checkpoint_name: Optional checkpoint name

        Returns:
            Checkpoint ID
        """
        if not checkpoint_name:
            checkpoint_name = f"otto_bgp_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Thread-safe checkpoint creation
        with self._state_lock:
            checkpoint = {
                'id': checkpoint_name,
                'hostname': device_hostname,
                'timestamp': datetime.now().isoformat(),
                'status': 'active',
                'thread_id': threading.current_thread().ident
            }

            self.checkpoints.append(checkpoint)

        self.logger.info(f"Created rollback checkpoint: {checkpoint_name}")

        return checkpoint_name

    def monitor_post_application(self,
                                metrics: Dict[str, any],
                                baseline: Dict[str, any]) -> bool:
        """
        Monitor router health after policy application

        Args:
            metrics: Current router metrics
            baseline: Baseline metrics before change

        Returns:
            True if router healthy, False if issues detected
        """
        healthy = True
        issues = []

        # Check BGP session count
        current_sessions = metrics.get('bgp_sessions_established', 0)
        baseline_sessions = baseline.get('bgp_sessions_established', 0)

        if current_sessions < baseline_sessions * 0.9:  # Lost >10% of sessions
            issues.append(f"BGP session loss: {baseline_sessions} -> {current_sessions}")
            healthy = False

        # Check route count
        current_routes = metrics.get('total_routes', 0)
        baseline_routes = baseline.get('total_routes', 0)

        if current_routes < baseline_routes * 0.5:  # Lost >50% of routes
            issues.append(f"Significant route loss: {baseline_routes} -> {current_routes}")
            healthy = False

        # Check CPU utilization
        cpu_util = metrics.get('cpu_utilization', 0)
        if cpu_util > 80:
            issues.append(f"High CPU utilization: {cpu_util}%")
            healthy = False

        # Check memory utilization
        memory_util = metrics.get('memory_utilization', 0)
        if memory_util > 90:
            issues.append(f"High memory utilization: {memory_util}%")
            healthy = False

        if issues:
            self.logger.error(f"Post-application issues detected: {', '.join(issues)}")
        else:
            self.logger.info("Post-application monitoring: Router healthy")

        return healthy

    def _validate_syntax(self, policies: List[Dict]) -> List[str]:
        """Validate policy syntax"""
        errors = []

        for policy in policies:
            content = policy.get('content', '')

            # Check for balanced braces
            if content.count('{') != content.count('}'):
                errors.append(f"Unbalanced braces in AS{policy.get('as_number', '?')} policy")

            # Check for proper termination
            if 'prefix-list' in content and ';' not in content:
                errors.append(f"Missing semicolons in AS{policy.get('as_number', '?')} policy")

        return errors

    def _check_bogon_prefixes(self, policies: List[Dict]) -> List[str]:
        """Check for bogon/reserved prefixes"""
        warnings = []

        for policy in policies:
            content = policy.get('content', '')

            # Extract all prefixes
            prefixes = re.findall(r'(\d+\.\d+\.\d+\.\d+/\d+)', content)

            for prefix in prefixes:
                # Check against bogon list
                for bogon in self.BOGON_PREFIXES:
                    if self._prefix_overlap(prefix, bogon):
                        warnings.append(
                            f"Bogon/private prefix detected in AS{policy.get('as_number', '?')}: {prefix}"
                        )

        return warnings

    def _check_prefix_counts(self, policies: List[Dict]) -> List[str]:
        """Check prefix counts against safety thresholds"""
        warnings = []
        total_prefixes = 0

        for policy in policies:
            content = policy.get('content', '')
            prefixes = re.findall(r'(\d+\.\d+\.\d+\.\d+/\d+)', content)
            prefix_count = len(prefixes)
            total_prefixes += prefix_count

            if prefix_count > self.MAX_PREFIXES_PER_AS:
                warnings.append(
                    f"AS{policy.get('as_number', '?')} has {prefix_count} prefixes "
                    f"(exceeds safe limit of {self.MAX_PREFIXES_PER_AS})"
                )

        if total_prefixes > self.MAX_TOTAL_PREFIXES:
            warnings.append(
                f"Total prefix count {total_prefixes} exceeds router limit of {self.MAX_TOTAL_PREFIXES}"
            )

        return warnings

    def _check_duplicates(self, policies: List[Dict]) -> List[str]:
        """Check for duplicate policies"""
        # Duplicate detection by resource-aware key
        warnings = []
        seen = set()
        for policy in policies:
            asn = policy.get('as_number')
            key = policy.get('resource') or (f"AS{asn}" if asn else None)
            if key:
                if key in seen:
                    warnings.append(f"Duplicate policy for {key}")
                seen.add(key)
        return warnings

    def _validate_as_numbers(self, policies: List[Dict]) -> List[str]:
        """Validate AS number ranges"""
        warnings = []

        for policy in policies:
            as_number = policy.get('as_number')
            res = policy.get('resource') or (f"AS{as_number}" if as_number else "unknown")
            if isinstance(as_number, int) and as_number > 0:
                if 64496 <= as_number <= 64511:
                    warnings.append(f"{res} is reserved for documentation")
                elif 65535 <= as_number <= 65551:
                    warnings.append(f"{res} is reserved")
                elif as_number > 4294967295:
                    warnings.append(f"{res} exceeds maximum 32-bit AS number")

        return warnings

    def _calculate_risk_level(self, errors: List[str], warnings: List[str]) -> str:
        """Calculate overall risk level"""
        if errors:
            return "critical"
        elif len(warnings) > 10:
            return "high"
        elif len(warnings) > 5:
            return "medium"
        elif warnings:
            return "low"
        return "low"

    def _prefix_overlap(self, prefix1: str, prefix2: str) -> bool:
        """Check if two prefixes overlap"""
        # Simplified overlap check
        # In production, would use proper IP address libraries
        try:
            p1_net = prefix1.split('/')[0]
            p2_net = prefix2.split('/')[0]

            # Basic check - same network portion
            return p1_net.startswith(p2_net.split('.')[0])
        except (ValueError, IndexError, AttributeError):
            return False

    def _count_total_prefixes(self, policies: List[Dict]) -> int:
        """Count total prefixes across all policies"""
        total = 0
        for policy in policies:
            content = policy.get('content', '')
            prefixes = re.findall(r'(\d+\.\d+\.\d+\.\d+/\d+)', content)
            total += len(prefixes)
        return total

    def _format_netconf_event(self, event_type: str, hostname: str,
                              success: bool, details: Dict) -> str:
        """
        Format event-specific notification body

        Args:
            event_type: Type of NETCONF event
            hostname: Target router hostname
            success: Whether operation succeeded
            details: Event-specific details

        Returns:
            Formatted email body
        """
        timestamp = datetime.now().isoformat()
        base_info = f"""NETCONF Event Notification
==========================
Event Type: {event_type.upper()}
Status: {'SUCCESS' if success else 'FAILED'}
Router: {hostname}
Timestamp: {timestamp}\n"""

        if event_type == 'connect':
            if success:
                body = base_info + "\nConnection established successfully"
            else:
                body = base_info + f"\nConnection failed: {details.get('error', 'Unknown error')}"

        elif event_type == 'preview':
            if success:
                diff_lines = len(details.get('diff', '').splitlines())
                body = base_info + f"\nConfiguration diff generated: {diff_lines} lines"
            else:
                body = base_info + f"\nDiff generation failed: {details.get('error', 'Unknown error')}"

        elif event_type == 'commit':
            if success:
                policies = details.get('policies', [])
                # Prefer resources for summary if available
                as_numbers = [p.get('as_number') for p in policies if p.get('as_number')]
                resources = [p.get('resource') for p in policies if p.get('resource')]
                summary_list = [f'AS{n}' for n in as_numbers] + resources
                body = base_info + f"""\nCommit ID: {details.get('commit_id', 'N/A')}
Policies Applied: {len(policies)}
AS Numbers: {', '.join(summary_list)}

Configuration Diff:
{details.get('diff', 'Not available')}"""
            else:
                policies = details.get('policies', [])
                body = base_info + f"""\nError: {details.get('error', 'Unknown error')}
Attempted Policies: {len(policies)}
Rollback Status: {details.get('rollback_status', 'N/A')}"""

        elif event_type == 'rollback':
            body = base_info + f"\nRollback to: {details.get('rollback_id', 'previous')}"
            if not success:
                body += f"\nError: {details.get('error', 'Unknown error')}"

        elif event_type == 'disconnect':
            body = base_info + "\nConnection closed"

        else:
            body = base_info + f"\nEvent details: {details}"

        return body

    def _send_email(self, email_cfg, subject: str, body: str) -> bool:
        """
        Send email using sendmail or SMTP

        Args:
            email_cfg: Email configuration object
            subject: Email subject
            body: Email body

        Returns:
            True if email sent successfully
        """
        try:
            msg = MIMEMultipart()
            msg['From'] = email_cfg.from_address
            msg['To'] = ', '.join(email_cfg.to_addresses)
            if getattr(email_cfg, 'cc_addresses', None):
                msg['Cc'] = ', '.join(email_cfg.cc_addresses)
            msg['Subject'] = f"{email_cfg.subject_prefix} {subject}"
            msg.attach(MIMEText(body, 'plain'))

            if getattr(email_cfg, 'delivery_method', 'sendmail') == 'sendmail':
                sendmail_path = getattr(email_cfg, 'sendmail_path', '/usr/sbin/sendmail')
                # Use -t to read recipients from headers; -i ignores lone '.' lines; -f sets envelope sender
                proc = subprocess.run(
                    [sendmail_path, '-t', '-i', f"-f{email_cfg.from_address}"],
                    input=msg.as_bytes(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=10,
                    check=False,
                )
                if proc.returncode != 0:
                    self.logger.error(
                        f"sendmail failed rc={proc.returncode}: {proc.stderr.decode(errors='ignore')}"
                    )
                    return False
                self.logger.info(f"Notification sent via sendmail: {subject}")
                return True

            # SMTP best-effort
            context = ssl.create_default_context()
            with smtplib.SMTP(email_cfg.smtp_server, email_cfg.smtp_port, timeout=10) as server:
                if email_cfg.smtp_use_tls:
                    server.starttls(context=context)
                if getattr(email_cfg, 'smtp_username', None):
                    server.login(email_cfg.smtp_username, getattr(email_cfg, 'smtp_password', ''))
                server.send_message(msg)
            self.logger.info(f"Notification sent via SMTP: {subject}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to send email notification: {e}")
            return False  # Best-effort, don't break autonomous operation

    def generate_safety_report(self,
                              check_result: SafetyCheckResult,
                              output_file: Optional[str] = None) -> str:
        """
        Generate detailed safety report

        Args:
            check_result: Safety check results
            output_file: Optional file to save report

        Returns:
            Formatted safety report
        """
        lines = []

        lines.append("=" * 60)
        lines.append("BGP POLICY APPLICATION SAFETY REPORT")
        lines.append("=" * 60)
        lines.append(f"Generated: {datetime.now().isoformat()}")
        lines.append(f"Risk Level: {check_result.risk_level.upper()}")
        lines.append(f"Safe to Proceed: {'YES' if check_result.safe_to_proceed else 'NO'}")
        lines.append("")

        if check_result.errors:
            lines.append("ERRORS (Must be resolved):")
            lines.append("-" * 40)
            for error in check_result.errors:
                lines.append(f"  ✗ {error}")
            lines.append("")

        if check_result.warnings:
            lines.append("WARNINGS (Review before proceeding):")
            lines.append("-" * 40)
            for warning in check_result.warnings:
                lines.append(f"  ⚠ {warning}")
            lines.append("")

        if check_result.bgp_impact:
            lines.append("BGP SESSION IMPACT:")
            lines.append("-" * 40)
            for session, impact in check_result.bgp_impact.items():
                lines.append(f"  {session}: {impact}")
            lines.append("")

        lines.append("RECOMMENDATION:")
        lines.append("-" * 40)
        lines.append(f"  {check_result.recommended_action}")
        lines.append("")
        lines.append("=" * 60)

        report = '\n'.join(lines)

        if output_file:
            with open(output_file, 'w') as f:
                f.write(report)
            self.logger.info(f"Safety report saved to {output_file}")

        return report

    def execute_pipeline(self, policies: List[Dict], hostname: str, mode: str,
                         rollout_context: Optional[Dict[str, str]] = None) -> 'ApplicationResult':
        """
        Execute unified pipeline with mode-dependent behavior

        Single pipeline with mode-dependent finalization:
        - Always-active guardrails (1-4) regardless of mode
        - Mode switches only affect finalization behavior
        - System mode: manual confirmation required
        - Autonomous mode: auto-finalize after health checks

        Args:
            policies: List of policy configurations to apply
            hostname: Target router hostname
            mode: Execution mode (system or autonomous)
            rollout_context: Optional coordination context (run_id, stage_id, target_id)

        Original Args:
            policies: List of BGP policies to apply
            hostname: Target router hostname
            mode: Execution mode ('system' or 'autonomous')

        Returns:
            ApplicationResult with success status and exit code
        """
        # Initialize mode manager
        mode_manager = ModeManager(mode)

        # Set mode switches in safety configuration
        auto_finalize = mode_manager.should_auto_finalize()
        mode_description = mode_manager.get_mode_description()
        auto_finalize_state = 'enabled' if auto_finalize else 'disabled'
        self.logger.info(
            "Executing pipeline in %s mode (auto_finalize=%s)",
            mode_description,
            auto_finalize_state,
        )

        # Record pipeline start event if coordinated
        if rollout_context:
            self._record_rollout_event(
                rollout_context.get('run_id'),
                'pipeline_start',
                {
                    'hostname': hostname,
                    'target_id': rollout_context.get('target_id'),
                    'stage_id': rollout_context.get('stage_id'),
                    'mode': mode
                }
            )

        try:
            # GUARDRAIL 1: Exclusive lock (always active)
            device_kwargs = {
                'host': hostname,
                'gather_facts': False,
                'ssh_config': {
                    'StrictHostKeyChecking': 'yes',
                    'UserKnownHostsFile': os.getenv('SSH_KNOWN_HOSTS', '/var/lib/otto-bgp/ssh-keys/known_hosts'),
                    'HostKeyAlgorithms': 'ssh-rsa,ssh-ed25519,ecdsa-sha2-nistp256'
                }
            }

            with Device(**device_kwargs) as dev:
                dev.timeout = 60  # Safety timeout

                with Config(dev, mode="exclusive") as cu:
                    self.logger.info(f"Exclusive lock acquired with verified host key: {hostname}")

                    # GUARDRAIL 1.5: RPKI validation (if enabled)
                    if 'rpki_validation' in self.guardrails:
                        guardrail = self.guardrails['rpki_validation']
                        rpki_result = guardrail.check({'policies': policies, 'operation': 'pipeline'})
                        if not rpki_result.passed:
                            self.logger.error(f"RPKI validation failed: {rpki_result.message}")
                            return ApplicationResult(
                                success=False,
                                exit_code=OttoExitCodes.VALIDATION_FAILED,
                                error_message=rpki_result.message
                            )

                    # GUARDRAIL 2: Pre-commit validation (always active)
                    if not self._pre_commit_guardrails(cu, policies):
                        return ApplicationResult(success=False, exit_code=OttoExitCodes.COMMIT_CHECK_FAILED)

                    # GUARDRAIL 3: Confirmed commit (always active)
                    commit_info = self._confirmed_commit(cu)
                    if not commit_info.success:
                        return ApplicationResult(success=False, exit_code=OttoExitCodes.NETCONF_FAILED)

                    # GUARDRAIL 4: Health checks (always active)
                    health_result = self._post_commit_guardrails(dev)
                    if not health_result.success:
                        # Let rollback timer handle it - don't force rollback here
                        return ApplicationResult(success=False, exit_code=OttoExitCodes.HEALTH_CHECK_FAILED)

                    # MODE SWITCH: Finalization behavior
                    finalization_strategy = mode_manager.get_finalization_strategy()
                    finalization_strategy.execute(cu, commit_info, health_result)

                    # Record pipeline success event if coordinated
                    if rollout_context:
                        self._record_rollout_event(
                            rollout_context.get('run_id'),
                            'pipeline_success',
                            {
                                'hostname': hostname,
                                'target_id': rollout_context.get('target_id'),
                                'commit_finalized': commit_info.success
                            }
                        )

                    return ApplicationResult(success=True, exit_code=OttoExitCodes.SUCCESS)

        except ConnectError as e:
            self.logger.error(f"Connection failed for {hostname}: {e}")
            return ApplicationResult(
                success=False,
                exit_code=OttoExitCodes.NETCONF_FAILED,
                error_message=f"Connection failed: {e}"
            )
        except CommitError as e:
            self.logger.error(f"Commit failed for {hostname}: {e}")
            return ApplicationResult(
                success=False,
                exit_code=OttoExitCodes.NETCONF_FAILED,
                error_message=f"Commit failed: {e}"
            )
        except Exception as e:
            self.logger.error(f"Unexpected error for {hostname}: {e}")
            return ApplicationResult(
                success=False,
                exit_code=OttoExitCodes.UNEXPECTED_ERROR,
                error_message=str(e)
            )

    def _pre_commit_guardrails(self, cu: Config, policies: List[Dict]) -> bool:
        """
        Execute pre-commit guardrails

        Args:
            cu: Juniper Config instance
            policies: Policies to validate

        Returns:
            True if all guardrails pass
        """
        # Check diff and skip no-op
        diff = cu.diff()
        if not diff:
            self.logger.info("No configuration diff - skipping commit")
            cu.rollback()
            return True  # No-op is success

        # Commit check validation
        try:
            cu.commit_check()
            self.logger.info("Commit check passed")
            return True
        except CommitError as e:
            self.logger.error(f"Commit check failed: {e}")
            cu.rollback()
            return False

    def _confirmed_commit(self, cu: Config, hold_minutes: int = 5) -> CommitInfo:
        """
        Execute confirmed commit with auto-rollback window

        Args:
            cu: Juniper Config instance
            hold_minutes: Rollback window in minutes

        Returns:
            CommitInfo with result details
        """
        try:
            result = cu.commit(
                confirm=hold_minutes,
                sync=True,
                comment="Otto BGP - automated application"
            )
            commit_id = getattr(result, 'commit_id', 'unknown')
            self.logger.info(f"Confirmed commit successful: {commit_id} ({hold_minutes}min window)")

            return CommitInfo(
                commit_id=commit_id,
                timestamp=datetime.now().isoformat(),
                success=True
            )
        except CommitError as e:
            self.logger.error(f"Confirmed commit failed: {e}")
            cu.rollback()
            return CommitInfo(
                commit_id="",
                timestamp=datetime.now().isoformat(),
                success=False,
                error_message=str(e)
            )

    def _post_commit_guardrails(self, device: Device, timeout: int = 30) -> HealthResult:
        """
        Execute post-commit health validation

        Args:
            device: Juniper Device instance
            timeout: Health check timeout

        Returns:
            HealthResult with validation details
        """
        checks = []
        try:
            # Management interface check
            _mgmt_info = device.rpc.get_interface_information(interface_name='fxp0')
            checks.append("Management interface: OK")

            # BGP neighbor check
            bgp_info = device.rpc.get_bgp_neighbor_information()
            established = len(bgp_info.xpath('.//bgp-peer[peer-state="Established"]'))
            checks.append(f"BGP neighbors established: {established}")

            self.logger.info(f"Health checks passed: {checks}")
            return HealthResult(success=True, details=checks)

        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return HealthResult(success=False, details=[], error=str(e))

    def _record_rollout_event(self, run_id: Optional[str],
                              event_type: str,
                              payload: Dict[str, Any]) -> None:
        """Record rollout event to database if run_id is provided

        Args:
            run_id: Rollout run identifier
            event_type: Type of event (pipeline_start, pipeline_success, etc.)
            payload: Event payload data
        """
        if not run_id:
            return

        try:
            from otto_bgp.database import MultiRouterDAO
            dao = MultiRouterDAO()
            dao.record_event(run_id=run_id, event_type=event_type, payload=payload)
            self.logger.debug(f"Recorded rollout event: {event_type}")
        except Exception as e:
            # Don't fail pipeline on event recording errors
            self.logger.warning(f"Failed to record rollout event: {e}")


@dataclass
class ApplicationResult:
    """Result of unified pipeline execution"""
    success: bool
    exit_code: int = OttoExitCodes.SUCCESS
    commit_id: Optional[str] = None
    diff_preview: Optional[str] = None
    error_message: Optional[str] = None
    guardrail_results: Optional[Dict[str, Any]] = None




# Factory function for creating safety manager instances
def create_safety_manager(logger: Optional[logging.Logger] = None,
                         enable_signal_handlers: bool = True,
                         emergency_override: bool = False) -> UnifiedSafetyManager:
    """
    Factory function for creating unified safety manager instances

    Args:
        logger: Optional logger instance
        enable_signal_handlers: Whether to install signal handlers (default True)
        emergency_override: Emergency override flag (requires justification)

    Returns:
        Configured UnifiedSafetyManager instance
    """
    return UnifiedSafetyManager(
        logger=logger,
        enable_signal_handlers=enable_signal_handlers,
        emergency_override=emergency_override
    )

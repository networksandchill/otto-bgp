"""
Juniper NETCONF Policy Applier - Automated BGP Policy Application

Uses PyEZ (Junos Python Extension) for NETCONF-based policy application.
Implements safety mechanisms including preview, confirmation, and rollback.

CRITICAL: Test in lab environment before production use.
"""

import errno
import logging
import socket
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Unified safety manager for NETCONF event notifications and guardrails
from otto_bgp.appliers.safety import UnifiedSafetyManager

# Timeout and retry utilities
from otto_bgp.utils.timeout_config import (
    ExponentialBackoff,
    TimeoutContext,
    TimeoutType,
)

# PyEZ imports with fallback for environments without PyEZ
try:
    from jnpr.junos import Device
    from jnpr.junos.exception import (
        CommitError,
        ConfigLoadError,
        ConnectError,
        RpcError,
    )
    from jnpr.junos.utils.config import Config

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

    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        safety_manager: Optional[UnifiedSafetyManager] = None,
    ):
        """
        Initialize the policy applier

        Args:
            logger: Optional logger instance
            safety_manager: Optional unified safety manager for autonomous
                mode notifications and guardrails
        """
        self.logger = logger or logging.getLogger(__name__)
        self.safety_manager = safety_manager or UnifiedSafetyManager(logger=self.logger)

        if not PYEZ_AVAILABLE:
            msg = "PyEZ not available - applier functionality limited"
            self.logger.warning(msg)
            self.logger.warning("Install with: pip install junos-eznc")

        self.device = None
        self.config = None
        self.connected = False
        self.autonomous_mode = False  # Set based on configuration

    def _check_autonomous_mode(self) -> bool:
        """
        Check if autonomous mode is enabled and notifications should be
        sent
        """
        try:
            from otto_bgp.utils.config import get_config_manager

            config_manager = get_config_manager()
            config = config_manager.get_config()
            return (
                config.autonomous_mode.enabled
                and config.autonomous_mode.notifications.email.enabled
            )
        except Exception as e:
            self.logger.debug(f"Could not check autonomous mode: {e}")
            return False

    def _is_retryable_netconf_error(self, e: Exception) -> bool:
        """
        Classify NETCONF errors as retryable or fatal

        Args:
            e: Exception to classify

        Returns:
            True if error is retryable (transient), False if fatal
        """
        error_str = str(e).lower()

        # FATAL errors (do not retry)
        if isinstance(e, ConnectError):
            if "auth" in error_str or "permission" in error_str:
                return False
            if "host key" in error_str:
                return False

        if isinstance(e, (CommitError, ConfigLoadError)):
            return False

        # RETRYABLE errors (transient failures)
        if isinstance(e, ConnectError):
            if "timeout" in error_str or "refused" in error_str:
                return True

        if isinstance(e, RpcError):
            if "timeout" in error_str or "temporary" in error_str:
                return True

        if isinstance(e, (socket.timeout, TimeoutError)):
            return True

        if isinstance(e, OSError):
            retryable_errnos = [errno.ETIMEDOUT, errno.ECONNREFUSED, errno.EHOSTUNREACH]
            if hasattr(e, "errno") and e.errno in retryable_errnos:
                return True

        return False

    def _with_backoff(
        self,
        func: Callable,
        *,
        max_retries: int = 3,
        timeout_ctx: Optional[TimeoutContext] = None,
        operation_name: str = "operation",
    ) -> Any:
        """
        Execute function with exponential backoff retry

        Args:
            func: Function to execute
            max_retries: Maximum retry attempts
            timeout_ctx: Optional timeout context
            operation_name: Name of operation for logging

        Returns:
            Result from successful function execution

        Raises:
            Last exception if all retries fail
        """
        backoff = ExponentialBackoff(
            initial_delay=1.0,
            max_delay=30.0,
            backoff_factor=2.0,
            max_retries=max_retries,
        )

        last_exception = None
        first_failure_notified = False
        attempt_count = 0
        start_time = time.time()

        while attempt_count <= max_retries:
            try:
                return func()
            except Exception as e:
                last_exception = e
                attempt_count += 1

                # Check if error is retryable
                if not self._is_retryable_netconf_error(e):
                    error_msg = f"{operation_name} failed with fatal error: {e}"
                    self.logger.error(error_msg)
                    raise

                # First failure notification (immediate in autonomous mode)
                if not first_failure_notified and self.autonomous_mode:
                    msg = f"{operation_name} failed (attempt 1), will retry: {e}"
                    self.logger.warning(msg)
                    try:
                        event_type = (
                            "commit"
                            if operation_name == "netconf_commit"
                            else "connect"
                        )
                        hostname = getattr(
                            getattr(self, "device", None), "hostname", "unknown"
                        )
                        notification_data = {
                            "error": str(e),
                            "attempt": 1,
                            "transient": True,
                        }
                        self.safety_manager.send_netconf_event_notification(
                            event_type, hostname, False, notification_data
                        )
                    except Exception:
                        pass
                    first_failure_notified = True

                # Check if we should retry
                if attempt_count > max_retries:
                    break

                # Check timeout before backoff delay
                if timeout_ctx:
                    next_delay = backoff.initial_delay * (
                        backoff.backoff_factor**backoff.attempt
                    )
                    if timeout_ctx.remaining_time() < next_delay:
                        self.logger.debug(
                            "Insufficient time remaining for retry, aborting"
                        )
                        break

                # Perform backoff delay
                if not backoff.delay(timeout_ctx):
                    break

                # Debug logging for retry attempts (no notifications)
                retry_msg = f"{operation_name} retry {attempt_count}/{max_retries}"
                self.logger.debug(retry_msg)

        # Final failure notification with retry summary
        total_duration = time.time() - start_time
        if self.autonomous_mode and last_exception:
            self.logger.error(
                f"{operation_name} failed after {attempt_count} attempts "
                f"({total_duration:.2f}s): {last_exception}"
            )
            # Send notification with complete retry summary
            try:
                event_type = (
                    "commit" if operation_name == "netconf_commit" else "connect"
                )
                hostname = getattr(getattr(self, "device", None), "hostname", "unknown")
                notification_data = {
                    "attempt_count": attempt_count,
                    "total_duration": total_duration,
                    "last_error": str(last_exception),
                    "final_failure": True,
                }
                self.safety_manager.send_netconf_event_notification(
                    event_type, hostname, False, notification_data
                )
            except Exception:
                pass

        raise last_exception

    def _fetch_current_state(self) -> str:
        """
        Fetch current router state for comparison

        Returns:
            Current configuration as string

        Raises:
            ApplicationError: If state fetch fails
        """
        if not self.connected or not self.device:
            raise ApplicationError("Not connected to router")

        try:
            # Fetch policy-options and protocols bgp configuration
            policy_filter = "<configuration><policy-options/></configuration>"
            policy_config = self.device.rpc.get_config(
                filter_xml=policy_filter, options={"format": "text"}
            )

            bgp_filter = "<configuration><protocols><bgp/></protocols></configuration>"
            bgp_config = self.device.rpc.get_config(
                filter_xml=bgp_filter, options={"format": "text"}
            )

            # Combine configurations
            policy_text = str(policy_config.text)
            bgp_text = str(bgp_config.text)
            current_state = policy_text + "\n" + bgp_text
            return current_state

        except Exception as e:
            self.logger.warning(f"Could not fetch current state: {e}")
            return ""

    def _preflight_validation(self, configuration: str) -> None:
        """
        Validate configuration before loading

        Args:
            configuration: Configuration to validate

        Raises:
            ApplicationError: If critical validation issues found
        """
        from otto_bgp.appliers.adapter import PolicyAdapter

        try:
            adapter = PolicyAdapter(logger=self.logger)
            validation_issues = adapter.validate_adapted_config(configuration)

            if not validation_issues:
                self.logger.debug("Preflight validation passed")
                return

            # Classify issues by severity
            critical_issues = []
            warning_issues = []

            for issue in validation_issues:
                issue_lower = issue.lower()
                is_duplicate = "duplicate prefix-list" in issue_lower
                is_undefined = "referenced policy not defined" in issue_lower

                if is_duplicate or is_undefined:
                    critical_issues.append(issue)
                elif "empty prefix-list" in issue_lower:
                    warning_issues.append(issue)
                else:
                    # Unknown issue type, treat as warning
                    warning_issues.append(issue)

            # Log warnings
            for warning in warning_issues:
                self.logger.warning(f"Preflight warning: {warning}")

            # Raise on critical issues
            if critical_issues:
                error_msg = "Critical preflight validation failures:\n"
                for issue in critical_issues:
                    error_msg += f"  - {issue}\n"

                self.logger.error(error_msg)

                # Send notification if in autonomous mode
                if self.autonomous_mode:
                    self.safety_manager.send_netconf_event_notification(
                        "validation",
                        self.device.hostname,
                        False,
                        {"critical_issues": critical_issues},
                    )

                raise ApplicationError(error_msg.strip())

        except ApplicationError:
            raise
        except Exception as e:
            self.logger.warning(f"Preflight validation error: {e}")

    def connect_to_router(
        self,
        hostname: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        port: int = 830,
        timeout: int = 30,
    ) -> Device:
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
            msg = "PyEZ not installed - cannot connect to router"
            raise ConnectionError(msg)

        self.logger.info(f"Connecting to router: {hostname}")

        try:
            # Create device connection
            device_params = {
                "host": hostname,
                "port": port,
                "gather_facts": True,
                "auto_probe": 0,
            }

            if username:
                device_params["user"] = username
            if password:
                device_params["password"] = password

            self.device = Device(**device_params)

            # Wrap Device.open() with backoff retry
            def open_device():
                self.device.open()
                return self.device

            timeout_ctx = TimeoutContext(
                TimeoutType.NETCONF_OPERATION, "netconf_connect", timeout
            )
            with timeout_ctx:
                self._with_backoff(
                    open_device,
                    max_retries=3,
                    timeout_ctx=timeout_ctx,
                    operation_name="netconf_connect",
                )

            # Bind configuration handler
            self.config = Config(self.device)

            self.connected = True
            self.autonomous_mode = self._check_autonomous_mode()

            device_model = self.device.facts.get("model", "Unknown")
            self.logger.info(f"Connected to {hostname} - {device_model}")

            # SUCCESS - send notification if in autonomous mode
            if self.autonomous_mode:
                self.safety_manager.send_netconf_event_notification(
                    "connect", hostname, True, {}
                )

            return self.device

        except ConnectError as e:
            self.logger.error(f"Failed to connect to {hostname}: {e}")

            # FAILURE - send notification if possible
            try:
                if self._check_autonomous_mode():
                    event_data = {"error": str(e)}
                    self.safety_manager.send_netconf_event_notification(
                        "connect", hostname, False, event_data
                    )
            except Exception:
                pass  # Don't let notification failure mask original error

            error_msg = f"Cannot connect to {hostname}: {str(e)}"
            raise ConnectionError(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error connecting to {hostname}: {e}"
            self.logger.error(error_msg)

            # FAILURE - send notification if possible
            try:
                if self._check_autonomous_mode():
                    self.safety_manager.send_netconf_event_notification(
                        "connect", hostname, False, {"error": str(e)}
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
            msg = f"Policies directory not found: {policies_dir}"
            self.logger.warning(msg)
            return policies

        # Load all Otto-generated policy files (ASN or IRR object)
        # Pattern matches: AS<number>_policy.txt and
        # IRR_<object>_policy.txt
        policy_files = sorted(
            [
                *policies_dir.glob("AS*_policy.txt"),
                *policies_dir.glob("IRR_*_policy.txt"),
            ]
        )

        for policy_file in policy_files:
            try:
                content = policy_file.read_text()
                as_number = self._extract_as_number(policy_file.name)

                # Derive resource from filename stem
                # e.g., "AS13335_policy" or "IRR_RS-FOO_policy"
                stem = policy_file.stem
                if stem.endswith("_policy"):
                    # Strip "_policy" suffix -> "AS13335" or "IRR_RS-FOO"
                    resource = stem[:-7]
                else:
                    resource = stem
                policies.append(
                    {
                        "as_number": as_number,
                        "filename": policy_file.name,
                        "content": content,
                        "path": str(policy_file),
                        "resource": resource,
                    }
                )

                self.logger.debug(f"Loaded policy: {policy_file.name}")

            except Exception as e:
                self.logger.error(f"Failed to load {policy_file}: {e}")

        loaded_count = len(policies)
        self.logger.info(f"Loaded {loaded_count} policies from {policies_dir}")
        return policies

    def preview_changes(
        self, policies: List[Dict[str, str]], format: str = "text"
    ) -> str:
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

            # Preflight validation before load
            self._preflight_validation(combined_config)

            # Load configuration in merge mode (don't replace)
            self.config.load(combined_config, format="text", merge=True)

            # Get diff
            if format == "set":
                diff = self.config.diff(format="set")
            elif format == "xml":
                diff = self.config.diff(format="xml")
            else:
                diff = self.config.diff()

            if not diff:
                self.logger.info("No configuration changes required")
                msg = "No changes required - policies already configured"
                diff = msg
            else:
                line_count = len(diff.splitlines())
                self.logger.info(f"Generated diff with {line_count} lines")

            # SUCCESS - send notification if in autonomous mode
            if self.autonomous_mode:
                event_data = {"diff": diff}
                self.safety_manager.send_netconf_event_notification(
                    "preview", self.device.hostname, True, event_data
                )

            return diff

        except ConfigLoadError as e:
            self.logger.error(f"Failed to load configuration: {e}")
            # Rollback any loaded changes
            self.config.rollback()

            # FAILURE - send notification if in autonomous mode
            if self.autonomous_mode:
                event_data = {"error": str(e)}
                self.safety_manager.send_netconf_event_notification(
                    "preview", self.device.hostname, False, event_data
                )

            error_msg = f"Configuration load failed: {str(e)}"
            raise ApplicationError(error_msg)
        except Exception as e:
            self.logger.error(f"Preview generation failed: {e}")
            self.config.rollback()

            # FAILURE - send notification if in autonomous mode
            if self.autonomous_mode:
                event_data = {"error": str(e)}
                self.safety_manager.send_netconf_event_notification(
                    "preview", self.device.hostname, False, event_data
                )

            raise ApplicationError(f"Preview failed: {str(e)}")

    def apply_with_confirmation(
        self,
        policies: List[Dict[str, str]],
        confirm_timeout: int = 10,
        comment: Optional[str] = None,
    ) -> ApplicationResult:
        """
        Apply policies with mode-aware finalization

        Args:
            policies: List of policies to apply
            confirm_timeout: Minutes for auto-rollback if not confirmed
                (default 10)
            comment: Commit comment

        Returns:
            ApplicationResult with operation details
        """
        if not self.connected or not self.config:
            return ApplicationResult(
                success=False,
                hostname=self.device.hostname if self.device else "unknown",
                policies_applied=0,
                error_message="Not connected to router",
            )

        hostname = self.device.hostname
        self.logger.info(f"Applying {len(policies)} policies to {hostname}")

        # Import mode manager for finalization strategy
        import os

        from otto_bgp.appliers.mode_manager import CommitInfo, ModeManager

        try:
            # Detect mode and get finalization strategy
            mode = os.getenv("OTTO_BGP_MODE", "system").lower()
            mode_manager = ModeManager(mode)
            strategy = mode_manager.get_finalization_strategy()

            mode_desc = mode_manager.get_mode_description()
            self.logger.info(f"Using {mode_desc} mode")

            # Optional: Detect no-op by comparing with current state
            # This saves RPC churn for redundant commits
            try:
                current_state = self._fetch_current_state()
                combined_config = self._combine_policies_for_load(policies)

                # Simple comparison - check if new config is subset
                # of current state
                config_lines = set(
                    line.strip()
                    for line in combined_config.splitlines()
                    if line.strip() and not line.strip().startswith("#")
                )
                current_lines = set(
                    line.strip() for line in current_state.splitlines() if line.strip()
                )

                if config_lines.issubset(current_lines):
                    no_op_msg = (
                        "No changes required - policies already configured "
                        "(detected via state comparison)"
                    )
                    self.logger.info(no_op_msg)
                    return ApplicationResult(
                        success=True,
                        hostname=hostname,
                        policies_applied=0,
                        diff_preview=no_op_msg,
                        timestamp=datetime.now().isoformat(),
                    )
            except Exception as e:
                # If pre-check fails, fall back to normal diff generation
                self.logger.debug(f"No-op detection failed, proceeding with diff: {e}")

            # Generate diff first
            diff = self.preview_changes(policies)

            if "No changes required" in diff:
                return ApplicationResult(
                    success=True,
                    hostname=hostname,
                    policies_applied=0,
                    diff_preview=diff,
                    timestamp=datetime.now().isoformat(),
                )

            # Create commit comment
            if not comment:
                policy_count = len(policies)
                comment = f"Otto BGP - Applied {policy_count} policies"

            # Perform confirmed commit with backoff retry
            timeout_msg = f"Initiating confirmed commit (timeout: {confirm_timeout}min)"
            self.logger.info(timeout_msg)

            def perform_commit():
                return self.config.commit(comment=comment, confirm=confirm_timeout)

            timeout_ctx = TimeoutContext(
                TimeoutType.NETCONF_OPERATION, "netconf_commit", 300
            )
            with timeout_ctx:
                commit_result = self._with_backoff(
                    perform_commit,
                    max_retries=3,
                    timeout_ctx=timeout_ctx,
                    operation_name="netconf_commit",
                )

            # Get commit ID
            commit_id = None
            if hasattr(commit_result, "commit_id"):
                commit_id = str(commit_result.commit_id)

            pending_msg = (
                f"Policies applied with confirmation pending (ID: {commit_id})"
            )
            self.logger.info(pending_msg)

            # SUCCESS - send notification if in autonomous mode
            if self.autonomous_mode:
                event_data = {
                    "commit_id": commit_id,
                    "policies": policies,
                    "diff": diff,
                }
                self.safety_manager.send_netconf_event_notification(
                    "commit", hostname, True, event_data
                )

            # NEW: Mode-aware finalization
            commit_info = CommitInfo(
                commit_id=commit_id or "unknown",
                timestamp=datetime.now().isoformat(),
                success=True,
            )

            # Run health checks
            health_result = self._run_health_checks()

            # Apply finalization strategy based on mode
            strategy.execute(self.config, commit_info, health_result)

            # Create successful result
            result = ApplicationResult(
                success=True,
                hostname=hostname,
                policies_applied=len(policies),
                diff_preview=diff,
                commit_id=commit_id,
                timestamp=datetime.now().isoformat(),
            )

            return result

        except (CommitError, RpcError) as e:
            error_type = type(e).__name__
            self.logger.error(f"Commit failed ({error_type}): {e}")

            # Check if error is retryable (transient)
            is_transient = self._is_retryable_netconf_error(e)

            if is_transient:
                # Check CommitRetryGuardrail before attempting recovery
                from otto_bgp.appliers.guardrails import CommitRetryGuardrail

                guardrail_context = {"hostname": hostname}
                # Get the commit_retry guardrail from safety_manager
                try:
                    guardrails = self.safety_manager.guardrails
                    commit_retry_guardrail = next(
                        (
                            g
                            for g in guardrails.values()
                            if isinstance(g, CommitRetryGuardrail)
                        ),
                        None,
                    )

                    if commit_retry_guardrail:
                        guardrail_result = commit_retry_guardrail.check(
                            guardrail_context
                        )

                        if not guardrail_result.passed:
                            # Circuit breaker triggered
                            breaker_msg = (
                                f"Circuit breaker blocked retry: "
                                f"{guardrail_result.message}"
                            )
                            self.logger.error(breaker_msg)
                            self.config.rollback()

                            if self.autonomous_mode:
                                event_data = {
                                    "error": str(e),
                                    "circuit_breaker": True,
                                    "guardrail_message": guardrail_result.message,
                                }
                                notif = (
                                    self.safety_manager.send_netconf_event_notification
                                )
                                notif("commit", hostname, False, event_data)

                            error_msg = f"Circuit breaker: {guardrail_result.message}"
                            raise ApplicationError(error_msg)

                        # Attempt commit recovery
                        self.logger.info(
                            "Attempting commit recovery (reconnect and retry)"
                        )

                        try:
                            # Reconnect
                            self.device.close()
                            self.device.open()
                            self.config = Config(self.device)

                            # Check if candidate config still exists
                            diff = self.config.diff()
                            if diff:
                                # Validate with commit_check before retry
                                self.logger.debug("Running commit_check before retry")
                                self.config.commit_check()

                                # Reattempt commit with backoff wrapper
                                retry_msg = "Retrying commit after reconnect"
                                self.logger.info(retry_msg)
                                commit_result = self._with_backoff(
                                    lambda: self.config.commit(
                                        comment=comment, confirm=confirm_timeout
                                    ),
                                    max_retries=1,
                                    operation_name="netconf_commit_retry",
                                )

                                # Success after retry
                                commit_id = None
                                if hasattr(commit_result, "commit_id"):
                                    commit_id = str(commit_result.commit_id)

                                success_msg = (
                                    f"Commit succeeded after retry (ID: {commit_id})"
                                )
                                self.logger.info(success_msg)

                                # Apply finalization strategy
                                commit_info = CommitInfo(
                                    commit_id=commit_id or "unknown",
                                    timestamp=datetime.now().isoformat(),
                                    success=True,
                                )
                                health_result = self._run_health_checks()
                                strategy.execute(
                                    self.config, commit_info, health_result
                                )

                                return ApplicationResult(
                                    success=True,
                                    hostname=hostname,
                                    policies_applied=len(policies),
                                    diff_preview=diff,
                                    commit_id=commit_id,
                                    timestamp=datetime.now().isoformat(),
                                )
                            else:
                                # No diff - commit likely succeeded
                                no_diff_msg = (
                                    "No candidate diff after reconnect - "
                                    "commit likely succeeded, proceeding to "
                                    "finalization"
                                )
                                self.logger.info(no_diff_msg)

                                # Apply finalization strategy
                                commit_info = CommitInfo(
                                    commit_id="recovered",
                                    timestamp=datetime.now().isoformat(),
                                    success=True,
                                )
                                health_result = self._run_health_checks()
                                strategy.execute(
                                    self.config, commit_info, health_result
                                )

                                return ApplicationResult(
                                    success=True,
                                    hostname=hostname,
                                    policies_applied=len(policies),
                                    diff_preview=None,
                                    commit_id="recovered",
                                    timestamp=datetime.now().isoformat(),
                                )

                        except Exception as retry_error:
                            recovery_msg = f"Commit recovery failed: {retry_error}"
                            self.logger.error(recovery_msg)
                            self.config.rollback()

                            # Record failure
                            if commit_retry_guardrail:
                                commit_retry_guardrail.record_failure(
                                    hostname, error_type
                                )

                            if self.autonomous_mode:
                                event_data = {
                                    "error": str(e),
                                    "retry_error": str(retry_error),
                                    "rollback_status": "Rollback after retry failure",
                                }
                                notif = (
                                    self.safety_manager.send_netconf_event_notification
                                )
                                notif("commit", hostname, False, event_data)

                            error_msg = f"Commit failed after retry: {str(retry_error)}"
                            return ApplicationResult(
                                success=False,
                                hostname=hostname,
                                policies_applied=0,
                                error_message=error_msg,
                            )

                except Exception as guardrail_error:
                    self.logger.warning(f"Guardrail check failed: {guardrail_error}")

            # Non-retryable error or recovery failed
            self.config.rollback()

            # FAILURE - send notification if in autonomous mode
            if self.autonomous_mode:
                self.safety_manager.send_netconf_event_notification(
                    "commit",
                    hostname,
                    False,
                    {
                        "error": str(e),
                        "error_type": error_type,
                        "retryable": is_transient,
                        "rollback_status": "Automatic rollback attempted",
                    },
                )

            return ApplicationResult(
                success=False,
                hostname=hostname,
                policies_applied=0,
                error_message=f"Commit failed: {str(e)}",
            )
        except Exception as e:
            self.logger.error(f"Application failed: {e}")
            self.config.rollback()

            # FAILURE - send notification if in autonomous mode
            if self.autonomous_mode:
                self.safety_manager.send_netconf_event_notification(
                    "commit",
                    hostname,
                    False,
                    {
                        "error": str(e),
                        "policies": policies,
                        "rollback_status": "Automatic rollback attempted",
                    },
                )

            return ApplicationResult(
                success=False,
                hostname=hostname,
                policies_applied=0,
                error_message=f"Application failed: {str(e)}",
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
                event_data = {"rollback_id": rollback_id}
                self.safety_manager.send_netconf_event_notification(
                    "rollback", self.device.hostname, True, event_data
                )

            self.logger.info("Rollback completed successfully")
            return True

        except Exception as e:
            self.logger.error(f"Rollback failed: {e}")

            # FAILURE - send notification if in autonomous mode
            if self.autonomous_mode:
                self.safety_manager.send_netconf_event_notification(
                    "rollback", self.device.hostname, False, {"error": str(e)}
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
            error_msg = "Device not connected"
            return HealthResult(success=False, details=[], error=error_msg)

        checks = []
        try:
            # Management interface check
            self.device.rpc.get_interface_information(interface_name="fxp0")
            checks.append("Management interface: OK")

            # BGP neighbor check
            bgp_info = self.device.rpc.get_bgp_neighbor_information()
            xpath_query = './/bgp-peer[peer-state="Established"]'
            established = len(bgp_info.xpath(xpath_query))
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
                        "disconnect", hostname, True, {}
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
            content = policy["content"]

            # Extract just the prefix-list content
            import re

            pattern = r"prefix-list\s+(\S+)\s*{([^}]*)}"
            match = re.search(pattern, content, re.DOTALL)
            if match:
                list_name = match.group(1)
                list_content = match.group(2)

                replace_line = f"    replace: prefix-list {list_name} {{"
                combined.append(replace_line)
                for line in list_content.strip().split("\n"):
                    if line.strip():
                        combined.append(f"        {line.strip()}")
                combined.append("    }")

        combined.append("}")

        return "\n".join(combined)

    def _extract_as_number(self, filename: str) -> int:
        """Extract AS number from filename"""
        import re

        match = re.search(r"AS(\d+)", filename)
        return int(match.group(1)) if match else 0

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensure disconnect"""
        self.disconnect()

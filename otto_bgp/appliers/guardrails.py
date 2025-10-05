"""
Otto BGP Guardrails - Modular Safety Components for Network Automation

Implements modular guardrail components that provide always-active safety
mechanisms for BGP policy application. Each guardrail component can be
enabled/disabled and configured independently.

CRITICAL: These guardrails prevent dangerous network configurations.
They are ALWAYS ACTIVE regardless of system or autonomous mode.
"""

import logging
import signal
import time
import threading
import fcntl
import os
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Critical guardrails that cannot be disabled
CRITICAL_GUARDRAILS = {
    "bogon_prefix",
    "signal_handling",
    "concurrent_operation",
    "commit_retry",
}


@dataclass
class GuardrailResult:
    """Result of a guardrail check"""

    passed: bool
    guardrail_name: str
    risk_level: str  # low, medium, high, critical
    message: str
    details: Dict[str, Any]
    recommended_action: str
    timestamp: datetime


@dataclass
class GuardrailConfig:
    """Configuration for a guardrail component"""

    enabled: bool = True
    strictness_level: str = "medium"  # low, medium, high, strict
    custom_thresholds: Dict[str, Any] = None
    emergency_override: bool = False


class GuardrailComponent(ABC):
    """
    Abstract base class for guardrail components

    Each guardrail implements a specific safety check that can be
    enabled/disabled and configured independently. All guardrails
    are ALWAYS ACTIVE by default regardless of operational mode.
    """

    def __init__(
        self,
        name: str,
        config: Optional[GuardrailConfig] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize guardrail component

        Args:
            name: Guardrail name
            config: Optional configuration
            logger: Optional logger instance
        """
        self.name = name
        self.config = config or GuardrailConfig()
        self.logger = logger or logging.getLogger(f"guardrail.{name}")
        self._last_check_time: Optional[datetime] = None
        self._check_count = 0

    @abstractmethod
    def check(self, context: Dict[str, Any]) -> GuardrailResult:
        """
        Perform guardrail check

        Args:
            context: Context information for the check

        Returns:
            GuardrailResult with check results
        """
        pass

    def is_enabled(self) -> bool:
        """Check if this guardrail is enabled"""
        return self.config.enabled and not self.config.emergency_override

    def update_config(self, config: GuardrailConfig) -> None:
        """Update guardrail configuration"""
        self.config = config
        self.logger.info(f"Updated configuration for {self.name}")


class PrefixCountGuardrail(GuardrailComponent):
    """
    Guardrail for validating BGP prefix counts

    Prevents application of policies that would exceed safe prefix limits
    which could cause router memory exhaustion or performance degradation.
    """

    # Default thresholds based on router capacity
    DEFAULT_THRESHOLDS = {
        "max_prefixes_per_as": 100000,
        "max_total_prefixes": 500000,
        "warning_threshold": 0.8,
        "critical_threshold": 0.95,
    }

    def __init__(
        self,
        config: Optional[GuardrailConfig] = None,
        logger: Optional[logging.Logger] = None,
    ):
        super().__init__("prefix_count", config, logger)

    def check(self, context: Dict[str, Any]) -> GuardrailResult:
        """
        Check prefix counts against safe thresholds

        Args:
            context: Must contain 'policies' key with policy list

        Returns:
            GuardrailResult with validation results
        """
        self._check_count += 1
        self._last_check_time = datetime.now()

        policies = context.get("policies", [])
        thresholds = self._get_thresholds()

        issues = []
        risk_level = "low"

        total_prefixes = 0
        for policy in policies:
            # Count prefixes in this policy
            prefix_count = self._count_prefixes_in_policy(policy)
            total_prefixes += prefix_count

            # Check per-AS limits
            if prefix_count > thresholds["max_prefixes_per_as"]:
                issues.append(
                    f"AS{policy.get('as_number', '?')} has "
                    f"{prefix_count} prefixes "
                    f"(exceeds limit of {thresholds['max_prefixes_per_as']})"
                )
                risk_level = "critical"

        # Check total prefix count
        max_total = thresholds["max_total_prefixes"]
        warning_level = int(max_total * thresholds["warning_threshold"])
        critical_level = int(max_total * thresholds["critical_threshold"])

        if total_prefixes > max_total:
            issues.append(
                f"Total prefix count {total_prefixes} exceeds "
                f"router limit of {max_total}"
            )
            risk_level = "critical"
        elif total_prefixes > critical_level:
            issues.append(
                f"Total prefix count {total_prefixes} exceeds critical "
                f"threshold of {critical_level}"
            )
            risk_level = "high"
        elif total_prefixes > warning_level:
            issues.append(
                f"Total prefix count {total_prefixes} exceeds warning "
                f"threshold of {warning_level}"
            )
            if risk_level == "low":
                risk_level = "medium"

        passed = len(issues) == 0 or (
            risk_level in ["low", "medium"] and self.config.strictness_level == "low"
        )

        message = (
            "Prefix count validation passed"
            if passed
            else f"Prefix count issues: {'; '.join(issues)}"
        )
        recommended_action = self._get_recommended_action(passed, risk_level)

        return GuardrailResult(
            passed=passed,
            guardrail_name=self.name,
            risk_level=risk_level,
            message=message,
            details={
                "total_prefixes": total_prefixes,
                "policy_count": len(policies),
                "thresholds": thresholds,
                "issues": issues,
            },
            recommended_action=recommended_action,
            timestamp=self._last_check_time,
        )

    def _count_prefixes_in_policy(self, policy: Dict[str, Any]) -> int:
        """Count prefixes in a policy"""
        import re

        content = policy.get("content", "")
        prefixes = re.findall(r"(\d+\.\d+\.\d+\.\d+/\d+)", content)
        return len(prefixes)

    def _get_thresholds(self) -> Dict[str, Any]:
        """Get thresholds with custom overrides"""
        thresholds = dict(self.DEFAULT_THRESHOLDS)
        if self.config.custom_thresholds:
            thresholds.update(self.config.custom_thresholds)
        return thresholds

    def _get_recommended_action(self, passed: bool, risk_level: str) -> str:
        """Get recommended action based on results"""
        if passed:
            return "Safe to proceed with policy application"
        elif risk_level == "critical":
            return "DO NOT PROCEED - Reduce prefix count before application"
        elif risk_level == "high":
            return "Review prefix count carefully before proceeding"
        else:
            return "Monitor prefix count during application"


class BogonPrefixGuardrail(GuardrailComponent):
    """
    Guardrail for detecting bogon/private prefixes in BGP policies

    Prevents announcement of private, reserved, or bogon prefixes
    that should never appear in the global BGP table.
    """

    # RFC-defined bogon/private ranges
    BOGON_RANGES = [
        "0.0.0.0/8",  # This network (RFC 1122)
        "10.0.0.0/8",  # Private use (RFC 1918)
        "127.0.0.0/8",  # Loopback (RFC 1122)
        "169.254.0.0/16",  # Link local (RFC 3927)
        "172.16.0.0/12",  # Private use (RFC 1918)
        "192.0.0.0/24",  # IETF Protocol Assignments (RFC 6890)
        "192.0.2.0/24",  # Documentation (RFC 5737)
        "192.168.0.0/16",  # Private use (RFC 1918)
        "198.18.0.0/15",  # Benchmark testing (RFC 2544)
        "198.51.100.0/24",  # Documentation (RFC 5737)
        "203.0.113.0/24",  # Documentation (RFC 5737)
        "224.0.0.0/4",  # Multicast (RFC 3171)
        "240.0.0.0/4",  # Reserved (RFC 1112)
    ]

    def __init__(
        self,
        config: Optional[GuardrailConfig] = None,
        logger: Optional[logging.Logger] = None,
    ):
        super().__init__("bogon_prefix", config, logger)

    def check(self, context: Dict[str, Any]) -> GuardrailResult:
        """
        Check for bogon/private prefixes

        Args:
            context: Must contain 'policies' key with policy list

        Returns:
            GuardrailResult with validation results
        """
        self._check_count += 1
        self._last_check_time = datetime.now()

        policies = context.get("policies", [])
        bogon_detections = []

        for policy in policies:
            as_number = policy.get("as_number", "?")
            content = policy.get("content", "")

            # Extract all prefixes from policy
            import re

            prefixes = re.findall(r"(\d+\.\d+\.\d+\.\d+/\d+)", content)

            for prefix in prefixes:
                if self._is_bogon_prefix(prefix):
                    bogon_detections.append(
                        {
                            "as_number": as_number,
                            "prefix": prefix,
                            "type": self._classify_bogon_type(prefix),
                        }
                    )

        # Determine risk level and pass/fail
        if not bogon_detections:
            risk_level = "low"
            passed = True
            message = "No bogon/private prefixes detected"
        else:
            # High strictness fails on any bogon, medium allows private use
            if self.config.strictness_level in ["high", "strict"]:
                risk_level = "high"
                passed = False
            elif any(d["type"] in ["reserved", "multicast"] for d in bogon_detections):
                risk_level = "critical"
                passed = False
            else:
                risk_level = "medium"
                passed = self.config.strictness_level == "low"

            detected_prefixes = [
                f"AS{d['as_number']}:{d['prefix']} ({d['type']})"
                for d in bogon_detections
            ]
            message = f"Bogon prefixes detected: {'; '.join(detected_prefixes)}"

        recommended_action = self._get_bogon_action(
            passed, risk_level, bogon_detections
        )

        return GuardrailResult(
            passed=passed,
            guardrail_name=self.name,
            risk_level=risk_level,
            message=message,
            details={
                "bogon_count": len(bogon_detections),
                "detections": bogon_detections,
                "policy_count": len(policies),
            },
            recommended_action=recommended_action,
            timestamp=self._last_check_time,
        )

    def _is_bogon_prefix(self, prefix: str) -> bool:
        """Check if prefix is bogon/private"""
        try:
            for bogon_range in self.BOGON_RANGES:
                if self._prefix_in_range(prefix, bogon_range):
                    return True
            return False
        except Exception:
            return True  # Treat parse errors as bogon for safety

    def _prefix_in_range(self, prefix: str, range_prefix: str) -> bool:
        """Simple prefix overlap check"""
        # Simplified implementation - production would use ipaddress module
        try:
            prefix_net = prefix.split("/")[0].split(".")
            range_net = range_prefix.split("/")[0].split(".")
            range_len = int(range_prefix.split("/")[1])

            # Compare octets based on prefix length
            octets_to_check = (range_len + 7) // 8
            for i in range(min(octets_to_check, 4)):
                if int(prefix_net[i]) != int(range_net[i]):
                    return False
            return True
        except Exception:
            return False

    def _classify_bogon_type(self, prefix: str) -> str:
        """Classify type of bogon prefix"""
        prefix_net = prefix.split("/")[0]

        if (
            prefix_net.startswith("10.")
            or prefix_net.startswith("192.168.")
            or prefix_net.startswith("172.")
        ):
            return "private"
        elif prefix_net.startswith("224."):
            return "multicast"
        elif prefix_net.startswith("127."):
            return "loopback"
        elif prefix_net.startswith("169.254."):
            return "link-local"
        else:
            return "reserved"

    def _get_bogon_action(
        self, passed: bool, risk_level: str, detections: List[Dict]
    ) -> str:
        """Get recommended action for bogon detections"""
        if passed:
            return "Safe to proceed - no bogon prefixes detected"
        elif risk_level == "critical":
            return "DO NOT PROCEED - Remove reserved/multicast prefixes"
        elif any(d["type"] == "private" for d in detections):
            return "Review private prefix announcements - may be intentional"
        else:
            return "Review detected prefixes before proceeding"


class ConcurrentOperationGuardrail(GuardrailComponent):
    """
    Guardrail for preventing concurrent Otto BGP operations

    Ensures only one Otto BGP instance can modify router configurations
    at a time to prevent conflicts and ensure consistent state.
    """

    def __init__(
        self,
        config: Optional[GuardrailConfig] = None,
        logger: Optional[logging.Logger] = None,
    ):
        super().__init__("concurrent_operation", config, logger)
        self.lock_file_path = Path("/tmp/otto-bgp.lock")
        self._lock_acquired = False
        # File descriptor for atomic fcntl.flock operations
        self._lock_fd = None
        # Track when lock was acquired for debugging
        self._lock_creation_time = None

    def check(self, context: Dict[str, Any]) -> GuardrailResult:
        """
        Check for concurrent operations

        Args:
            context: Must contain 'operation' key with operation type

        Returns:
            GuardrailResult with concurrency check results
        """
        self._check_count += 1
        self._last_check_time = datetime.now()

        operation = context.get("operation", "unknown")

        # Check for existing lock file
        concurrent_process = self._check_concurrent_process()

        if concurrent_process:
            risk_level = "high"
            passed = False
            message = (
                f"Concurrent Otto BGP operation detected: PID {concurrent_process}"
            )
            details = {
                "concurrent_pid": concurrent_process,
                "lock_file": str(self.lock_file_path),
                "current_operation": operation,
            }
            recommended_action = (
                "Wait for concurrent operation to complete or terminate it if stale"
            )
        else:
            # Try to acquire lock
            lock_acquired = self._acquire_lock()
            if lock_acquired:
                risk_level = "low"
                passed = True
                message = "No concurrent operations detected - lock acquired"
                details = {
                    "lock_acquired": True,
                    "lock_file": str(self.lock_file_path),
                    "current_operation": operation,
                }
                recommended_action = "Safe to proceed with operation"
            else:
                risk_level = "high"
                passed = False
                message = "Failed to acquire operation lock"
                details = {
                    "lock_acquired": False,
                    "lock_file": str(self.lock_file_path),
                    "current_operation": operation,
                }
                recommended_action = "Retry operation or check for stale lock file"

        return GuardrailResult(
            passed=passed,
            guardrail_name=self.name,
            risk_level=risk_level,
            message=message,
            details=details,
            recommended_action=recommended_action,
            timestamp=self._last_check_time,
        )

    def _check_concurrent_process(self) -> Optional[int]:
        """Check for concurrent Otto BGP process"""
        try:
            if not self.lock_file_path.exists():
                return None

            # Read PID from lock file
            pid_str = self.lock_file_path.read_text().strip()
            pid = int(pid_str)

            # Check if process is still running
            import os

            try:
                os.kill(pid, 0)  # Signal 0 just checks if process exists
                return pid
            except OSError:
                # Process doesn't exist - remove stale lock
                self._remove_lock()
                return None

        except Exception as e:
            self.logger.warning(f"Error checking concurrent process: {e}")
            return None

    def _acquire_lock(self) -> bool:
        """
        Acquire operation lock using atomic fcntl.flock for locking.

        Fixes race condition where multiple processes could create lock
        file simultaneously. Uses exclusive non-blocking lock for
        immediate failure if another process holds the lock.

        Performance: Minimal overhead - single fcntl syscall.
        """
        try:
            # Create or open lock file (race is handled by fcntl)
            self._lock_fd = open(self.lock_file_path, "w")

            # Atomic exclusive lock - fails if another process has it
            fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

            # Lock acquired successfully - write PID and metadata
            self._lock_fd.write(f"{os.getpid()}\n")
            self._lock_fd.write(f"acquired_at={time.time()}\n")
            thread_id = threading.current_thread().ident
            self._lock_fd.write(f"thread_id={thread_id}\n")
            self._lock_fd.flush()

            self._lock_acquired = True
            self._lock_creation_time = time.time()

            thread_id = threading.current_thread().ident
            self.logger.debug(
                f"Acquired exclusive lock (PID {os.getpid()}, thread {thread_id})"
            )
            return True

        except (OSError, IOError) as e:
            # Lock is held by another process or system error
            if self._lock_fd:
                try:
                    self._lock_fd.close()
                except Exception:
                    pass
                self._lock_fd = None

            # Check if lock is held (EAGAIN/EACCES) vs other errors
            if e.errno in (11, 13):  # EAGAIN or EACCES
                self.logger.debug(f"Lock held by another process (errno {e.errno})")
                return False
            else:
                self.logger.error(f"Failed to acquire lock due to system error: {e}")
                return False

        except Exception as e:
            # Unexpected error
            if self._lock_fd:
                try:
                    self._lock_fd.close()
                except Exception:
                    pass
                self._lock_fd = None
            self.logger.error(f"Unexpected error acquiring lock: {e}")
            return False

    def _remove_lock(self):
        """
        Remove operation lock and release fcntl lock.

        Properly releases both the fcntl lock and closes file
        descriptor to ensure other processes can acquire the lock.
        """
        try:
            if self._lock_fd is not None:
                # Release fcntl lock explicitly
                # (though closing the fd would do this too)
                try:
                    fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass  # Lock might already be released

                # Close file descriptor
                self._lock_fd.close()
                self._lock_fd = None

                # Log lock release with timing info
                if self._lock_creation_time:
                    lock_duration = time.time() - self._lock_creation_time
                    self.logger.debug(f"Released lock after {lock_duration:.2f}s")

            # Clean up lock file
            if self.lock_file_path.exists():
                self.lock_file_path.unlink()

            self._lock_acquired = False
            self._lock_creation_time = None

        except Exception as e:
            self.logger.warning(f"Failed to remove lock cleanly: {e}")
            # Force cleanup even if there were errors
            self._lock_acquired = False
            self._lock_fd = None
            self._lock_creation_time = None

    def cleanup(self):
        """Cleanup lock on exit"""
        if self._lock_acquired:
            self._remove_lock()


class SignalHandlingGuardrail(GuardrailComponent):
    """
    Guardrail for graceful signal handling and rollback

    Handles system signals (SIGINT, SIGTERM) to perform graceful
    rollback and cleanup before termination.
    """

    def __init__(
        self,
        config: Optional[GuardrailConfig] = None,
        logger: Optional[logging.Logger] = None,
    ):
        super().__init__("signal_handling", config, logger)
        self._rollback_callbacks: List[callable] = []
        self._signal_handlers_installed = False
        # Thread-safe shutdown coordination using threading.Event
        # Fixes race condition where multiple signals could trigger
        # shutdown logic
        self._shutdown_event = threading.Event()
        # Reentrant lock for nested signal handling
        self._shutdown_lock = threading.RLock()

    def install_signal_handlers(self):
        """Install signal handlers for graceful shutdown"""
        if self._signal_handlers_installed:
            return

        # Install handlers for common termination signals
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # SIGUSR1 for graceful configuration reload
        signal.signal(signal.SIGUSR1, self._reload_handler)

        self._signal_handlers_installed = True
        self.logger.info("Signal handlers installed for graceful shutdown")

    def add_rollback_callback(self, callback: callable):
        """Add callback to be executed during rollback"""
        self._rollback_callbacks.append(callback)

    def check(self, context: Dict[str, Any]) -> GuardrailResult:
        """
        Check signal handling readiness

        Args:
            context: Context information

        Returns:
            GuardrailResult with signal handling status
        """
        self._check_count += 1
        self._last_check_time = datetime.now()

        if not self._signal_handlers_installed:
            self.install_signal_handlers()

        passed = self._signal_handlers_installed and not self._shutdown_event.is_set()
        risk_level = "low" if passed else "medium"
        message = "Signal handlers ready" if passed else "Signal handling not ready"

        details = {
            "handlers_installed": self._signal_handlers_installed,
            "rollback_callbacks": len(self._rollback_callbacks),
            "shutdown_initiated": self._shutdown_event.is_set(),
        }

        recommended_action = (
            "Signal handling ready for graceful shutdown"
            if passed
            else "Install signal handlers before proceeding"
        )

        return GuardrailResult(
            passed=passed,
            guardrail_name=self.name,
            risk_level=risk_level,
            message=message,
            details=details,
            recommended_action=recommended_action,
            timestamp=self._last_check_time,
        )

    def _signal_handler(self, signum: int, frame):
        """
        Thread-safe signal handler with atomic shutdown coordination.

        Fixes race condition by using threading.Event for atomic
        shutdown state and RLock for coordinated access during signal
        handling.

        Performance: Minimal overhead - single atomic check + lock
        acquisition only on shutdown.
        """
        import threading
        import time

        signal_name = (
            signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
        )
        thread_id = threading.current_thread().ident

        self.logger.debug(f"Signal {signal_name} received by thread {thread_id}")

        # Thread-safe shutdown coordination with atomic check-and-set
        with self._shutdown_lock:
            if self._shutdown_event.is_set():
                # Shutdown already initiated by another thread/signal
                # Force exit on repeated signals within grace period
                self.logger.critical(
                    f"Force exit on repeated {signal_name} "
                    f"(thread {thread_id}) - "
                    f"shutdown already in progress"
                )
                raise KeyboardInterrupt(f"Force exit on repeated {signal_name}")

            # Atomically set shutdown state - first signal wins
            self._shutdown_event.set()
            shutdown_start_time = time.time()

        self.logger.warning(
            f"Received {signal_name} (thread {thread_id}) - "
            f"initiating graceful shutdown"
        )

        # Start rollback in separate thread to avoid blocking signal handler
        # Use specific thread naming for debugging race conditions
        rollback_thread = threading.Thread(
            target=self._perform_graceful_rollback,
            args=(signum, shutdown_start_time, thread_id),
            name=f"otto-rollback-{signal_name}-{thread_id}",
        )
        rollback_thread.daemon = True
        rollback_thread.start()

        # Give rollback time to complete with progress monitoring
        rollback_thread.join(timeout=30)
        if rollback_thread.is_alive():
            self.logger.error(
                f"Rollback thread still running after 30s timeout "
                f"(signal {signal_name})"
            )

        # Signal cleanup complete - let main handle exit
        self.logger.info(f"Signal handler cleanup complete for {signal_name}")
        raise KeyboardInterrupt(f"Terminated by {signal_name}")

    def _reload_handler(self, signum: int, frame):
        """Handle configuration reload signal"""
        self.logger.info("Received SIGUSR1 - reloading configuration")
        # Implementation would reload configuration
        # For now, just log the event

    def _perform_graceful_rollback(
        self,
        signum: int,
        shutdown_start_time: float = None,
        initiating_thread_id: int = None,
    ):
        """
        Perform graceful rollback with enhanced logging for debugging.

        Args:
            signum: Signal number that initiated shutdown
            shutdown_start_time: When shutdown was initiated
                (for timing analysis)
            initiating_thread_id: Thread ID that received the signal
        """
        import threading
        import time

        current_thread_id = threading.current_thread().ident
        start_time = time.time()

        if shutdown_start_time:
            delay_ms = (start_time - shutdown_start_time) * 1000
            self.logger.info(
                f"Starting graceful rollback (signal {signum}) - "
                f"initiated by thread {initiating_thread_id}, "
                f"executing in thread {current_thread_id}, "
                f"delay: {delay_ms:.2f}ms"
            )
        else:
            self.logger.info(f"Starting graceful rollback (signal {signum})")

        rollback_success = True

        # Execute rollback callbacks
        for i, callback in enumerate(self._rollback_callbacks):
            try:
                callback_num = i + 1
                total = len(self._rollback_callbacks)
                self.logger.info(f"Executing rollback callback {callback_num}/{total}")
                callback()
            except Exception as e:
                self.logger.error(f"Rollback callback {i + 1} failed: {e}")
                rollback_success = False

        if rollback_success:
            self.logger.info("Graceful rollback completed successfully")
        else:
            self.logger.error("Some rollback operations failed")

        return rollback_success


# Global guardrail registry
_GUARDRAIL_REGISTRY: Dict[str, GuardrailComponent] = {}


def register_guardrail(guardrail: GuardrailComponent):
    """Register a guardrail component"""
    _GUARDRAIL_REGISTRY[guardrail.name] = guardrail


def get_guardrail(name: str) -> Optional[GuardrailComponent]:
    """Get guardrail by name with validation"""
    if name not in _GUARDRAIL_REGISTRY:
        available = list(_GUARDRAIL_REGISTRY.keys())
        raise ValueError(f"Unknown guardrail name: {name}. Available: {available}")
    return _GUARDRAIL_REGISTRY[name]


def get_all_guardrails() -> Dict[str, GuardrailComponent]:
    """Get all registered guardrails"""
    return dict(_GUARDRAIL_REGISTRY)


def list_guardrails() -> List[str]:
    """List all available guardrail names"""
    return list(_GUARDRAIL_REGISTRY.keys())


def validate_guardrail_health() -> Dict[str, bool]:
    """Lightweight health checks for guardrail components"""
    health_status = {}

    for name, guardrail in _GUARDRAIL_REGISTRY.items():
        try:
            # Basic health check - ensure guardrail can be instantiated
            health_status[name] = hasattr(guardrail, "check") and callable(
                guardrail.check
            )
        except Exception:
            health_status[name] = False

    return health_status


class CommitRetryGuardrail(GuardrailComponent):
    """
    Circuit breaker for repeated commit failures

    Tracks commit failure history per hostname and blocks operations
    when failure rate exceeds threshold within time window.
    """

    def __init__(
        self,
        config: Optional[GuardrailConfig] = None,
        logger: Optional[logging.Logger] = None,
    ):
        super().__init__("commit_retry", config, logger)
        self._lock = threading.Lock()
        self._failure_history: Dict[str, List[Tuple[float, str]]] = {}
        self._max_failures = 3
        self._window_seconds = 300
        self._persistence_paths = [
            Path("/var/lib/otto-bgp/guardrails/commit_retry.json"),
            Path.home() / ".local/share/otto-bgp/guardrails/commit_retry.json",
        ]
        self._load_state()

    def _load_state(self) -> None:
        """Load failure history from persistent storage"""
        import json

        for path in self._persistence_paths:
            try:
                if path.exists():
                    with open(path, "r") as f:
                        data = json.load(f)
                        # Convert timestamps back to floats
                        self._failure_history = {
                            hostname: [
                                (float(ts), error_type) for ts, error_type in failures
                            ]
                            for hostname, failures in data.items()
                        }
                    self.logger.debug(f"Loaded commit retry state from {path}")
                    return
            except Exception as e:
                self.logger.warning(f"Could not load state from {path}: {e}")

        # No persistent state found, using in-memory only
        self.logger.debug("No persistent state found, using in-memory tracking")

    def _save_state(self) -> None:
        """Save failure history to persistent storage"""
        import json

        # Clean stale entries before saving
        self._clean_stale_entries()

        data = {
            hostname: [(ts, error_type) for ts, error_type in failures]
            for hostname, failures in self._failure_history.items()
        }

        for path in self._persistence_paths:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with open(path, "w") as f:
                    json.dump(data, f, indent=2)
                self.logger.debug(f"Saved commit retry state to {path}")
                return
            except Exception as e:
                self.logger.warning(f"Could not save state to {path}: {e}")

        # If all paths fail, log warning but continue (in-memory only)
        self.logger.warning("Could not persist commit retry state to disk")

    def _clean_stale_entries(self) -> None:
        """Remove entries older than window_seconds"""
        now = time.time()
        cutoff = now - self._window_seconds

        for hostname in list(self._failure_history.keys()):
            self._failure_history[hostname] = [
                (ts, error_type)
                for ts, error_type in self._failure_history[hostname]
                if ts >= cutoff
            ]
            # Remove hostname if no recent failures
            if not self._failure_history[hostname]:
                del self._failure_history[hostname]

    def check(self, context: Dict[str, Any]) -> GuardrailResult:
        """
        Check if commit retry circuit breaker should trigger

        Args:
            context: Must contain 'hostname' key

        Returns:
            GuardrailResult indicating if operation should proceed
        """
        self._check_count += 1
        self._last_check_time = datetime.now()

        hostname = context.get("hostname")
        if not hostname:
            return GuardrailResult(
                passed=True,
                guardrail_name=self.name,
                risk_level="low",
                message="No hostname provided, allowing operation",
                details={},
                recommended_action="Provide hostname in context",
                timestamp=self._last_check_time,
            )

        # Thread-safe access to failure history
        with self._lock:
            self._clean_stale_entries()
            recent_failures = self._failure_history.get(hostname, [])

        failure_count = len(recent_failures)

        if failure_count >= self._max_failures:
            return GuardrailResult(
                passed=False,
                guardrail_name=self.name,
                risk_level="high",
                message=(
                    f"Circuit breaker triggered: {failure_count} failures "
                    f"in {self._window_seconds}s"
                ),
                details={
                    "hostname": hostname,
                    "failure_count": failure_count,
                    "max_failures": self._max_failures,
                    "window_seconds": self._window_seconds,
                    "recent_failures": [
                        {"timestamp": ts, "error_type": error_type}
                        for ts, error_type in recent_failures
                    ],
                },
                recommended_action=(
                    f"Wait {self._window_seconds}s or investigate "
                    f"repeated failures on {hostname}"
                ),
                timestamp=self._last_check_time,
            )

        return GuardrailResult(
            passed=True,
            guardrail_name=self.name,
            risk_level="low",
            message=(f"Commit retry allowed ({failure_count}/{self._max_failures})"),
            details={
                "hostname": hostname,
                "failure_count": failure_count,
                "max_failures": self._max_failures,
            },
            recommended_action="Continue with operation",
            timestamp=self._last_check_time,
        )

    def record_failure(self, hostname: str, error_type: str) -> None:
        """
        Record a commit failure for circuit breaking

        Args:
            hostname: Router hostname
            error_type: Type of error that occurred
        """
        with self._lock:
            if hostname not in self._failure_history:
                self._failure_history[hostname] = []

            self._failure_history[hostname].append((time.time(), error_type))
            self._clean_stale_entries()
            self._save_state()

        self.logger.warning(f"Recorded commit failure for {hostname}: {error_type}")


def initialize_default_guardrails(
    logger: Optional[logging.Logger] = None,
) -> List[GuardrailComponent]:
    """
    Initialize default guardrail components

    Args:
        logger: Optional logger instance

    Returns:
        List of initialized guardrail components
    """
    guardrails = [
        PrefixCountGuardrail(logger=logger),
        BogonPrefixGuardrail(logger=logger),
        ConcurrentOperationGuardrail(logger=logger),
        SignalHandlingGuardrail(logger=logger),
        CommitRetryGuardrail(logger=logger),
    ]

    # Register guardrails
    for guardrail in guardrails:
        register_guardrail(guardrail)

    return guardrails


def validate_guardrail_config(
    enabled_names: List[str], env_overrides: Optional[Dict[str, Any]] = None
) -> List[str]:
    """Validate guardrail configuration: names and parameter ranges"""
    errors = []
    # 1) Critical guardrails present
    for critical in CRITICAL_GUARDRAILS:
        if critical not in enabled_names:
            errors.append(f"Critical guardrail '{critical}' missing from configuration")
    # 2) Names exist in registry
    for name in enabled_names:
        if name not in _GUARDRAIL_REGISTRY:
            errors.append(f"Unknown guardrail '{name}' in configuration")
    # 3) Parameter ranges for prefix_count overrides
    if env_overrides:
        pco = (
            env_overrides.get("prefix_count") or {}
            if isinstance(env_overrides, dict)
            else {}
        )
        th = pco.get("custom_thresholds") or {} if isinstance(pco, dict) else {}
        warn = th.get("warning_threshold")
        crit = th.get("critical_threshold")
        mtotal = th.get("max_total_prefixes")
        per_as = th.get("max_prefixes_per_as")

        def _bad_ratio(v):
            return v is not None and not (
                isinstance(v, (float, int)) and 0.0 < float(v) <= 1.0
            )

        def _bad_posint(v):
            return v is not None and not (isinstance(v, int) and v > 0)

        if _bad_ratio(warn):
            errors.append("warning_threshold must be in (0.0, 1.0]")
        if _bad_ratio(crit):
            errors.append("critical_threshold must be in (0.0, 1.0]")
        if warn is not None and crit is not None and float(warn) >= float(crit):
            errors.append("warning_threshold must be less than critical_threshold")
        if _bad_posint(mtotal):
            errors.append("max_total_prefixes must be a positive integer")
        if _bad_posint(per_as):
            errors.append("max_prefixes_per_as must be a positive integer")
    return errors

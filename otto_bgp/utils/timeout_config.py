"""
Centralized timeout configuration for Otto BGP

This module provides configurable timeout values for all blocking operations
in Otto BGP, preventing indefinite hangs and deadlocks.

Security: All timeout values are validated and have safe defaults
Performance: Optimized timeout values based on operation type
"""

import logging
import os
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional


class TimeoutType(Enum):
    """Types of operations that can timeout"""

    PROCESS_EXECUTION = "process_execution"
    THREAD_POOL = "thread_pool"
    NETWORK_CONNECTION = "network_connection"
    FILE_OPERATION = "file_operation"
    BATCH_PROCESSING = "batch_processing"
    RPKI_VALIDATION = "rpki_validation"
    SSH_CONNECTION = "ssh_connection"
    NETCONF_OPERATION = "netconf_operation"


@dataclass
class TimeoutConfig:
    """Configuration for a specific timeout type"""

    default: float
    min_value: float
    max_value: float
    env_var: str
    description: str

    def get_value(self) -> float:
        """Get the configured timeout value from environment or default"""
        try:
            value = float(os.environ.get(self.env_var, self.default))
            # Validate bounds
            if value < self.min_value:
                logging.warning(
                    f"Timeout {self.env_var}={value} below minimum "
                    f"{self.min_value}, using minimum"
                )
                return self.min_value
            if value > self.max_value:
                logging.warning(
                    f"Timeout {self.env_var}={value} above maximum "
                    f"{self.max_value}, using maximum"
                )
                return self.max_value
            return value
        except (ValueError, TypeError):
            logging.warning(
                f"Invalid timeout value for {self.env_var}, using "
                f"default {self.default}"
            )
            return self.default


class TimeoutManager:
    """Centralized timeout management for Otto BGP"""

    # Timeout configurations for different operation types
    _TIMEOUT_CONFIGS = {
        TimeoutType.PROCESS_EXECUTION: TimeoutConfig(
            default=30.0,
            min_value=5.0,
            max_value=300.0,
            env_var="OTTO_BGP_PROCESS_TIMEOUT",
            description="Timeout for individual process execution",
        ),
        TimeoutType.THREAD_POOL: TimeoutConfig(
            default=60.0,
            min_value=10.0,
            max_value=600.0,
            env_var="OTTO_BGP_THREAD_TIMEOUT",
            description="Timeout for thread pool operations",
        ),
        TimeoutType.NETWORK_CONNECTION: TimeoutConfig(
            default=10.0,
            min_value=2.0,
            max_value=60.0,
            env_var="OTTO_BGP_NETWORK_TIMEOUT",
            description="Timeout for network connections",
        ),
        TimeoutType.FILE_OPERATION: TimeoutConfig(
            default=30.0,
            min_value=5.0,
            max_value=300.0,
            env_var="OTTO_BGP_FILE_TIMEOUT",
            description="Timeout for file operations",
        ),
        TimeoutType.BATCH_PROCESSING: TimeoutConfig(
            default=300.0,
            min_value=60.0,
            max_value=1800.0,
            env_var="OTTO_BGP_BATCH_TIMEOUT",
            description="Timeout for batch processing operations",
        ),
        TimeoutType.RPKI_VALIDATION: TimeoutConfig(
            default=120.0,
            min_value=30.0,
            max_value=600.0,
            env_var="OTTO_BGP_RPKI_TIMEOUT",
            description="Timeout for RPKI validation operations",
        ),
        TimeoutType.SSH_CONNECTION: TimeoutConfig(
            default=15.0,
            min_value=5.0,
            max_value=60.0,
            env_var="OTTO_BGP_SSH_TIMEOUT",
            description="Timeout for SSH connections",
        ),
        TimeoutType.NETCONF_OPERATION: TimeoutConfig(
            default=45.0,
            min_value=10.0,
            max_value=300.0,
            env_var="OTTO_BGP_NETCONF_TIMEOUT",
            description="Timeout for NETCONF operations",
        ),
    }

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._cached_values: Dict[TimeoutType, float] = {}
        self._last_cache_time = 0
        self._cache_ttl = 300  # 5 minutes

    def get_timeout(self, timeout_type: TimeoutType) -> float:
        """
        Get timeout value for specified operation type

        Args:
            timeout_type: Type of operation needing timeout

        Returns:
            Timeout value in seconds
        """
        current_time = time.time()

        # Refresh cache periodically to pick up environment changes
        if current_time - self._last_cache_time > self._cache_ttl:
            self._cached_values.clear()
            self._last_cache_time = current_time

        if timeout_type not in self._cached_values:
            config = self._TIMEOUT_CONFIGS.get(timeout_type)
            if not config:
                msg = f"Unknown timeout type {timeout_type}, using default 30s"
                self.logger.warning(msg)
                return 30.0

            self._cached_values[timeout_type] = config.get_value()
            timeout_val = self._cached_values[timeout_type]
            self.logger.debug(f"Loaded timeout {timeout_type.value}: {timeout_val}s")

        return self._cached_values[timeout_type]

    def get_all_timeouts(self) -> Dict[str, float]:
        """Get all configured timeout values for monitoring/debugging"""
        return {
            timeout_type.value: self.get_timeout(timeout_type)
            for timeout_type in TimeoutType
        }

    def validate_environment(self) -> Dict[str, Any]:
        """
        Validate all timeout environment variables

        Returns:
            Dictionary with validation results
        """
        results = {"valid": True, "warnings": [], "errors": [], "timeouts": {}}

        for timeout_type, config in self._TIMEOUT_CONFIGS.items():
            env_value = os.environ.get(config.env_var)
            actual_value = self.get_timeout(timeout_type)

            results["timeouts"][timeout_type.value] = {
                "env_var": config.env_var,
                "env_value": env_value,
                "actual_value": actual_value,
                "default": config.default,
                "description": config.description,
            }

            if env_value:
                try:
                    parsed_value = float(env_value)
                    out_of_range = (
                        parsed_value < config.min_value
                        or parsed_value > config.max_value
                    )
                    if out_of_range:
                        msg = (
                            f"{config.env_var}={env_value} outside "
                            f"recommended range "
                            f"[{config.min_value}, {config.max_value}]"
                        )
                        results["warnings"].append(msg)
                except (ValueError, TypeError):
                    msg = f"Invalid value for {config.env_var}: {env_value}"
                    results["errors"].append(msg)
                    results["valid"] = False

        return results


class TimeoutContext:
    """Context manager for timeout-aware operations"""

    def __init__(
        self,
        timeout_type: TimeoutType,
        operation_name: str = None,
        custom_timeout: float = None,
    ):
        self.timeout_type = timeout_type
        self.operation_name = operation_name or timeout_type.value
        self.custom_timeout = custom_timeout
        self.manager = TimeoutManager()
        self.logger = logging.getLogger(__name__)
        self.start_time = None
        self.timeout_value = None

    def __enter__(self):
        self.start_time = time.time()
        timeout_val = self.custom_timeout or self.manager.get_timeout(self.timeout_type)
        self.timeout_value = timeout_val
        msg = f"Starting {self.operation_name} with {self.timeout_value}s timeout"
        self.logger.debug(msg)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            elapsed = time.time() - self.start_time
            # Warn if using >80% of timeout
            if elapsed > self.timeout_value * 0.8:
                msg = (
                    f"{self.operation_name} took {elapsed:.2f}s "
                    f"(timeout: {self.timeout_value}s)"
                )
                self.logger.warning(msg)
            else:
                msg = f"{self.operation_name} completed in {elapsed:.2f}s"
                self.logger.debug(msg)

    @property
    def timeout(self) -> float:
        """Get the timeout value for this context"""
        return self.timeout_value or self.manager.get_timeout(self.timeout_type)

    def check_timeout(self) -> bool:
        """Check if operation has timed out"""
        if not self.start_time:
            return False
        elapsed = time.time() - self.start_time
        return elapsed > self.timeout

    def remaining_time(self) -> float:
        """Get remaining time before timeout"""
        if not self.start_time:
            return self.timeout
        elapsed = time.time() - self.start_time
        return max(0, self.timeout - elapsed)


class ExponentialBackoff:
    """Exponential backoff for retry operations with timeout awareness"""

    def __init__(
        self,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_factor: float = 2.0,
        max_retries: int = 5,
    ):
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.max_retries = max_retries
        self.attempt = 0
        self.logger = logging.getLogger(__name__)

    def delay(self, timeout_context: Optional[TimeoutContext] = None) -> bool:
        """
        Calculate and apply backoff delay

        Args:
            timeout_context: Optional timeout context to respect

        Returns:
            True if delay was applied, False if max retries reached or
            timeout exceeded
        """
        if self.attempt >= self.max_retries:
            self.logger.debug(f"Max retries ({self.max_retries}) reached")
            return False

        calculated = self.initial_delay * (self.backoff_factor**self.attempt)
        delay_time = min(calculated, self.max_delay)

        # Check if delay would exceed timeout
        if timeout_context and timeout_context.remaining_time() < delay_time:
            msg = f"Delay {delay_time}s would exceed timeout, aborting retry"
            self.logger.debug(msg)
            return False

        retry_msg = (
            f"Retry {self.attempt + 1}/{self.max_retries} after {delay_time}s delay"
        )
        self.logger.debug(retry_msg)
        time.sleep(delay_time)
        self.attempt += 1
        return True

    def reset(self):
        """Reset backoff state"""
        self.attempt = 0


# Global timeout manager instance
timeout_manager = TimeoutManager()


# Convenience functions for common use cases
def get_timeout(timeout_type: TimeoutType) -> float:
    """Get timeout value for operation type"""
    return timeout_manager.get_timeout(timeout_type)


def timeout_context(
    timeout_type: TimeoutType, operation_name: str = None, custom_timeout: float = None
) -> TimeoutContext:
    """Create timeout context for operation"""
    return TimeoutContext(timeout_type, operation_name, custom_timeout)


def validate_timeouts() -> Dict[str, Any]:
    """Validate all timeout configurations"""
    return timeout_manager.validate_environment()

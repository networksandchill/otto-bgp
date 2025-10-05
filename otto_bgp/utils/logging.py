#!/usr/bin/env python3
"""
Centralized Logging Configuration for Otto BGP

Provides standardized logging setup with:
- Console and file output
- Configurable log levels
- Structured log formatting
- Performance monitoring
- systemd journal integration
"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path
from typing import Dict
import functools
import time

from otto_bgp.utils.config import get_config


class BGPToolkitFormatter(logging.Formatter):
    """Custom formatter for Otto BGP with enhanced structure"""

    # Color codes for console output
    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def __init__(self, use_colors: bool = True, include_module: bool = True):
        """
        Initialize formatter

        Args:
            use_colors: Use ANSI color codes for console output
            include_module: Include module name in log output
        """
        self.use_colors = use_colors and sys.stderr.isatty()
        self.include_module = include_module

        if include_module:
            format_str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        else:
            format_str = "%(asctime)s - %(levelname)s - %(message)s"

        super().__init__(fmt=format_str, datefmt="%Y-%m-%d %H:%M:%S")

    def format(self, record):
        """Format log record with optional colors"""
        # Add performance context if available
        if hasattr(record, "duration"):
            record.message = f"{record.getMessage()} [took {record.duration:.3f}s]"

        # Format base message
        formatted = super().format(record)

        # Add colors for console output
        if self.use_colors and record.levelname in self.COLORS:
            color = self.COLORS[record.levelname]
            formatted = f"{color}{formatted}{self.RESET}"

        return formatted


class BGPToolkitLogger:
    """Enhanced logger for Otto BGP operations"""

    def __init__(self, name: str):
        """Initialize Otto BGP logger"""
        self.logger = logging.getLogger(name)
        self.name = name

    def time_operation(self, operation_name: str = None):
        """
        Decorator to time and log operation duration

        Args:
            operation_name: Custom name for the operation
        """

        def decorator(func):
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                op_name = operation_name or f"{self.name}.{func.__name__}"
                start_time = time.time()

                self.logger.info(f"Starting {op_name}")

                try:
                    result = func(*args, **kwargs)
                    duration = time.time() - start_time

                    # Create log record with duration
                    record = self.logger.makeRecord(
                        name=self.logger.name,
                        level=logging.INFO,
                        fn="",
                        lno=0,
                        msg=f"Completed {op_name}",
                        args=(),
                        exc_info=None,
                    )
                    record.duration = duration

                    self.logger.handle(record)
                    return result

                except Exception as e:
                    duration = time.time() - start_time

                    # Create error record with duration
                    record = self.logger.makeRecord(
                        name=self.logger.name,
                        level=logging.ERROR,
                        fn="",
                        lno=0,
                        msg=f"Failed {op_name}: {e}",
                        args=(),
                        exc_info=sys.exc_info(),
                    )
                    record.duration = duration

                    self.logger.handle(record)
                    raise

            return wrapper

        return decorator

    def log_ssh_connection(self, hostname: str, success: bool, duration: float = None):
        """Log SSH connection attempt"""
        level = logging.INFO if success else logging.WARNING
        status = "connected" if success else "failed"

        message = f"SSH {status} to {hostname}"
        if duration:
            message += f" in {duration:.3f}s"

        self.logger.log(level, message)

    def log_bgpq3_execution(
        self, as_number: int, success: bool, duration: float = None
    ):
        """Log bgpq3 execution result"""
        level = logging.INFO if success else logging.WARNING
        status = "generated" if success else "failed"

        message = f"Policy {status} for AS{as_number}"
        if duration:
            message += f" in {duration:.3f}s"

        self.logger.log(level, message)

    def log_batch_summary(
        self, operation: str, total: int, successful: int, duration: float
    ):
        """Log batch operation summary"""
        failed = total - successful
        success_rate = (successful / total * 100) if total > 0 else 0

        message = f"Batch {operation}: {successful}/{total} successful ({success_rate:.1f}%) in {duration:.2f}s"

        if failed > 0:
            self.logger.warning(message + f" - {failed} failed")
        else:
            self.logger.info(message)

    # Standard logging method delegation
    def debug(self, msg, *args, **kwargs):
        """Log debug message"""
        return self.logger.debug(msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        """Log info message"""
        return self.logger.info(msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        """Log warning message"""
        return self.logger.warning(msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        """Log error message"""
        return self.logger.error(msg, *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        """Log critical message"""
        return self.logger.critical(msg, *args, **kwargs)

    def exception(self, msg, *args, **kwargs):
        """Log exception with traceback"""
        return self.logger.exception(msg, *args, **kwargs)


def setup_logging(
    config_manager=None,
    level: str = None,
    log_to_file: bool = None,
    log_file: str = None,
    console_colors: bool = True,
    include_modules: bool = True,
) -> Dict[str, logging.Handler]:
    """
    Setup centralized logging for Otto BGP

    Args:
        config_manager: Configuration manager instance
        level: Log level override
        log_to_file: Enable file logging override
        log_file: Log file path override
        console_colors: Use colors in console output
        include_modules: Include module names in log format

    Returns:
        Dictionary of configured handlers
    """
    # Get configuration
    if config_manager is None:
        config_manager = get_config()

    logging_config = (
        config_manager.logging if hasattr(config_manager, "logging") else None
    )

    # Use overrides or config values
    if level is None:
        level = logging_config.level if logging_config else "INFO"
    if log_to_file is None:
        log_to_file = logging_config.log_to_file if logging_config else False
    if log_file is None:
        log_file = logging_config.log_file if logging_config else None

    # Convert string level to logging constant
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handlers = {}

    # Console handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(numeric_level)
    console_formatter = BGPToolkitFormatter(
        use_colors=console_colors, include_module=include_modules
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    handlers["console"] = console_handler

    # File handler (if enabled)
    if log_to_file and log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Use rotating file handler to prevent large log files
        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
        )
        file_handler.setLevel(numeric_level)
        file_formatter = BGPToolkitFormatter(
            use_colors=False,  # No colors in file output
            include_module=True,
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
        handlers["file"] = file_handler

    # systemd journal handler (if available and running as service)
    try:
        from systemd import journal

        if journal and _is_running_as_service():
            journal_handler = journal.JournalHandler()
            journal_handler.setLevel(numeric_level)
            journal_formatter = BGPToolkitFormatter(
                use_colors=False, include_module=True
            )
            journal_handler.setFormatter(journal_formatter)
            root_logger.addHandler(journal_handler)
            handlers["journal"] = journal_handler
    except ImportError:
        # systemd not available
        pass

    # Log the logging configuration
    logger = logging.getLogger("otto-bgp.logging")
    logger.info(f"Logging configured: level={level}, handlers={list(handlers.keys())}")

    return handlers


def _is_running_as_service() -> bool:
    """Check if running as a systemd service"""
    try:
        # Check if we have systemd environment variables
        return (
            os.getenv("INVOCATION_ID") is not None
            or os.getenv("JOURNAL_STREAM") is not None
        )
    except (OSError, KeyError):
        return False


def get_logger(name: str) -> BGPToolkitLogger:
    """
    Get enhanced Otto BGP logger

    Args:
        name: Logger name (typically __name__)

    Returns:
        BGPToolkitLogger instance
    """
    return BGPToolkitLogger(name)


def log_system_info():
    """Log system information for debugging"""
    import platform
    import sys
    import os
    from pathlib import Path

    logger = logging.getLogger("bgp-toolkit.system")

    logger.info(f"Otto BGP starting on {platform.system()} {platform.release()}")
    logger.info(f"Python {sys.version}")
    logger.info(f"Working directory: {Path.cwd()}")

    # Log key environment variables (sanitized)
    env_vars = [
        "SSH_USERNAME",
        "BGPQ3_PATH",
        "BGP_TOOLKIT_OUTPUT_DIR",
        "BGP_TOOLKIT_LOG_LEVEL",
    ]

    for var in env_vars:
        value = os.getenv(var)
        if value:
            logger.debug(f"Environment: {var}={value}")
        else:
            logger.debug(f"Environment: {var} not set")


# Performance monitoring context manager
class LoggingTimer:
    """Context manager for timing operations with logging"""

    def __init__(
        self, logger: logging.Logger, operation: str, level: int = logging.INFO
    ):
        self.logger = logger
        self.operation = operation
        self.level = level
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        self.logger.log(self.level, f"Starting {self.operation}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time

        if exc_type is None:
            self.logger.log(
                self.level, f"Completed {self.operation} in {duration:.3f}s"
            )
        else:
            self.logger.error(
                f"Failed {self.operation} after {duration:.3f}s: {exc_val}"
            )

        return False  # Don't suppress exceptions

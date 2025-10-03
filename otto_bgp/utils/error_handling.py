#!/usr/bin/env python3
"""
Otto BGP Error Handling Utilities

Provides standardized error formatting, parameter validation, and user guidance
for consistent error reporting across the Otto BGP application.

Error Format Standards:
- INFO: "✓ {message}"                    # Success messages
- WARNING: "⚠ {message}"                 # Warning messages  
- ERROR: "✗ {message}"                   # Error messages
- FATAL: "✗ Fatal: {message}"            # Critical errors
- USAGE: "Usage: {usage_help}"           # Usage guidance
"""

import os
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Union
from functools import wraps
import subprocess
import time


class ErrorSeverity:
    """Error severity levels for consistent classification"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    FATAL = "fatal"
    USAGE = "usage"


class OttoError(Exception):
    """Base exception class for Otto BGP with standardized error handling"""
    
    def __init__(self, message: str, severity: str = ErrorSeverity.ERROR, 
                 guidance: Optional[str] = None, technical_details: Optional[str] = None):
        self.message = message
        self.severity = severity
        self.guidance = guidance
        self.technical_details = technical_details
        super().__init__(message)


class ValidationError(OttoError):
    """Raised when parameter validation fails"""
    
    def __init__(self, message: str, parameter: str = None, guidance: str = None):
        self.parameter = parameter
        super().__init__(message, ErrorSeverity.ERROR, guidance)


class ConfigurationError(OttoError):
    """Raised when configuration is invalid or missing"""
    pass


class ConnectionError(OttoError):
    """Raised when network connections fail"""
    pass


class ErrorFormatter:
    """Centralized error message formatting with consistent symbols and styles"""
    
    SYMBOLS = {
        ErrorSeverity.INFO: "✓",
        ErrorSeverity.WARNING: "⚠",
        ErrorSeverity.ERROR: "✗",
        ErrorSeverity.FATAL: "✗ Fatal:",
        ErrorSeverity.USAGE: "Usage:"
    }
    
    @classmethod
    def format_message(cls, message: str, severity: str = ErrorSeverity.ERROR, 
                      guidance: Optional[str] = None) -> str:
        """Format a message with the appropriate symbol and structure"""
        symbol = cls.SYMBOLS.get(severity, "•")
        
        if severity == ErrorSeverity.FATAL:
            formatted = f"{symbol} {message}"
        elif severity == ErrorSeverity.USAGE:
            formatted = f"{symbol} {message}"
        else:
            formatted = f"{symbol} {message}"
        
        if guidance:
            formatted += f"\n  Suggestion: {guidance}"
        
        return formatted
    
    @classmethod
    def format_error(cls, error: Union[Exception, OttoError], 
                    hide_technical: bool = True) -> str:
        """Format an exception with appropriate level of detail"""
        if isinstance(error, OttoError):
            formatted = cls.format_message(error.message, error.severity, error.guidance)
            if not hide_technical and error.technical_details:
                formatted += f"\n  Technical: {error.technical_details}"
            return formatted
        
        # Handle standard exceptions
        error_type = type(error).__name__
        message = str(error)
        
        if isinstance(error, FileNotFoundError):
            guidance = "Check that the file path is correct and the file exists"
            return cls.format_message(f"File not found: {message}", 
                                    ErrorSeverity.ERROR, guidance)
        elif isinstance(error, PermissionError):
            guidance = "Check file permissions or run with appropriate privileges"
            return cls.format_message(f"Permission denied: {message}", 
                                    ErrorSeverity.ERROR, guidance)
        elif isinstance(error, subprocess.TimeoutExpired):
            guidance = "Check network connectivity or increase timeout value"
            return cls.format_message(f"Operation timed out: {message}", 
                                    ErrorSeverity.ERROR, guidance)
        elif isinstance(error, ValueError):
            guidance = "Verify input parameters and try again"
            return cls.format_message(f"Invalid input: {message}", 
                                    ErrorSeverity.ERROR, guidance)
        elif isinstance(error, KeyboardInterrupt):
            return cls.format_message("Operation interrupted by user", ErrorSeverity.WARNING)
        else:
            if hide_technical:
                return cls.format_message(f"Unexpected error occurred", ErrorSeverity.ERROR, 
                                        "Check logs for details or run with --verbose")
            else:
                return cls.format_message(f"Unexpected {error_type}: {message}", 
                                        ErrorSeverity.ERROR)


class ParameterValidator:
    """Enhanced parameter validation with range checks and user guidance"""
    
    @staticmethod
    def validate_timeout(timeout: int, parameter_name: str = "timeout") -> int:
        """Validate timeout values with reasonable ranges"""
        if timeout <= 0:
            raise ValidationError(
                f"Timeout must be positive (>0 seconds), got {timeout}",
                parameter_name,
                "Use a positive integer for timeout values (e.g., 30)"
            )
        
        if timeout > 3600:  # 1 hour
            logger = logging.getLogger('otto-bgp.validation')
            logger.warning(f"Very high timeout ({timeout}s) - this may cause long delays")
            # Don't raise error, just warn
        
        return timeout
    
    @staticmethod
    def validate_port(port: int, parameter_name: str = "port") -> int:
        """Validate port numbers"""
        if not (1 <= port <= 65535):
            raise ValidationError(
                f"Port must be between 1-65535, got {port}",
                parameter_name,
                "Use a valid port number (e.g., 22 for SSH, 830 for NETCONF)"
            )
        return port
    
    @staticmethod
    def validate_file_exists(file_path: Union[str, Path], parameter_name: str = "file") -> Path:
        """Validate that a file exists and is readable"""
        path = Path(file_path)
        
        if not path.exists():
            raise ValidationError(
                f"File does not exist: {path}",
                parameter_name,
                f"Check the file path and ensure the file exists"
            )
        
        if not path.is_file():
            raise ValidationError(
                f"Path is not a file: {path}",
                parameter_name,
                "Provide a path to a file, not a directory"
            )
        
        if not os.access(path, os.R_OK):
            raise ValidationError(
                f"Cannot read file: {path}",
                parameter_name,
                "Check file permissions or run with appropriate privileges"
            )
        
        return path
    
    @staticmethod
    def validate_directory_writable(dir_path: Union[str, Path], 
                                  parameter_name: str = "directory") -> Path:
        """Validate that a directory is writable"""
        path = Path(dir_path)
        
        if path.exists() and not path.is_dir():
            raise ValidationError(
                f"Path exists but is not a directory: {path}",
                parameter_name,
                "Provide a path to a directory, not a file"
            )
        
        # Create directory if it doesn't exist
        try:
            path.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            raise ValidationError(
                f"Cannot create directory: {path}",
                parameter_name,
                "Check parent directory permissions or choose a different location"
            )
        
        # Test write access
        test_file = path / f".otto_bgp_write_test_{int(time.time())}"
        try:
            test_file.touch()
            test_file.unlink()
        except (PermissionError, OSError):
            raise ValidationError(
                f"Cannot write to directory: {path}",
                parameter_name,
                "Check directory permissions or run with appropriate privileges"
            )
        
        return path
    
    @staticmethod
    def validate_as_number(as_number: Union[str, int], 
                          parameter_name: str = "as_number") -> int:
        """Validate AS numbers with RFC compliance"""
        try:
            if isinstance(as_number, str):
                # Handle "AS12345" format
                if as_number.upper().startswith('AS'):
                    as_number = as_number[2:]
                as_num = int(as_number)
            else:
                as_num = int(as_number)
        except (ValueError, TypeError):
            raise ValidationError(
                f"AS number must be an integer, got '{as_number}'",
                parameter_name,
                "Use a numeric AS number (e.g., 12345 or AS12345)"
            )
        
        # RFC 4271: AS numbers are 32-bit unsigned integers
        if not (0 <= as_num <= 4294967295):
            raise ValidationError(
                f"AS number out of valid range (0-4294967295), got {as_num}",
                parameter_name,
                "Use a valid 32-bit AS number"
            )
        
        # Warn about reserved ranges but don't block
        if as_num == 0:
            logger = logging.getLogger('otto-bgp.validation')
            logger.warning(f"AS{as_num} is reserved (RFC 7607)")
        elif 64512 <= as_num <= 65534:
            logger = logging.getLogger('otto-bgp.validation')
            logger.info(f"AS{as_num} is in private use range (RFC 6996)")
        elif 65535 <= as_num <= 65551:
            logger = logging.getLogger('otto-bgp.validation')
            logger.warning(f"AS{as_num} is reserved for documentation (RFC 5398)")
        
        return as_num


def handle_errors(logger_name: str = None, hide_technical: bool = True):
    """Decorator for standardized error handling in command functions"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger = logging.getLogger(logger_name or f'otto-bgp.{func.__name__}')
            
            try:
                return func(*args, **kwargs)
            except OttoError as e:
                logger.error(f"{e.severity.title()} in {func.__name__}: {e.message}")
                print(ErrorFormatter.format_error(e, hide_technical))
                
                # Return appropriate exit codes
                if e.severity == ErrorSeverity.FATAL:
                    return 2
                elif e.severity == ErrorSeverity.ERROR:
                    return 1
                else:
                    return 0
                    
            except KeyboardInterrupt:
                logger.info(f"Command {func.__name__} interrupted by user")
                print(ErrorFormatter.format_message("Operation interrupted by user", 
                                                   ErrorSeverity.WARNING))
                return 130
                
            except Exception as e:
                logger.error(f"Unexpected error in {func.__name__}: {e}")
                print(ErrorFormatter.format_error(e, hide_technical))
                return 1
        
        return wrapper
    return decorator


def print_success(message: str):
    """Print a success message with consistent formatting"""
    print(ErrorFormatter.format_message(message, ErrorSeverity.INFO))


def print_warning(message: str, guidance: str = None):
    """Print a warning message with consistent formatting"""
    print(ErrorFormatter.format_message(message, ErrorSeverity.WARNING, guidance))


def print_error(message: str, guidance: str = None):
    """Print an error message with consistent formatting"""
    print(ErrorFormatter.format_message(message, ErrorSeverity.ERROR, guidance))


def print_fatal(message: str, guidance: str = None):
    """Print a fatal error message with consistent formatting"""
    print(ErrorFormatter.format_message(message, ErrorSeverity.FATAL, guidance))


def print_usage(usage_text: str):
    """Print usage information with consistent formatting"""
    print(ErrorFormatter.format_message(usage_text, ErrorSeverity.USAGE))


def validate_common_args(args):
    """Validate common command-line arguments with enhanced validation"""
    validator = ParameterValidator()
    
    # Validate timeout parameters
    if hasattr(args, 'timeout') and args.timeout is not None:
        args.timeout = validator.validate_timeout(args.timeout, "timeout")
    
    if hasattr(args, 'command_timeout') and args.command_timeout is not None:
        args.command_timeout = validator.validate_timeout(args.command_timeout, "command_timeout")
    
    if hasattr(args, 'confirm_timeout') and args.confirm_timeout is not None:
        args.confirm_timeout = validator.validate_timeout(args.confirm_timeout, "confirm_timeout")
    
    # Validate port parameters
    if hasattr(args, 'port') and args.port is not None:
        args.port = validator.validate_port(args.port, "port")
    
    # Validate file parameters
    if hasattr(args, 'input_file') and args.input_file:
        validator.validate_file_exists(args.input_file, "input_file")
    
    if hasattr(args, 'devices_csv') and args.devices_csv:
        validator.validate_file_exists(args.devices_csv, "devices_csv")
    
    # Validate directory parameters
    if hasattr(args, 'output_dir') and args.output_dir:
        validator.validate_directory_writable(args.output_dir, "output_dir")
    
    if hasattr(args, 'policy_dir') and args.policy_dir:
        # Policy dir should exist for apply command, but not necessarily for others
        if hasattr(args, 'command') and args.command == 'apply':
            validator.validate_file_exists(args.policy_dir, "policy_dir")
        else:
            validator.validate_directory_writable(args.policy_dir, "policy_dir")
    
    return args


# Export commonly used functions and classes
__all__ = [
    'ErrorSeverity', 'OttoError', 'ValidationError', 'ConfigurationError', 'ConnectionError',
    'ErrorFormatter', 'ParameterValidator', 'handle_errors',
    'print_success', 'print_warning', 'print_error', 'print_fatal', 'print_usage',
    'validate_common_args'
]
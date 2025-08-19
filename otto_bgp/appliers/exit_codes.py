"""
Otto BGP Exit Codes - Standardized Exit Codes for Monitoring Integration

Provides standardized exit codes for Otto BGP operations to enable proper
monitoring, alerting, and automated response systems.

IMPORTANT: These exit codes are used by monitoring systems and autonomous
operations. Changes to exit codes must be coordinated with operations team.
"""

from enum import IntEnum
from typing import Dict, Optional
import logging


class OttoExitCodes(IntEnum):
    """
    Standardized exit codes for Otto BGP operations
    
    Exit codes follow UNIX conventions:
    - 0: Success
    - 1-2: User/configuration errors  
    - 3-63: Application-specific errors
    - 64-113: System errors (sysexits.h convention)
    - 128+: Signal termination
    """
    
    # Success
    SUCCESS = 0
    
    # User/Configuration Errors (1-2)
    GENERAL_ERROR = 1
    INVALID_USAGE = 2
    
    # Otto BGP Application Errors (3-63)
    SAFETY_CHECK_FAILED = 3
    NETCONF_CONNECTION_FAILED = 4
    POLICY_VALIDATION_FAILED = 5
    BGP_SESSION_IMPACT_CRITICAL = 6
    ROLLBACK_FAILED = 7
    AUTONOMOUS_MODE_BLOCKED = 8
    CONFIGURATION_SYNTAX_ERROR = 9
    POLICY_ADAPTATION_FAILED = 10
    DEVICE_AUTHENTICATION_FAILED = 11
    HOST_KEY_VERIFICATION_FAILED = 12
    COMMAND_INJECTION_DETECTED = 13
    AS_NUMBER_VALIDATION_FAILED = 14
    POLICY_NAME_SANITIZATION_FAILED = 15
    GUARDRAIL_VIOLATION = 16
    BGPQ4_EXECUTION_FAILED = 17
    OUTPUT_DIRECTORY_ERROR = 18
    INPUT_FILE_ERROR = 19
    CONCURRENT_OPERATION_CONFLICT = 20
    VALIDATION_FAILED = 21
    UNEXPECTED_ERROR = 22
    
    # System Errors (64-113, following sysexits.h)
    USAGE_ERROR = 64           # Command line usage error
    DATA_ERROR = 65            # Data format error
    NO_INPUT = 66              # Cannot open input
    NO_USER = 67               # Addressee unknown
    NO_HOST = 68               # Host name unknown
    UNAVAILABLE = 69           # Service unavailable
    SOFTWARE_ERROR = 70        # Internal software error
    OS_ERROR = 71              # System error (e.g., can't fork)
    OS_FILE = 72               # Critical OS file missing
    CANT_CREATE = 73           # Can't create (user) output file
    IO_ERROR = 74              # Input/output error
    TEMP_FAIL = 75             # Temp failure; user is invited to retry
    PROTOCOL_ERROR = 76        # Remote error in protocol
    NO_PERMISSION = 77         # Permission denied
    CONFIG_ERROR = 78          # Configuration error
    
    # Signal Termination (128+)
    SIGNAL_BASE = 128
    SIGINT_TERMINATION = 130   # Ctrl+C (SIGINT = 2, 128+2)
    SIGTERM_TERMINATION = 143  # SIGTERM = 15, 128+15
    SIGKILL_TERMINATION = 137  # SIGKILL = 9, 128+9


class ExitCodeManager:
    """
    Manager for Otto BGP exit codes with logging and monitoring integration
    
    Provides centralized exit code handling with proper logging,
    monitoring integration, and graceful shutdown procedures.
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize exit code manager
        
        Args:
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
        self._exit_context: Dict[str, str] = {}
        
    def set_exit_context(self, **context) -> None:
        """
        Set context information for exit code reporting
        
        Args:
            **context: Key-value pairs for exit context
        """
        self._exit_context.update(context)
        
    def exit_with_code(self, exit_code: OttoExitCodes, message: str = "", 
                      context: Optional[Dict] = None) -> None:
        """
        Exit with specified code and proper logging
        
        Args:
            exit_code: Otto BGP exit code
            message: Optional exit message
            context: Optional additional context
        """
        # Merge context
        full_context = dict(self._exit_context)
        if context:
            full_context.update(context)
            
        # Log exit with appropriate level
        if exit_code == OttoExitCodes.SUCCESS:
            self.logger.info(f"Otto BGP completed successfully: {message}")
        elif exit_code.value <= 20:  # Application errors
            self.logger.error(f"Otto BGP application error ({exit_code.value}): {message}")
        elif exit_code.value >= 64 and exit_code.value <= 78:  # System errors
            self.logger.critical(f"Otto BGP system error ({exit_code.value}): {message}")
        elif exit_code.value >= 128:  # Signal termination
            self.logger.warning(f"Otto BGP terminated by signal ({exit_code.value}): {message}")
        else:
            self.logger.error(f"Otto BGP error ({exit_code.value}): {message}")
            
        # Log context if available
        if full_context:
            self.logger.debug(f"Exit context: {full_context}")
            
        # Send monitoring notification if configured
        self._send_monitoring_notification(exit_code, message, full_context)
        
        # Exit with the specified code
        import sys
        sys.exit(exit_code.value)
        
    def _send_monitoring_notification(self, exit_code: OttoExitCodes, 
                                    message: str, context: Dict) -> None:
        """
        Send exit code notification to monitoring systems
        
        Args:
            exit_code: Exit code
            message: Exit message
            context: Exit context
        """
        try:
            # Check if monitoring integration is enabled
            from otto_bgp.utils.config import get_config_manager
            config_manager = get_config_manager()
            config = config_manager.get_config()
            
            if hasattr(config, 'monitoring') and config.monitoring.enabled:
                # Send monitoring notification
                self._send_monitoring_alert(exit_code, message, context, config.monitoring)
                
        except Exception as e:
            # Best effort - don't let monitoring failure affect exit
            self.logger.debug(f"Failed to send monitoring notification: {e}")
            
    def _send_monitoring_alert(self, exit_code: OttoExitCodes, message: str, 
                              context: Dict, monitoring_config) -> None:
        """
        Send alert to monitoring system
        
        Args:
            exit_code: Exit code
            message: Exit message  
            context: Exit context
            monitoring_config: Monitoring configuration
        """
        # This would integrate with monitoring systems like:
        # - Prometheus metrics
        # - Grafana alerts
        # - Nagios/NRPE
        # - CloudWatch
        # - Custom webhooks
        
        alert_data = {
            'service': 'otto-bgp',
            'exit_code': exit_code.value,
            'exit_name': exit_code.name,
            'message': message,
            'context': context,
            'timestamp': self._get_timestamp(),
            'severity': self._get_severity(exit_code)
        }
        
        self.logger.debug(f"Monitoring alert data: {alert_data}")
        
        # Implementation would depend on monitoring system
        # For now, log the structured data
        if exit_code != OttoExitCodes.SUCCESS:
            self.logger.info(f"MONITORING_ALERT: {alert_data}")
            
    def _get_severity(self, exit_code: OttoExitCodes) -> str:
        """
        Get severity level for monitoring systems
        
        Args:
            exit_code: Exit code
            
        Returns:
            Severity string
        """
        if exit_code == OttoExitCodes.SUCCESS:
            return "info"
        elif exit_code.value <= 2:
            return "warning"
        elif exit_code.value <= 20:
            return "error"
        elif exit_code.value >= 64 and exit_code.value <= 78:
            return "critical"
        elif exit_code.value >= 128:
            return "warning"  # Signal termination is often expected
        else:
            return "error"
            
    def _get_timestamp(self) -> str:
        """Get ISO timestamp for monitoring"""
        from datetime import datetime
        return datetime.now().isoformat()


# Global exit code manager instance
_exit_manager: Optional[ExitCodeManager] = None


def get_exit_manager() -> ExitCodeManager:
    """
    Get global exit code manager instance
    
    Returns:
        Global ExitCodeManager instance
    """
    global _exit_manager
    if _exit_manager is None:
        _exit_manager = ExitCodeManager()
    return _exit_manager


def exit_success(message: str = "Operation completed successfully"):
    """Convenience function for successful exit"""
    get_exit_manager().exit_with_code(OttoExitCodes.SUCCESS, message)


def exit_error(message: str = "General error occurred"):
    """Convenience function for general error exit"""
    get_exit_manager().exit_with_code(OttoExitCodes.GENERAL_ERROR, message)


def exit_safety_failed(message: str = "Safety check failed"):
    """Convenience function for safety check failure"""
    get_exit_manager().exit_with_code(OttoExitCodes.SAFETY_CHECK_FAILED, message)


def exit_netconf_failed(message: str = "NETCONF connection failed"):
    """Convenience function for NETCONF connection failure"""
    get_exit_manager().exit_with_code(OttoExitCodes.NETCONF_CONNECTION_FAILED, message)


def exit_guardrail_violation(message: str = "Guardrail violation detected"):
    """Convenience function for guardrail violations"""
    get_exit_manager().exit_with_code(OttoExitCodes.GUARDRAIL_VIOLATION, message)


def exit_rollback_failed(message: str = "Rollback operation failed"):
    """Convenience function for rollback failures"""
    get_exit_manager().exit_with_code(OttoExitCodes.ROLLBACK_FAILED, message)


# Exit code descriptions for documentation and help text
EXIT_CODE_DESCRIPTIONS = {
    OttoExitCodes.SUCCESS: "Operation completed successfully",
    OttoExitCodes.GENERAL_ERROR: "General error occurred",
    OttoExitCodes.INVALID_USAGE: "Invalid command line usage",
    OttoExitCodes.SAFETY_CHECK_FAILED: "Safety validation failed",
    OttoExitCodes.NETCONF_CONNECTION_FAILED: "NETCONF connection failed",
    OttoExitCodes.POLICY_VALIDATION_FAILED: "Policy validation failed",
    OttoExitCodes.BGP_SESSION_IMPACT_CRITICAL: "Critical BGP session impact detected",
    OttoExitCodes.ROLLBACK_FAILED: "Configuration rollback failed",
    OttoExitCodes.AUTONOMOUS_MODE_BLOCKED: "Autonomous mode operation blocked",
    OttoExitCodes.CONFIGURATION_SYNTAX_ERROR: "Configuration syntax error",
    OttoExitCodes.POLICY_ADAPTATION_FAILED: "Policy adaptation failed",
    OttoExitCodes.DEVICE_AUTHENTICATION_FAILED: "Device authentication failed",
    OttoExitCodes.HOST_KEY_VERIFICATION_FAILED: "SSH host key verification failed",
    OttoExitCodes.COMMAND_INJECTION_DETECTED: "Command injection attempt detected",
    OttoExitCodes.AS_NUMBER_VALIDATION_FAILED: "AS number validation failed",
    OttoExitCodes.POLICY_NAME_SANITIZATION_FAILED: "Policy name sanitization failed",
    OttoExitCodes.GUARDRAIL_VIOLATION: "Safety guardrail violation",
    OttoExitCodes.BGPQ4_EXECUTION_FAILED: "bgpq4 execution failed",
    OttoExitCodes.OUTPUT_DIRECTORY_ERROR: "Output directory error",
    OttoExitCodes.INPUT_FILE_ERROR: "Input file error",
    OttoExitCodes.CONCURRENT_OPERATION_CONFLICT: "Concurrent operation conflict",
    OttoExitCodes.VALIDATION_FAILED: "Input validation failed",
    OttoExitCodes.UNEXPECTED_ERROR: "Unexpected error occurred",
    OttoExitCodes.SIGINT_TERMINATION: "Interrupted by user (Ctrl+C)",
    OttoExitCodes.SIGTERM_TERMINATION: "Terminated by system signal",
    OttoExitCodes.SIGKILL_TERMINATION: "Killed by system signal"
}


def get_exit_code_description(exit_code: OttoExitCodes) -> str:
    """
    Get human-readable description for exit code
    
    Args:
        exit_code: Otto BGP exit code
        
    Returns:
        Description string
    """
    return EXIT_CODE_DESCRIPTIONS.get(exit_code, f"Unknown exit code: {exit_code.value}")
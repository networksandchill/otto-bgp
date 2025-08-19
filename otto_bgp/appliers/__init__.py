"""
Policy Application Module - NETCONF/PyEZ Integration for Otto BGP

This module provides safe, automated application of BGP policies to Juniper routers.
Includes preview, confirmation, rollback, and safety validation mechanisms.

SECURITY WARNING: This module can modify production router configurations.
Always test in lab environment first. Never apply to production without review.
"""

from .juniper_netconf import (
    JuniperPolicyApplier,
    ApplicationResult,
    ConnectionError,
    ApplicationError
)
from .adapter import PolicyAdapter, AdaptationResult
from .safety import UnifiedSafetyManager, SafetyManager, SafetyCheckResult, create_safety_manager
from .guardrails import (
    GuardrailComponent, GuardrailResult, GuardrailConfig,
    PrefixCountGuardrail, BogonPrefixGuardrail, 
    ConcurrentOperationGuardrail, SignalHandlingGuardrail,
    initialize_default_guardrails
)
from .exit_codes import OttoExitCodes, ExitCodeManager, get_exit_manager

__all__ = [
    # Core applier components
    'JuniperPolicyApplier',
    'PolicyAdapter',
    'UnifiedSafetyManager',
    'SafetyManager',  # Backward compatibility
    'create_safety_manager',
    
    # Result classes
    'ApplicationResult',
    'AdaptationResult', 
    'SafetyCheckResult',
    
    # Guardrail system
    'GuardrailComponent',
    'GuardrailResult',
    'GuardrailConfig',
    'PrefixCountGuardrail',
    'BogonPrefixGuardrail',
    'ConcurrentOperationGuardrail', 
    'SignalHandlingGuardrail',
    'initialize_default_guardrails',
    
    # Exit code system
    'OttoExitCodes',
    'ExitCodeManager',
    'get_exit_manager',
    
    # Exception classes
    'ConnectionError',
    'ApplicationError'
]

# Version of the applier module
__version__ = '0.3.2'
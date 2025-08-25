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
from .safety import UnifiedSafetyManager, SafetyCheckResult, create_safety_manager
from .guardrails import (
    GuardrailComponent, GuardrailResult, GuardrailConfig,
    PrefixCountGuardrail, BogonPrefixGuardrail, 
    ConcurrentOperationGuardrail, SignalHandlingGuardrail,
    initialize_default_guardrails
)
from .exit_codes import OttoExitCodes

__all__ = [
    # Core applier components
    'JuniperPolicyApplier',
    'PolicyAdapter',
    'UnifiedSafetyManager',
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
    
    # Exception classes
    'ConnectionError',
    'ApplicationError'
]


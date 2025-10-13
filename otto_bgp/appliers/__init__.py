"""
Policy Application Module - NETCONF/PyEZ Integration for Otto BGP

This module provides safe, automated application of BGP policies to Juniper routers.
Includes preview, confirmation, rollback, and safety validation mechanisms.

SECURITY WARNING: This module can modify production router configurations.
Always test in lab environment first. Never apply to production without review.
"""

from .adapter import AdaptationResult, PolicyAdapter
from .exit_codes import OttoExitCodes
from .guardrails import (
    BogonPrefixGuardrail,
    ConcurrentOperationGuardrail,
    GuardrailComponent,
    GuardrailConfig,
    GuardrailResult,
    PrefixCountGuardrail,
    SignalHandlingGuardrail,
    initialize_default_guardrails,
)
from .juniper_netconf import (
    ApplicationError,
    ApplicationResult,
    ConnectionError,
    JuniperPolicyApplier,
)
from .safety import SafetyCheckResult, UnifiedSafetyManager, create_safety_manager

__all__ = [
    # Core applier components
    "JuniperPolicyApplier",
    "PolicyAdapter",
    "UnifiedSafetyManager",
    "create_safety_manager",
    # Result classes
    "ApplicationResult",
    "AdaptationResult",
    "SafetyCheckResult",
    # Guardrail system
    "GuardrailComponent",
    "GuardrailResult",
    "GuardrailConfig",
    "PrefixCountGuardrail",
    "BogonPrefixGuardrail",
    "ConcurrentOperationGuardrail",
    "SignalHandlingGuardrail",
    "initialize_default_guardrails",
    # Exit code system
    "OttoExitCodes",
    # Exception classes
    "ConnectionError",
    "ApplicationError",
]

"""
Otto BGP Validators Module

Provides comprehensive validation components for BGP policy safety including:
- RPKI/ROA validation with tri-state logic
- VRP (Validated ROA Payloads) processing
- Allowlist exception handling
- Offline validation with cached data

All validators follow Otto BGP's security-first design principles.
"""

from .rpki import RPKIValidator, RPKIGuardrail

__all__ = ["RPKIValidator", "RPKIGuardrail"]

"""
Otto BGP Reports Module - Deployment matrices and analytics

This module generates reports and deployment matrices for router-aware
policy distribution and AS number mappings.
"""

from .matrix import DeploymentMatrix, generate_deployment_matrix

__all__ = ["DeploymentMatrix", "generate_deployment_matrix"]

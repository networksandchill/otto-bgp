"""
Otto BGP Mode Manager - Mode-specific behavior without duplicating guardrails

This module implements mode-specific behavior strategies while maintaining
the unified safety manager architecture. Guardrails are always active;
only finalization strategies differ between modes.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from jnpr.junos.utils.config import Config

logger = logging.getLogger(__name__)


@dataclass
class CommitInfo:
    """Information about a committed configuration"""
    commit_id: str
    timestamp: str
    success: bool
    error_message: Optional[str] = None


@dataclass 
class HealthResult:
    """Health check result data"""
    success: bool
    details: list
    error: Optional[str] = None


class FinalizationStrategy(ABC):
    """Abstract base for mode-specific finalization strategies"""
    
    @abstractmethod
    def execute(self, cu: Config, commit_info: CommitInfo, health_result: HealthResult) -> None:
        """Execute the finalization strategy"""
        pass


class AutoFinalizationStrategy(FinalizationStrategy):
    """Autonomous mode: auto-finalize after health checks"""
    
    def execute(self, cu: Config, commit_info: CommitInfo, health_result: HealthResult) -> None:
        """
        HEALTH CHECK DECISION MATRIX - Autonomous Mode:
        - Health checks PASS → Auto-finalize commit
        - Health checks FAIL → Do NOT finalize; allow rollback window to expire (auto-rollback)
        - Health checks TIMEOUT → Do NOT finalize; allow rollback window to expire (auto-rollback)
        """
        if health_result.success:
            try:
                cu.commit(comment=f"Otto v0.3.2 auto-confirmed: {commit_info.commit_id}")
                logger.info("Changes auto-finalized successfully")
            except Exception as e:
                logger.error(f"Auto-finalization failed: {e}")
                # Don't raise - let rollback timer handle it
        else:
            logger.warning("Health checks failed - allowing rollback timer to handle (auto-rollback)")
            logger.warning(f"Health check failure details: {health_result.error}")
            # Do NOT call cu.rollback() here - let confirmed commit timer handle it


class ManualFinalizationStrategy(FinalizationStrategy):
    """System mode: await manual confirmation"""
    
    def execute(self, cu: Config, commit_info: CommitInfo, health_result: HealthResult) -> None:
        """
        HEALTH CHECK DECISION MATRIX - System Mode:
        - Health checks PASS → NEVER auto-finalize; operator must confirm manually
        - Health checks FAIL → NEVER auto-finalize; operator must decide manually
        - Health checks TIMEOUT → NEVER auto-finalize; operator must decide manually
        """
        # Extract hold window from commit info (default 5 minutes)
        hold_window = 5  # This should come from SafetyConfiguration
        
        logger.info(f"Changes committed with {hold_window}min rollback window")
        logger.info(f"Commit ID: {commit_info.commit_id}")
        logger.info("Manual confirmation required within rollback window")
        
        print(f"\n🔔 MANUAL CONFIRMATION REQUIRED")
        print(f"Commit ID: {commit_info.commit_id}")
        print(f"Rollback window: {hold_window} minutes")
        print(f"To confirm: juniper-cli commit")
        print(f"To rollback: juniper-cli rollback")
        
        if not health_result.success:
            logger.warning(f"Health check issues detected: {health_result.details}")
            logger.info("Manual intervention required - system mode never auto-finalizes")
            print(f"\n⚠️  HEALTH CHECK ISSUES DETECTED:")
            if health_result.error:
                print(f"   Error: {health_result.error}")
            print(f"   Details: {health_result.details}")
            print(f"   Manual review recommended before confirming")


class SchedulingBehavior(ABC):
    """Abstract base for scheduling behavior"""
    
    @abstractmethod
    def should_execute(self) -> bool:
        """Determine if execution should proceed"""
        pass


class ScheduledBehavior(SchedulingBehavior):
    """Autonomous mode: scheduled execution"""
    
    def should_execute(self) -> bool:
        """Always execute when scheduled (systemd timer controls timing)"""
        return True


class InteractiveBehavior(SchedulingBehavior):
    """System mode: interactive execution"""
    
    def should_execute(self) -> bool:
        """Always execute when manually invoked"""
        return True


class ModeManager:
    """Manages mode-specific behavior without duplicating guardrails"""
    
    def __init__(self, mode: str):
        self.mode = mode
        self.is_autonomous = (mode == "autonomous")
        logger.info(f"Mode manager initialized for {mode} mode")
    
    def get_finalization_strategy(self) -> FinalizationStrategy:
        """Return appropriate finalization strategy"""
        if self.is_autonomous:
            return AutoFinalizationStrategy()
        else:
            return ManualFinalizationStrategy()
    
    def get_scheduling_behavior(self) -> SchedulingBehavior:
        """Return appropriate scheduling behavior"""
        if self.is_autonomous:
            return ScheduledBehavior()
        else:
            return InteractiveBehavior()
    
    def should_auto_finalize(self) -> bool:
        """Check if this mode should auto-finalize commits"""
        return self.is_autonomous
    
    def get_mode_description(self) -> str:
        """Get human-readable mode description"""
        if self.is_autonomous:
            return "Autonomous (scheduled, auto-finalize)"
        else:
            return "System (manual, interactive)"
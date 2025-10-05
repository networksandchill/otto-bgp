"""Multi-router coordination orchestrator for staged BGP policy rollouts"""
import logging
from dataclasses import dataclass
from typing import List, Dict, Optional, Any, Protocol
import hashlib

from otto_bgp.database import (
    MultiRouterDAO,
    RolloutRun,
    RolloutStage,
    RolloutTarget
)

logger = logging.getLogger('otto_bgp.pipeline.multi_router_coordinator')


# Strategy Protocol for extensible rollout strategies

class RolloutStrategy(Protocol):
    """Protocol for rollout strategy implementations"""

    def plan_stages(self, devices: List[Dict[str, Any]],
                   policies: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Plan rollout stages based on devices and policies

        Returns list of stage configurations with:
        - name: Stage name
        - sequencing: Stage order (0, 1, 2...)
        - targets: List of target configurations
        """
        ...

    def get_concurrency(self, stage_sequencing: int) -> int:
        """Get concurrency limit for a stage"""
        ...


@dataclass
class CoordinatorConfig:
    """Configuration for multi-router coordinator"""
    default_concurrency: int = 1
    enable_events: bool = True
    auto_progress_stages: bool = True
    require_confirmation: bool = False


class BlastStrategy:
    """Simple blast strategy - all routers in single stage"""

    def __init__(self, concurrency: int = 5):
        self.concurrency = concurrency

    def plan_stages(self, devices: List[Dict[str, Any]],
                   policies: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Create single stage with all devices"""
        targets = []
        for device in devices:
            hostname = device.get('hostname')
            if not hostname:
                continue

            # Calculate policy hash for this device
            device_policy = policies.get(hostname, {})
            policy_hash = self._calculate_policy_hash(device_policy)

            targets.append({
                'hostname': hostname,
                'policy_hash': policy_hash,
                'device_info': device
            })

        return [{
            'name': 'blast_all_routers',
            'sequencing': 0,
            'targets': targets
        }]

    def get_concurrency(self, stage_sequencing: int) -> int:
        """Return configured concurrency"""
        return self.concurrency

    @staticmethod
    def _calculate_policy_hash(policy_data: Any) -> str:
        """Calculate hash of policy content"""
        if isinstance(policy_data, dict):
            content = str(sorted(policy_data.items()))
        else:
            content = str(policy_data)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


class PhasedStrategy:
    """Phased rollout strategy - routers grouped by attribute"""

    def __init__(self, group_by: str = 'region', concurrency: int = 2):
        """
        Args:
            group_by: Device attribute to group by (region, role, etc.)
            concurrency: Concurrent operations per stage
        """
        self.group_by = group_by
        self.concurrency = concurrency

    def plan_stages(self, devices: List[Dict[str, Any]],
                   policies: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Create stages grouped by specified attribute"""
        groups: Dict[str, List[Dict[str, Any]]] = {}

        for device in devices:
            hostname = device.get('hostname')
            if not hostname:
                continue

            # Get grouping key
            group_key = device.get(self.group_by, 'default')

            if group_key not in groups:
                groups[group_key] = []

            # Calculate policy hash
            device_policy = policies.get(hostname, {})
            policy_hash = BlastStrategy._calculate_policy_hash(device_policy)

            groups[group_key].append({
                'hostname': hostname,
                'policy_hash': policy_hash,
                'device_info': device
            })

        # Create stages from groups
        stages = []
        for seq, (group_name, targets) in enumerate(sorted(groups.items())):
            stages.append({
                'name': f'{self.group_by}_{group_name}',
                'sequencing': seq,
                'targets': targets
            })

        return stages

    def get_concurrency(self, stage_sequencing: int) -> int:
        """Return configured concurrency"""
        return self.concurrency


class CanaryStrategy:
    """Canary rollout strategy - single test router, then remaining"""

    def __init__(self, canary_hostname: str, concurrency: int = 5):
        """
        Args:
            canary_hostname: Hostname of canary router
            concurrency: Concurrent operations for main stage
        """
        self.canary_hostname = canary_hostname
        self.concurrency = concurrency

    def plan_stages(self, devices: List[Dict[str, Any]],
                   policies: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Create canary stage + main rollout stage"""
        canary_targets = []
        main_targets = []

        for device in devices:
            hostname = device.get('hostname')
            if not hostname:
                continue

            device_policy = policies.get(hostname, {})
            policy_hash = BlastStrategy._calculate_policy_hash(device_policy)

            target = {
                'hostname': hostname,
                'policy_hash': policy_hash,
                'device_info': device
            }

            if hostname == self.canary_hostname:
                canary_targets.append(target)
            else:
                main_targets.append(target)

        stages = []
        if canary_targets:
            stages.append({
                'name': 'canary',
                'sequencing': 0,
                'targets': canary_targets
            })

        if main_targets:
            stages.append({
                'name': 'main_rollout',
                'sequencing': 1 if canary_targets else 0,
                'targets': main_targets
            })

        return stages

    def get_concurrency(self, stage_sequencing: int) -> int:
        """Canary stage uses concurrency=1, main stage uses configured"""
        return 1 if stage_sequencing == 0 else self.concurrency


@dataclass
class BatchResult:
    """Result of processing a batch of targets"""
    targets: List[RolloutTarget]
    stage_id: str
    stage_name: str
    has_more: bool


class MultiRouterCoordinator:
    """Orchestrates multi-router policy rollouts with staged execution"""

    def __init__(self, dao: Optional[MultiRouterDAO] = None,
                 config: Optional[CoordinatorConfig] = None):
        """Initialize coordinator with DAO and configuration"""
        self.dao = dao or MultiRouterDAO()
        self.config = config or CoordinatorConfig()
        self.current_run: Optional[RolloutRun] = None
        self.current_stages: List[RolloutStage] = []
        self.current_stage_index: int = 0
        logger.debug("MultiRouterCoordinator initialized")

    def hydrate_from_db(self, run_id: str) -> None:
        """Load existing rollout run state from database"""
        try:
            self.current_run = self.dao.get_run(run_id)
            if not self.current_run:
                raise ValueError(f"Rollout run {run_id} not found")

            self.current_stages = self.dao.get_stages(run_id)

            # Find current active stage
            self.current_stage_index = 0
            for idx, stage in enumerate(self.current_stages):
                targets = self.dao.get_targets(stage.stage_id)
                # If any targets are not completed, this is the active stage
                if any(t.state not in ['completed', 'skipped', 'failed'] for t in targets):
                    self.current_stage_index = idx
                    break
                # If all completed/skipped, move to next stage
                if all(t.state in ['completed', 'skipped'] for t in targets):
                    self.current_stage_index = idx + 1

            logger.info(f"Hydrated rollout run {run_id} at stage {self.current_stage_index}")

            if self.config.enable_events:
                self.dao.record_event(
                    run_id=run_id,
                    event_type='run_hydrated',
                    payload={'stage_index': self.current_stage_index}
                )

        except Exception as e:
            logger.error(f"Failed to hydrate run {run_id}: {e}")
            raise

    def plan_run(self, devices: List[Dict[str, Any]],
                policies: Dict[str, Any],
                strategy: Optional[RolloutStrategy] = None,
                initiated_by: Optional[str] = None) -> str:
        """Plan a new rollout run with specified strategy

        Args:
            devices: List of device configurations
            policies: Mapping of hostname -> policy content
            strategy: Rollout strategy (defaults to BlastStrategy)
            initiated_by: Identifier of who initiated the run

        Returns:
            run_id: ID of created rollout run
        """
        if strategy is None:
            strategy = BlastStrategy(concurrency=self.config.default_concurrency)

        try:
            # Create rollout run
            self.current_run = self.dao.create_run(initiated_by=initiated_by)
            run_id = self.current_run.run_id

            logger.info(f"Planning rollout run {run_id}")

            # Plan stages using strategy
            stage_plans = strategy.plan_stages(devices, policies)

            # Create stages and enqueue targets
            self.current_stages = []
            for stage_plan in stage_plans:
                # Create stage
                stage = self.dao.add_stage(
                    run_id=run_id,
                    name=stage_plan['name'],
                    sequencing=stage_plan['sequencing'],
                    guardrail_snapshot={'strategy': strategy.__class__.__name__}
                )
                self.current_stages.append(stage)

                # Enqueue targets for this stage
                if stage_plan['targets']:
                    self.dao.enqueue_targets(
                        stage_id=stage.stage_id,
                        targets=stage_plan['targets']
                    )

            # Update run status to active
            self.dao.update_run_status(run_id, 'active')
            self.current_stage_index = 0

            if self.config.enable_events:
                self.dao.record_event(
                    run_id=run_id,
                    event_type='run_planned',
                    payload={
                        'stages': len(stage_plans),
                        'total_targets': sum(len(s['targets']) for s in stage_plans),
                        'strategy': strategy.__class__.__name__
                    }
                )

            logger.info(f"Planned run {run_id} with {len(stage_plans)} stages")
            return run_id

        except Exception as e:
            logger.error(f"Failed to plan rollout run: {e}")
            if self.current_run:
                self.abort_run(f"Planning failed: {e}")
            raise

    def next_batch(self, concurrency: Optional[int] = None) -> Optional[BatchResult]:
        """Get next batch of targets to process

        Args:
            concurrency: Override default concurrency limit

        Returns:
            BatchResult with targets to process, or None if run complete
        """
        if not self.current_run or not self.current_stages:
            logger.warning("No active rollout run")
            return None

        # Check if we've processed all stages
        if self.current_stage_index >= len(self.current_stages):
            logger.info("All stages completed")
            self.dao.update_run_status(self.current_run.run_id, 'completed')

            if self.config.enable_events:
                self.dao.record_event(
                    run_id=self.current_run.run_id,
                    event_type='run_completed',
                    payload={'total_stages': len(self.current_stages)}
                )
            return None

        current_stage = self.current_stages[self.current_stage_index]
        batch_size = concurrency or self.config.default_concurrency

        # Get pending targets for current stage
        targets = self.dao.get_pending_targets(
            stage_id=current_stage.stage_id,
            limit=batch_size
        )

        if not targets:
            # No more pending targets in this stage, check if stage is complete
            all_targets = self.dao.get_targets(current_stage.stage_id)
            pending_count = len([t for t in all_targets if t.state == 'pending'])
            in_progress_count = len([t for t in all_targets if t.state == 'in_progress'])

            if pending_count == 0 and in_progress_count == 0:
                # Stage complete, move to next
                logger.info(f"Stage {current_stage.name} completed")

                if self.config.enable_events:
                    self.dao.record_event(
                        run_id=self.current_run.run_id,
                        event_type='stage_completed',
                        payload={
                            'stage_id': current_stage.stage_id,
                            'stage_name': current_stage.name
                        }
                    )

                self.current_stage_index += 1

                # Try next stage
                if self.config.auto_progress_stages:
                    return self.next_batch(concurrency)
                else:
                    return None
            else:
                # Targets still in progress
                logger.debug(f"Stage {current_stage.name}: {in_progress_count} in progress")
                return None

        # Mark targets as in_progress
        for target in targets:
            self.dao.update_target_state(target.target_id, 'in_progress')

        logger.debug(f"Retrieved batch of {len(targets)} targets from stage {current_stage.name}")

        return BatchResult(
            targets=targets,
            stage_id=current_stage.stage_id,
            stage_name=current_stage.name,
            has_more=len(targets) == batch_size
        )

    def complete_target(self, target_id: str, result: Optional[Dict[str, Any]] = None) -> None:
        """Mark target as completed successfully"""
        try:
            self.dao.update_target_state(target_id, 'completed', last_error=None)
            logger.debug(f"Target {target_id} completed successfully")

            if self.config.enable_events and self.current_run:
                self.dao.record_event(
                    run_id=self.current_run.run_id,
                    event_type='target_completed',
                    payload={'target_id': target_id, 'result': result}
                )

        except Exception as e:
            logger.error(f"Failed to mark target {target_id} as completed: {e}")
            raise

    def fail_target(self, target_id: str, error: str) -> None:
        """Mark target as failed with error message"""
        try:
            self.dao.update_target_state(target_id, 'failed', last_error=error)
            logger.warning(f"Target {target_id} failed: {error}")

            if self.config.enable_events and self.current_run:
                self.dao.record_event(
                    run_id=self.current_run.run_id,
                    event_type='target_failed',
                    payload={'target_id': target_id, 'error': error}
                )

        except Exception as e:
            logger.error(f"Failed to mark target {target_id} as failed: {e}")
            raise

    def skip_target(self, target_id: str, reason: str) -> None:
        """Mark target as skipped with reason"""
        try:
            self.dao.update_target_state(target_id, 'skipped', last_error=reason)
            logger.info(f"Target {target_id} skipped: {reason}")

            if self.config.enable_events and self.current_run:
                self.dao.record_event(
                    run_id=self.current_run.run_id,
                    event_type='target_skipped',
                    payload={'target_id': target_id, 'reason': reason}
                )

        except Exception as e:
            logger.error(f"Failed to mark target {target_id} as skipped: {e}")
            raise

    def abort_run(self, reason: str) -> None:
        """Abort current rollout run"""
        if not self.current_run:
            logger.warning("No active run to abort")
            return

        try:
            self.dao.update_run_status(self.current_run.run_id, 'aborted')
            logger.warning(f"Aborted run {self.current_run.run_id}: {reason}")

            if self.config.enable_events:
                self.dao.record_event(
                    run_id=self.current_run.run_id,
                    event_type='run_aborted',
                    payload={'reason': reason}
                )

        except Exception as e:
            logger.error(f"Failed to abort run: {e}")
            raise

    def pause_run(self) -> None:
        """Pause current rollout run"""
        if not self.current_run:
            logger.warning("No active run to pause")
            return

        try:
            self.dao.update_run_status(self.current_run.run_id, 'paused')
            logger.info(f"Paused run {self.current_run.run_id}")

            if self.config.enable_events:
                self.dao.record_event(
                    run_id=self.current_run.run_id,
                    event_type='run_paused',
                    payload={'stage_index': self.current_stage_index}
                )

        except Exception as e:
            logger.error(f"Failed to pause run: {e}")
            raise

    def resume_run(self) -> None:
        """Resume paused rollout run"""
        if not self.current_run:
            logger.warning("No run to resume")
            return

        try:
            self.dao.update_run_status(self.current_run.run_id, 'active')
            logger.info(f"Resumed run {self.current_run.run_id}")

            if self.config.enable_events:
                self.dao.record_event(
                    run_id=self.current_run.run_id,
                    event_type='run_resumed',
                    payload={'stage_index': self.current_stage_index}
                )

        except Exception as e:
            logger.error(f"Failed to resume run: {e}")
            raise

    def get_run_status(self) -> Optional[Dict[str, Any]]:
        """Get current run status summary"""
        if not self.current_run:
            return None

        try:
            summary = self.dao.get_run_summary(self.current_run.run_id)
            summary['current_stage_index'] = self.current_stage_index

            if self.current_stage_index < len(self.current_stages):
                summary['current_stage'] = self.current_stages[self.current_stage_index].to_dict()

            return summary

        except Exception as e:
            logger.error(f"Failed to get run status: {e}")
            raise
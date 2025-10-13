"""Multi-router coordination data access layer"""
import json
import logging
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .core import DatabaseManager, get_db
from .exceptions import DatabaseError

logger = logging.getLogger('otto_bgp.database.multi_router')


@dataclass
class RolloutRun:
    """Represents a multi-router rollout run"""
    run_id: str
    created_at: str
    status: str  # planning, active, paused, completed, failed, aborted
    initiated_by: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)


@dataclass
class RolloutStage:
    """Represents a stage in a rollout run"""
    stage_id: str
    run_id: str
    sequencing: int
    name: str
    guardrail_snapshot: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)


@dataclass
class RolloutTarget:
    """Represents a target router in a rollout stage"""
    target_id: str
    stage_id: str
    hostname: str
    policy_hash: Optional[str]
    state: str  # pending, in_progress, completed, failed, skipped
    last_error: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)


@dataclass
class RolloutEvent:
    """Represents an event in a rollout run"""
    event_id: Optional[int]
    run_id: str
    event_type: str
    payload: Optional[str]
    timestamp: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)


class MultiRouterDAO:
    """Data access object for multi-router coordination"""

    def __init__(self, db: Optional[DatabaseManager] = None):
        """Initialize DAO with database manager"""
        self.db = db or get_db()
        logger.debug("MultiRouterDAO initialized")

    # Rollout Run Operations

    def create_run(self, initiated_by: Optional[str] = None,
                   run_id: Optional[str] = None) -> RolloutRun:
        """Create a new rollout run"""
        if run_id is None:
            run_id = f"run_{uuid4().hex[:12]}"

        try:
            with self.db.transaction() as conn:
                conn.execute(
                    '''INSERT INTO rollout_runs (run_id, status, initiated_by)
                       VALUES (?, ?, ?)''',
                    (run_id, 'planning', initiated_by)
                )

                row = conn.execute(
                    '''SELECT run_id, created_at, status, initiated_by
                       FROM rollout_runs WHERE run_id = ?''',
                    (run_id,)
                ).fetchone()

                logger.info(f"Created rollout run: {run_id}")
                return RolloutRun(
                    run_id=row['run_id'],
                    created_at=row['created_at'],
                    status=row['status'],
                    initiated_by=row['initiated_by']
                )
        except Exception as e:
            logger.error(f"Failed to create rollout run: {e}")
            raise DatabaseError(f"Failed to create rollout run: {e}")

    def get_run(self, run_id: str) -> Optional[RolloutRun]:
        """Get a rollout run by ID"""
        try:
            row = self.db.fetchone(
                '''SELECT run_id, created_at, status, initiated_by
                   FROM rollout_runs WHERE run_id = ?''',
                (run_id,)
            )

            if row:
                return RolloutRun(
                    run_id=row['run_id'],
                    created_at=row['created_at'],
                    status=row['status'],
                    initiated_by=row['initiated_by']
                )
            return None
        except Exception as e:
            logger.error(f"Failed to get rollout run {run_id}: {e}")
            raise DatabaseError(f"Failed to get rollout run: {e}")

    def update_run_status(self, run_id: str, status: str) -> None:
        """Update rollout run status"""
        valid_statuses = {'planning', 'active', 'paused', 'completed', 'failed', 'aborted'}
        if status not in valid_statuses:
            raise ValueError(f"Invalid status: {status}")

        try:
            with self.db.transaction() as conn:
                conn.execute(
                    '''UPDATE rollout_runs SET status = ?
                       WHERE run_id = ?''',
                    (status, run_id)
                )
                logger.info(f"Updated run {run_id} status to {status}")
        except Exception as e:
            logger.error(f"Failed to update run status: {e}")
            raise DatabaseError(f"Failed to update run status: {e}")

    def list_runs(self, status: Optional[str] = None,
                  limit: int = 100) -> List[RolloutRun]:
        """List rollout runs, optionally filtered by status"""
        try:
            if status:
                query = '''SELECT run_id, created_at, status, initiated_by
                          FROM rollout_runs WHERE status = ?
                          ORDER BY created_at DESC LIMIT ?'''
                rows = self.db.fetchall(query, (status, limit))
            else:
                query = '''SELECT run_id, created_at, status, initiated_by
                          FROM rollout_runs
                          ORDER BY created_at DESC LIMIT ?'''
                rows = self.db.fetchall(query, (limit,))

            return [
                RolloutRun(
                    run_id=row['run_id'],
                    created_at=row['created_at'],
                    status=row['status'],
                    initiated_by=row['initiated_by']
                )
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Failed to list runs: {e}")
            raise DatabaseError(f"Failed to list runs: {e}")

    # Rollout Stage Operations

    def add_stage(self, run_id: str, name: str, sequencing: int,
                  guardrail_snapshot: Optional[Dict[str, Any]] = None,
                  stage_id: Optional[str] = None) -> RolloutStage:
        """Add a stage to a rollout run"""
        if stage_id is None:
            stage_id = f"stage_{uuid4().hex[:12]}"

        snapshot_json = json.dumps(guardrail_snapshot) if guardrail_snapshot else None

        try:
            with self.db.transaction() as conn:
                conn.execute(
                    '''INSERT INTO rollout_stages
                       (stage_id, run_id, sequencing, name, guardrail_snapshot)
                       VALUES (?, ?, ?, ?, ?)''',
                    (stage_id, run_id, sequencing, name, snapshot_json)
                )

                row = conn.execute(
                    '''SELECT stage_id, run_id, sequencing, name, guardrail_snapshot
                       FROM rollout_stages WHERE stage_id = ?''',
                    (stage_id,)
                ).fetchone()

                logger.info(f"Added stage {stage_id} to run {run_id}")
                return RolloutStage(
                    stage_id=row['stage_id'],
                    run_id=row['run_id'],
                    sequencing=row['sequencing'],
                    name=row['name'],
                    guardrail_snapshot=row['guardrail_snapshot']
                )
        except Exception as e:
            logger.error(f"Failed to add stage: {e}")
            raise DatabaseError(f"Failed to add stage: {e}")

    def get_stages(self, run_id: str) -> List[RolloutStage]:
        """Get all stages for a rollout run, ordered by sequencing"""
        try:
            rows = self.db.fetchall(
                '''SELECT stage_id, run_id, sequencing, name, guardrail_snapshot
                   FROM rollout_stages
                   WHERE run_id = ?
                   ORDER BY sequencing ASC''',
                (run_id,)
            )

            return [
                RolloutStage(
                    stage_id=row['stage_id'],
                    run_id=row['run_id'],
                    sequencing=row['sequencing'],
                    name=row['name'],
                    guardrail_snapshot=row['guardrail_snapshot']
                )
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Failed to get stages for run {run_id}: {e}")
            raise DatabaseError(f"Failed to get stages: {e}")

    # Rollout Target Operations

    def enqueue_targets(
        self,
        stage_id: str,
        targets: List[Dict[str, Any]],
    ) -> List[RolloutTarget]:
        """Enqueue multiple targets for a stage"""
        result_targets = []

        try:
            with self.db.transaction() as conn:
                for target_data in targets:
                    target_id = target_data.get('target_id') or f"target_{uuid4().hex[:12]}"
                    hostname = target_data['hostname']
                    policy_hash = target_data.get('policy_hash')

                    conn.execute(
                        '''INSERT INTO rollout_targets
                           (target_id, stage_id, hostname, policy_hash, state)
                           VALUES (?, ?, ?, ?, ?)''',
                        (target_id, stage_id, hostname, policy_hash, 'pending')
                    )

                    row = conn.execute(
                        '''SELECT target_id, stage_id, hostname, policy_hash,
                                  state, last_error, updated_at
                           FROM rollout_targets WHERE target_id = ?''',
                        (target_id,)
                    ).fetchone()

                    result_targets.append(RolloutTarget(
                        target_id=row['target_id'],
                        stage_id=row['stage_id'],
                        hostname=row['hostname'],
                        policy_hash=row['policy_hash'],
                        state=row['state'],
                        last_error=row['last_error'],
                        updated_at=row['updated_at']
                    ))

                logger.info(f"Enqueued {len(result_targets)} targets for stage {stage_id}")
                return result_targets
        except Exception as e:
            logger.error(f"Failed to enqueue targets: {e}")
            raise DatabaseError(f"Failed to enqueue targets: {e}")

    def update_target_state(
        self,
        target_id: str,
        state: str,
        last_error: Optional[str] = None,
    ) -> None:
        """Update target state and error message"""
        valid_states = {'pending', 'in_progress', 'completed', 'failed', 'skipped'}
        if state not in valid_states:
            raise ValueError(f"Invalid state: {state}")

        try:
            with self.db.transaction() as conn:
                conn.execute(
                    '''UPDATE rollout_targets
                       SET state = ?, last_error = ?, updated_at = CURRENT_TIMESTAMP
                       WHERE target_id = ?''',
                    (state, last_error, target_id)
                )
                logger.debug(f"Updated target {target_id} state to {state}")
        except Exception as e:
            logger.error(f"Failed to update target state: {e}")
            raise DatabaseError(f"Failed to update target state: {e}")

    def get_pending_targets(self, stage_id: str, limit: int = 10) -> List[RolloutTarget]:
        """Get pending targets for a stage"""
        try:
            rows = self.db.fetchall(
                '''SELECT target_id, stage_id, hostname, policy_hash,
                          state, last_error, updated_at
                   FROM rollout_targets
                   WHERE stage_id = ? AND state = 'pending'
                   LIMIT ?''',
                (stage_id, limit)
            )

            return [
                RolloutTarget(
                    target_id=row['target_id'],
                    stage_id=row['stage_id'],
                    hostname=row['hostname'],
                    policy_hash=row['policy_hash'],
                    state=row['state'],
                    last_error=row['last_error'],
                    updated_at=row['updated_at']
                )
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Failed to get pending targets: {e}")
            raise DatabaseError(f"Failed to get pending targets: {e}")

    def get_targets(
        self,
        stage_id: str,
        state: Optional[str] = None,
    ) -> List[RolloutTarget]:
        """Get all targets for a stage, optionally filtered by state"""
        try:
            if state:
                query = '''SELECT target_id, stage_id, hostname, policy_hash,
                                  state, last_error, updated_at
                          FROM rollout_targets
                          WHERE stage_id = ? AND state = ?
                          ORDER BY updated_at ASC'''
                rows = self.db.fetchall(query, (stage_id, state))
            else:
                query = '''SELECT target_id, stage_id, hostname, policy_hash,
                                  state, last_error, updated_at
                          FROM rollout_targets
                          WHERE stage_id = ?
                          ORDER BY updated_at ASC'''
                rows = self.db.fetchall(query, (stage_id,))

            return [
                RolloutTarget(
                    target_id=row['target_id'],
                    stage_id=row['stage_id'],
                    hostname=row['hostname'],
                    policy_hash=row['policy_hash'],
                    state=row['state'],
                    last_error=row['last_error'],
                    updated_at=row['updated_at']
                )
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Failed to get targets: {e}")
            raise DatabaseError(f"Failed to get targets: {e}")

    # Rollout Event Operations

    def record_event(
        self,
        run_id: str,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> RolloutEvent:
        """Record an event for a rollout run"""
        payload_json = json.dumps(payload) if payload else None

        try:
            with self.db.transaction() as conn:
                cursor = conn.execute(
                    '''INSERT INTO rollout_events (run_id, event_type, payload)
                       VALUES (?, ?, ?)''',
                    (run_id, event_type, payload_json)
                )

                event_id = cursor.lastrowid

                row = conn.execute(
                    '''SELECT event_id, run_id, event_type, payload, timestamp
                       FROM rollout_events WHERE event_id = ?''',
                    (event_id,)
                ).fetchone()

                logger.debug(f"Recorded event {event_type} for run {run_id}")
                return RolloutEvent(
                    event_id=row['event_id'],
                    run_id=row['run_id'],
                    event_type=row['event_type'],
                    payload=row['payload'],
                    timestamp=row['timestamp']
                )
        except Exception as e:
            logger.error(f"Failed to record event: {e}")
            raise DatabaseError(f"Failed to record event: {e}")

    def get_events(
        self,
        run_id: str,
        event_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[RolloutEvent]:
        """Get events for a rollout run"""
        try:
            if event_type:
                query = '''SELECT event_id, run_id, event_type, payload, timestamp
                          FROM rollout_events
                          WHERE run_id = ? AND event_type = ?
                          ORDER BY timestamp DESC LIMIT ?'''
                rows = self.db.fetchall(query, (run_id, event_type, limit))
            else:
                query = '''SELECT event_id, run_id, event_type, payload, timestamp
                          FROM rollout_events
                          WHERE run_id = ?
                          ORDER BY timestamp DESC LIMIT ?'''
                rows = self.db.fetchall(query, (run_id, limit))

            return [
                RolloutEvent(
                    event_id=row['event_id'],
                    run_id=row['run_id'],
                    event_type=row['event_type'],
                    payload=row['payload'],
                    timestamp=row['timestamp']
                )
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Failed to get events: {e}")
            raise DatabaseError(f"Failed to get events: {e}")

    # Aggregate Queries

    def get_run_summary(self, run_id: str) -> Dict[str, Any]:
        """Get comprehensive summary of a rollout run"""
        try:
            run = self.get_run(run_id)
            if not run:
                raise DatabaseError(f"Run {run_id} not found")

            stages = self.get_stages(run_id)
            events = self.get_events(run_id, limit=50)

            # Get target statistics for each stage
            stage_stats = []
            for stage in stages:
                targets = self.get_targets(stage.stage_id)
                stats = {
                    'stage_id': stage.stage_id,
                    'stage_name': stage.name,
                    'sequencing': stage.sequencing,
                    'total': len(targets),
                    'pending': len([t for t in targets if t.state == 'pending']),
                    'in_progress': len([t for t in targets if t.state == 'in_progress']),
                    'completed': len([t for t in targets if t.state == 'completed']),
                    'failed': len([t for t in targets if t.state == 'failed']),
                    'skipped': len([t for t in targets if t.state == 'skipped'])
                }
                stage_stats.append(stats)

            return {
                'run': run.to_dict(),
                'stages': [s.to_dict() for s in stages],
                'stage_stats': stage_stats,
                'recent_events': [e.to_dict() for e in events]
            }
        except Exception as e:
            logger.error(f"Failed to get run summary: {e}")
            raise DatabaseError(f"Failed to get run summary: {e}")

"""Pipeline and rollout status API endpoints"""
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException

from otto_bgp.database import DatabaseError, MultiRouterDAO

logger = logging.getLogger('webui.api.pipeline')
router = APIRouter()


@router.get("/rollouts")
async def list_rollouts(status: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
    """List rollout runs

    Args:
        status: Optional status filter (planning, active, paused, completed, failed, aborted)
        limit: Maximum number of runs to return (default 50, max 100)

    Returns:
        Dictionary with list of rollout runs
    """
    try:
        # Validate limit
        if limit > 100:
            limit = 100
        elif limit < 1:
            limit = 1

        dao = MultiRouterDAO()
        runs = dao.list_runs(status=status, limit=limit)

        return {
            "success": True,
            "runs": [run.to_dict() for run in runs],
            "count": len(runs)
        }

    except DatabaseError as e:
        logger.error(f"Database error listing rollouts: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    except Exception as e:
        logger.error(f"Failed to list rollouts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rollouts/{run_id}")
async def get_rollout_status(run_id: str) -> Dict[str, Any]:
    """Get detailed status of a rollout run

    Args:
        run_id: Rollout run identifier

    Returns:
        Comprehensive rollout status including stages, targets, and events
    """
    try:
        dao = MultiRouterDAO()
        summary = dao.get_run_summary(run_id)

        if not summary:
            raise HTTPException(status_code=404, detail=f"Rollout run not found: {run_id}")

        return {
            "success": True,
            "summary": summary
        }

    except DatabaseError as e:
        logger.error(f"Database error getting rollout {run_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    except Exception as e:
        logger.error(f"Failed to get rollout status for {run_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rollouts/{run_id}/stages")
async def get_rollout_stages(run_id: str) -> Dict[str, Any]:
    """Get stages for a rollout run

    Args:
        run_id: Rollout run identifier

    Returns:
        List of rollout stages with statistics
    """
    try:
        dao = MultiRouterDAO()

        # Check if run exists
        run = dao.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"Rollout run not found: {run_id}")

        # Get stages
        stages = dao.get_stages(run_id)

        # Get stats for each stage
        stages_with_stats = []
        for stage in stages:
            targets = dao.get_targets(stage.stage_id)
            stats = {
                'total': len(targets),
                'pending': len([t for t in targets if t.state == 'pending']),
                'in_progress': len([t for t in targets if t.state == 'in_progress']),
                'completed': len([t for t in targets if t.state == 'completed']),
                'failed': len([t for t in targets if t.state == 'failed']),
                'skipped': len([t for t in targets if t.state == 'skipped'])
            }

            stages_with_stats.append({
                **stage.to_dict(),
                'stats': stats
            })

        return {
            "success": True,
            "run_id": run_id,
            "stages": stages_with_stats
        }

    except DatabaseError as e:
        logger.error(f"Database error getting stages for {run_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    except Exception as e:
        logger.error(f"Failed to get stages for {run_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rollouts/{run_id}/stages/{stage_id}/targets")
async def get_stage_targets(run_id: str, stage_id: str,
                           state: Optional[str] = None) -> Dict[str, Any]:
    """Get targets for a rollout stage

    Args:
        run_id: Rollout run identifier
        stage_id: Stage identifier
        state: Optional state filter (pending, in_progress, completed, failed, skipped)

    Returns:
        List of targets with their current state
    """
    try:
        dao = MultiRouterDAO()

        # Verify run and stage exist
        run = dao.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"Rollout run not found: {run_id}")

        stages = dao.get_stages(run_id)
        if not any(s.stage_id == stage_id for s in stages):
            raise HTTPException(status_code=404, detail=f"Stage not found: {stage_id}")

        # Get targets
        targets = dao.get_targets(stage_id, state=state)

        return {
            "success": True,
            "run_id": run_id,
            "stage_id": stage_id,
            "targets": [target.to_dict() for target in targets],
            "count": len(targets)
        }

    except DatabaseError as e:
        logger.error(f"Database error getting targets for {stage_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    except Exception as e:
        logger.error(f"Failed to get targets for {stage_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rollouts/{run_id}/events")
async def get_rollout_events(run_id: str, event_type: Optional[str] = None,
                            limit: int = 100) -> Dict[str, Any]:
    """Get events for a rollout run

    Args:
        run_id: Rollout run identifier
        event_type: Optional event type filter
        limit: Maximum number of events to return (default 100, max 500)

    Returns:
        List of rollout events
    """
    try:
        # Validate limit
        if limit > 500:
            limit = 500
        elif limit < 1:
            limit = 1

        dao = MultiRouterDAO()

        # Check if run exists
        run = dao.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"Rollout run not found: {run_id}")

        # Get events
        events = dao.get_events(run_id, event_type=event_type, limit=limit)

        return {
            "success": True,
            "run_id": run_id,
            "events": [event.to_dict() for event in events],
            "count": len(events)
        }

    except DatabaseError as e:
        logger.error(f"Database error getting events for {run_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    except Exception as e:
        logger.error(f"Failed to get events for {run_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
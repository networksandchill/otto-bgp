"""RPKI Override Management API"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from webui.core.audit import audit_log
from webui.core.security import require_role

# Import database manager
try:
    from otto_bgp.database.rpki_overrides import RPKIOverrideManager
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

router = APIRouter()


class OverrideRequest(BaseModel):
    reason: str


class BulkOperation(BaseModel):
    as_number: int
    action: str  # 'enable' or 'disable'
    reason: Optional[str] = None


@router.get("/overrides")
async def list_overrides(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=500),
    user: dict = Depends(require_role("read_only"))
):
    """List all RPKI overrides with pagination"""
    if not DB_AVAILABLE:
        raise HTTPException(500, "Database not available")

    try:
        mgr = RPKIOverrideManager()
        all_overrides = mgr.get_all_overrides()

        # Pagination
        start = (page - 1) * per_page
        end = start + per_page
        overrides = all_overrides[start:end]

        return {
            "overrides": overrides,
            "total": len(all_overrides),
            "page": page,
            "per_page": per_page
        }
    except Exception as e:
        raise HTTPException(
            500, f"Failed to list overrides: {str(e)}"
        )


@router.post("/overrides/{as_number}/disable")
async def disable_rpki(
    as_number: int,
    request: OverrideRequest,
    user: dict = Depends(require_role("admin")),
    request_obj: Request = None  # FastAPI Request object for IP
):
    """Disable RPKI validation for an AS"""
    if not DB_AVAILABLE:
        raise HTTPException(500, "Database not available")

    # Extract client IP address
    client_ip = None
    if request_obj:
        client_ip = (
            request_obj.client.host if request_obj.client else None
        )

    try:
        mgr = RPKIOverrideManager()
        success = mgr.disable_rpki(
            as_number,
            request.reason,
            user.get("sub", "unknown"),
            ip_address=client_ip
        )

        if success:
            audit_log(
                "rpki_override_disabled",
                user=user.get("sub"),
                resource=f"AS{as_number}",
                details={"reason": request.reason, "ip": client_ip}
            )
            return {
                "success": True,
                "message": f"RPKI disabled for AS{as_number}"
            }
        else:
            raise HTTPException(400, "Failed to disable RPKI")

    except Exception as e:
        raise HTTPException(500, f"Failed to disable RPKI: {str(e)}")


@router.post("/overrides/{as_number}/enable")
async def enable_rpki(
    as_number: int,
    request: OverrideRequest,
    user: dict = Depends(require_role("admin")),
    request_obj: Request = None  # FastAPI Request object for IP
):
    """Enable RPKI validation for an AS"""
    if not DB_AVAILABLE:
        raise HTTPException(500, "Database not available")

    # Extract client IP address
    client_ip = None
    if request_obj:
        client_ip = (
            request_obj.client.host if request_obj.client else None
        )

    try:
        mgr = RPKIOverrideManager()
        success = mgr.enable_rpki(
            as_number,
            request.reason,
            user.get("sub", "unknown"),
            ip_address=client_ip
        )

        if success:
            audit_log(
                "rpki_override_enabled",
                user=user.get("sub"),
                resource=f"AS{as_number}",
                details={"reason": request.reason, "ip": client_ip}
            )
            return {
                "success": True,
                "message": f"RPKI enabled for AS{as_number}"
            }
        else:
            raise HTTPException(400, "Failed to enable RPKI")

    except Exception as e:
        raise HTTPException(500, f"Failed to enable RPKI: {str(e)}")


@router.get("/overrides/history")
async def get_history(
    as_number: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    user: dict = Depends(require_role("read_only"))
):
    """Get override history"""
    if not DB_AVAILABLE:
        raise HTTPException(500, "Database not available")

    try:
        mgr = RPKIOverrideManager()
        history = mgr.get_override_history(as_number, limit)
        return {"history": history, "total": len(history)}
    except Exception as e:
        raise HTTPException(500, f"Failed to get history: {str(e)}")


@router.post("/overrides/bulk")
async def bulk_update(
    operations: List[BulkOperation],
    user: dict = Depends(require_role("admin"))
):
    """Perform bulk override operations"""
    if not DB_AVAILABLE:
        raise HTTPException(500, "Database not available")

    try:
        mgr = RPKIOverrideManager()
        ops_list = [op.dict() for op in operations]
        result = mgr.bulk_update(ops_list, user.get("sub", "unknown"))

        audit_log(
            "rpki_override_bulk_update",
            user=user.get("sub"),
            details={
                "operations": len(operations),
                "result": result
            }
        )

        return result
    except Exception as e:
        raise HTTPException(500, f"Bulk update failed: {str(e)}")

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from webui.core.audit import audit_log
from webui.core.security import require_role
from webui.core.systemd import control_service, systemd_units_status

router = APIRouter()


@router.get("/units")
async def units(names: Optional[str] = Query(""), user: dict = Depends(require_role("read_only"))):
    unit_list = [u.strip() for u in names.split(',') if u.strip()] if names else []
    result = systemd_units_status(unit_list)
    audit_log("view_services", user=user.get("sub"))
    return {"units": result}


@router.post("/control")
async def control(payload: dict, user: dict = Depends(require_role("admin"))):
    action = payload.get('action')
    service = payload.get('service')
    result = control_service(action, service)
    if not result.get('success'):
        raise HTTPException(status_code=400, detail=result.get('message', 'failed'))
    audit_log(f"systemd_{action}", user=user.get("sub"), resource=service)
    return result

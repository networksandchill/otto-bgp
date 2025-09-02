from fastapi import APIRouter, Depends
from webui.core.security import require_role
from webui.core.rpki import get_rpki_status
from webui.core.audit import audit_log

router = APIRouter()


@router.get("/status")
async def rpki_status(user: dict = Depends(require_role("read_only"))):
    data = get_rpki_status()
    audit_log("rpki_status_viewed", user=user.get("sub"))
    return data

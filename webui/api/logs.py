from fastapi import APIRouter, HTTPException, Depends, Query
from webui.core.security import require_role
from webui.core.logs import get_log_files, read_log_file, get_journalctl_logs
from webui.core.audit import audit_log

router = APIRouter()


@router.get("")
async def get_system_logs(
    service: str = "all", level: str = "all", limit: int = 100,
    user: dict = Depends(require_role("read_only"))
):
    lines = get_journalctl_logs(None, limit)
    audit_log("logs_viewed", user=user.get("sub"), resource=f"{service}:{level}")
    return {"lines": lines}


@router.get("/files")
async def list_log_files(user: dict = Depends(require_role("read_only"))):
    files = get_log_files()
    audit_log("list_logs", user=user.get("sub"))
    return {"files": files}


@router.get("/files/{filename}")
async def read_log(
    filename: str,
    lines: int = Query(100, ge=1, le=10000),
    offset: int = Query(0, ge=0),
    user: dict = Depends(require_role("read_only"))
):
    if "/" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    content = read_log_file(filename, lines, offset)
    if "error" in content:
        raise HTTPException(status_code=404, detail=content["error"])
    audit_log("read_log", user=user.get("sub"), resource=filename)
    return content

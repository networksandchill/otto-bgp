from fastapi import APIRouter, Depends, HTTPException, Query

from webui.core.audit import audit_log
from webui.core.logs import get_journalctl_logs, get_log_files, read_log_file
from webui.core.security import require_role

router = APIRouter()


@router.get("")
async def get_system_logs(
    service: str = "all", level: str = "all", limit: int = 100,
    user: dict = Depends(require_role("read_only"))
):
    import json
    from datetime import datetime
    
    # Get journalctl logs for the specified service
    unit = None
    if service != "all":
        unit_map = {
            "otto-bgp": "otto-bgp.service",
            "webui": "otto-bgp-webui-adapter.service",
            "rpki": "otto-bgp-rpki-update.service",
            "rpki-client": "rpki-client.service",
            "rpki-preflight": "otto-bgp-rpki-preflight.service"
        }
        unit = unit_map.get(service)
    
    lines = get_journalctl_logs(unit, limit)
    
    # Parse JSON lines into log entries
    logs = []
    for line in lines:
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            # Map systemd priority to log level
            priority = entry.get("PRIORITY", 6)
            # Convert to int if it's a string
            if isinstance(priority, str):
                try:
                    priority = int(priority)
                except (ValueError, TypeError):
                    priority = 6
            if priority <= 3:
                level_str = "error"
            elif priority == 4:
                level_str = "warning"
            elif priority == 7:
                level_str = "success"
            else:
                level_str = "info"
            
            # Skip if level filter doesn't match
            if level != "all" and level_str != level:
                continue
            
            # Extract service name from unit or syslog identifier
            service_name = "system"
            if entry.get("_SYSTEMD_UNIT"):
                service_name = entry["_SYSTEMD_UNIT"].replace(".service", "").replace("otto-bgp-", "")
                if service_name == "otto-bgp":
                    service_name = "otto-bgp"
                elif service_name == "webui-adapter":
                    service_name = "webui"
            elif entry.get("SYSLOG_IDENTIFIER"):
                service_name = entry["SYSLOG_IDENTIFIER"]
            
            # Create log entry
            logs.append({
                "timestamp": datetime.fromtimestamp(int(entry.get("__REALTIME_TIMESTAMP", 0)) / 1000000).isoformat(),
                "level": level_str,
                "service": service_name,
                "message": entry.get("MESSAGE", "")
            })
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
    
    audit_log("logs_viewed", user=user.get("sub"), resource=f"{service}:{level}")
    return {"logs": logs}


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

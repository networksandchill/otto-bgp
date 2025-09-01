import json
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional
from webui.core.security import require_role
from webui.core.config_io import (
    load_config, save_config, redact_sensitive_fields,
    sync_config_to_otto_env
)
from webui.core.audit import audit_log


class SMTPTest(BaseModel):
    enabled: bool = True
    host: str
    port: int = 587
    use_tls: bool = True
    username: Optional[str] = None
    password: Optional[str] = None
    from_address: str
    to_addresses: list[str]


router = APIRouter()


@router.get("/")
async def get_config(user: dict = Depends(require_role("read_only"))):
    """Get current configuration (redacted)"""
    cfg = load_config()
    cfg = redact_sensitive_fields(cfg)
    audit_log("config_viewed", user=user.get("sub"))
    return cfg


@router.put("/")
async def update_config(request: Request, user: dict = Depends(require_role("admin"))):
    """Update configuration using request body and sync to otto.env"""
    new_config = await request.json()
    # Save UI config.json (non-system keys) and sync system settings to otto.env in core
    ui_keys = ["ssh", "rpki", "bgpq4", "guardrails", "network_security", "smtp"]
    save_config({k: v for k, v in new_config.items() if k not in ui_keys})
    ok = sync_config_to_otto_env(new_config)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to sync to otto.env")
    audit_log("config_updated", user=user.get("sub"))
    return {"success": True}


@router.post("/validate")
async def validate_config(request: Request, user: dict = Depends(require_role("admin"))):
    payload = await request.json()
    config_json = payload.get('config_json', '')
    try:
        obj = json.loads(config_json) if config_json else {}
    except json.JSONDecodeError as e:
        return {"valid": False, "issues": [{"path": "config", "msg": f"Invalid JSON: {e}"}]}
    issues = []
    if 'devices' in obj and not isinstance(obj['devices'], list):
        issues.append({"path": "devices", "msg": "Devices must be a list"})
    return {"valid": len(issues) == 0, "issues": issues}


@router.post("/test-smtp")
async def test_smtp(config: SMTPTest, user: dict = Depends(require_role("admin"))):
    # Only schema validation here; actual send is handled in adapter and will be moved separately
    smtp_dict = config.dict()
    from webui.core.config_io import validate_smtp_config as _v
    issues = _v(smtp_dict)
    if issues:
        raise HTTPException(status_code=400, detail={"issues": issues})
    audit_log("smtp_test_request", user=user.get("sub"))
    return {"validated": True}

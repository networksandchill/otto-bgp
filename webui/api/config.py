import json
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional
from webui.core.security import require_role
from webui.core.config_io import (
    load_config, save_config, redact_sensitive_fields,
    sync_config_to_otto_env, update_core_email_config,
    normalize_email_addresses
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
    
    # Handle SMTP separately - persist to config.json nested structure
    if 'smtp' in new_config:
        smtp_config = new_config.pop('smtp')
        try:
            # Validate email addresses
            if 'to_addresses' in smtp_config:
                normalized = normalize_email_addresses(smtp_config['to_addresses'])
                if smtp_config.get('to_addresses') and not normalized:
                    raise HTTPException(
                        status_code=422,
                        detail={"issues": [{"path": "smtp.to_addresses", "msg": "Invalid email addresses"}]}
                    )
                smtp_config['to_addresses'] = normalized
            
            # Update core email config in config.json
            update_core_email_config(smtp_config)
        except ValueError as e:
            raise HTTPException(
                status_code=422,
                detail={"issues": [{"path": "smtp", "msg": str(e)}]}
            )
    
    # Save other UI config (non-system keys) and sync system settings to otto.env
    ui_keys = ["ssh", "rpki", "bgpq4", "guardrails", "network_security"]
    save_config({k: v for k, v in new_config.items() if k not in ui_keys})
    ok = sync_config_to_otto_env(new_config)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to sync to otto.env")
    
    audit_log("config_updated", user=user.get("sub"))
    
    # Return with restart_required flag for SMTP changes
    return {"success": True, "restart_required": True}


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
    """Validate SMTP configuration schema"""
    smtp_dict = config.dict()
    from webui.core.config_io import validate_smtp_config as _v
    issues = _v(smtp_dict)
    
    # Additional validation for email addresses
    if 'to_addresses' in smtp_dict:
        normalized = normalize_email_addresses(smtp_dict['to_addresses'])
        if not normalized and smtp_dict.get('to_addresses'):
            issues.append("Invalid or empty email addresses")
    
    if issues:
        raise HTTPException(status_code=400, detail={"issues": issues})
    
    audit_log("smtp_test_request", user=user.get("sub"))
    return {"validated": True}

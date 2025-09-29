import json
import tempfile
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Request, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from webui.core.security import require_role
from webui.core.config_io import (
    load_config, save_config, redact_sensitive_fields,
    sync_config_to_otto_env, update_core_email_config,
    normalize_email_addresses, load_config_json_only
)
from webui.core.audit import audit_log
from webui.core.fileops import create_timestamped_backup, restore_backup
from webui.settings import CONFIG_PATH, CONFIG_DIR, DATA_DIR


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
async def update_config(request: Request,
                        user: dict = Depends(require_role("admin"))):
    """Update configuration using request body and sync to otto.env"""
    new_config = await request.json()
    # Create backup before any changes
    backup_root = DATA_DIR / 'backups'
    files_to_backup = [
        CONFIG_PATH,
        CONFIG_DIR / 'devices.csv',
        CONFIG_DIR / 'otto.env'
    ]
    backup_dir, backed_up = create_timestamped_backup(
        files_to_backup, backup_root
    )
    audit_log('prechange_backup_created',
              user=user.get('sub'), resource=str(backup_dir))
    # Validate guardrails configuration
    if 'guardrails' in new_config:
        try:
            from otto_bgp.appliers.guardrails import (
                validate_guardrail_config, initialize_default_guardrails
            )

            # Initialize guardrail registry if needed
            try:
                initialize_default_guardrails()
            except Exception:
                pass  # Registry may already be initialized

            gr = new_config['guardrails']
            enabled = gr.get('enabled_guardrails', [])

            # Build env_overrides dict for validation
            env_overrides = {}
            if 'prefix_count_thresholds' in gr or 'strictness' in gr:
                prefix_config = {}
                if 'prefix_count_thresholds' in gr:
                    prefix_config['custom_thresholds'] = gr['prefix_count_thresholds']
                if 'strictness' in gr and 'prefix_count' in gr['strictness']:
                    prefix_config['strictness_level'] = gr['strictness']['prefix_count']
                if prefix_config:
                    env_overrides['prefix_count'] = prefix_config

            # Validate guardrail configuration
            validation_errors = validate_guardrail_config(enabled, env_overrides)
            if validation_errors:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "issues": [
                            {"path": "guardrails", "msg": err}
                            for err in validation_errors
                        ]
                    }
                )

            # Check RPKI conditional enforcement
            # If RPKI is enabled, rpki_validation must be in enabled list
            if 'rpki' in new_config and new_config.get('rpki', {}).get('enabled'):
                if 'rpki_validation' not in enabled:
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "issues": [{
                                "path": "guardrails.enabled_guardrails",
                                "msg": "rpki_validation guardrail is mandatory when RPKI is enabled"
                            }]
                        }
                    )

            # Validate strictness enum values
            if 'strictness' in gr:
                valid_strictness = {'low', 'medium', 'high', 'strict'}
                for guardrail_name, strictness_value in gr['strictness'].items():
                    if strictness_value and strictness_value not in valid_strictness:
                        raise HTTPException(
                            status_code=400,
                            detail={
                                "issues": [{
                                    "path": f"guardrails.strictness.{guardrail_name}",
                                    "msg": f"Invalid strictness '{strictness_value}'. Must be one of: {', '.join(sorted(valid_strictness))}"
                                }]
                            }
                        )

        except HTTPException:
            raise  # Re-raise HTTP exceptions as-is
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail={"issues": [{"path": "guardrails", "msg": f"Validation error: {str(e)}"}]}
            )

    # Handle SMTP separately - persist to config.json nested structure
    if 'smtp' in new_config:
        smtp_config = new_config.pop('smtp')
        try:
            # Validate email addresses
            if 'to_addresses' in smtp_config:
                normalized = normalize_email_addresses(
                    smtp_config['to_addresses']
                )
                if smtp_config.get('to_addresses') and not normalized:
                    raise HTTPException(
                        status_code=422,
                        detail={"issues": [
                            {"path": "smtp.to_addresses",
                             "msg": "Invalid email addresses"}
                        ]}
                    )
                smtp_config['to_addresses'] = normalized
            # Update core email config in config.json
            update_core_email_config(smtp_config)
        except ValueError as e:
            raise HTTPException(
                status_code=422,
                detail={"issues": [{"path": "smtp", "msg": str(e)}]}
            )

    # Save UI config (non-system keys) and sync to otto.env
    ui_keys = [
        "ssh", "rpki", "bgpq4", "guardrails", "network_security"
    ]
    save_config(
        {k: v for k, v in new_config.items() if k not in ui_keys}
    )
    ok = sync_config_to_otto_env(new_config)
    if not ok:
        raise HTTPException(
            status_code=500, detail="Failed to sync to otto.env"
        )
    audit_log("config_updated", user=user.get("sub"))

    # Return with restart_required flag for SMTP changes
    return {"success": True, "restart_required": True}


@router.post("/validate")
async def validate_config(request: Request,
                          user: dict = Depends(require_role("admin"))):
    payload = await request.json()
    config_json = payload.get('config_json', '')
    try:
        obj = json.loads(config_json) if config_json else {}
    except json.JSONDecodeError as e:
        return {
            "valid": False,
            "issues": [{"path": "config", "msg": f"Invalid JSON: {e}"}]
        }
    issues = []
    if 'devices' in obj and not isinstance(obj['devices'], list):
        issues.append({"path": "devices", "msg": "Devices must be a list"})
    return {"valid": len(issues) == 0, "issues": issues}


@router.post("/test-smtp")
async def test_smtp(config: SMTPTest,
                    user: dict = Depends(require_role("admin"))):
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


# Global rate limit storage for test emails
RATE_LIMITS = {}


@router.post("/send-test-email")
async def send_test_email(request: Request,
                          user: dict = Depends(require_role("admin"))):
    """Send a test email with rate limiting"""
    import smtplib
    import ssl
    from time import time
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    payload = await request.json() if request else {}

    # Load current config and merge with any override
    cfg = (load_config_json_only()
           .get('autonomous_mode', {})
           .get('notifications', {})
           .get('email', {}))
    if payload:
        # Map UI fields to backend fields
        if 'host' in payload:
            cfg['smtp_server'] = payload['host']
        if 'port' in payload:
            cfg['smtp_port'] = payload['port']
        if 'username' in payload:
            cfg['smtp_username'] = payload['username']
        if 'password' in payload and payload['password'] != '*****':
            cfg['smtp_password'] = payload['password']
        if 'use_tls' in payload:
            cfg['smtp_use_tls'] = payload['use_tls']
        if 'from_address' in payload:
            cfg['from_address'] = payload['from_address']
        if 'to_addresses' in payload:
            cfg['to_addresses'] = payload['to_addresses']
        if 'subject_prefix' in payload:
            cfg['subject_prefix'] = payload['subject_prefix']

    # Rate limiting - 1 email per minute per user
    key = f"test_email:{user.get('sub')}"
    now = time()
    last = RATE_LIMITS.get(key, 0)
    if now - last < 60:
        raise HTTPException(
            status_code=429,
            detail=(
                'Too many test emails. Please wait a minute '
                'before trying again.'
            )
        )
    # Validate configuration
    if not cfg.get('smtp_server'):
        raise HTTPException(
            status_code=400, detail='SMTP server not configured'
        )
    if not cfg.get('to_addresses'):
        raise HTTPException(
            status_code=400, detail='No recipient addresses configured'
        )
    if not cfg.get('from_address'):
        raise HTTPException(
            status_code=400, detail='No from address configured'
        )
    # Optional recipient allowlist (for production safety)
    allowed = set([a.lower() for a in cfg.get('test_email_allowlist', [])])
    to_addresses = cfg['to_addresses']
    if allowed:
        to_addresses = [t for t in to_addresses if t.lower() in allowed]
        if not to_addresses:
            raise HTTPException(
                status_code=400,
                detail='Recipients not in test email allowlist'
            )
    try:
        # Create message
        msg = MIMEMultipart()
        msg['From'] = cfg['from_address']
        msg['To'] = ', '.join(to_addresses)

        # Add TEST marker to subject
        subject_prefix = cfg.get('subject_prefix', '[Otto BGP]')
        msg['Subject'] = (
            f"{subject_prefix} TEST Email - "
            "Configuration Verification"
        )
        # Email body with TEST marker
        body = """This is a TEST email from Otto BGP WebUI.

This email confirms that your SMTP configuration is working correctly.

Configuration Details:
- SMTP Server: {}:{}
- TLS: {}
- From: {}
- To: {}

This is a TEST message only. No action is required.

--
Otto BGP WebUI
""".format(
            cfg.get('smtp_server'),
            cfg.get('smtp_port', 587),
            'Enabled' if cfg.get('smtp_use_tls', True) else 'Disabled',
            cfg['from_address'],
            ', '.join(to_addresses)
        )

        msg.attach(MIMEText(body, 'plain'))
        # Send email
        context = ssl.create_default_context()

        with smtplib.SMTP(
            cfg['smtp_server'],
            cfg.get('smtp_port', 587),
            timeout=10
        ) as server:
            if cfg.get('smtp_use_tls', True):
                server.starttls(context=context)

            if cfg.get('smtp_username'):
                server.login(
                    cfg['smtp_username'],
                    cfg.get('smtp_password', '')
                )

            server.send_message(msg)
        # Update rate limit
        RATE_LIMITS[key] = now

        # Audit log
        audit_log(
            'smtp_test_email_sent',
            user=user.get('sub'),
            resource=','.join(to_addresses)
        )

        return {
            "success": True,
            "message": f"Test email sent to {', '.join(to_addresses)}"
        }
    except smtplib.SMTPAuthenticationError:
        raise HTTPException(
            status_code=400,
            detail='SMTP authentication failed. Check username and password.'
        )
    except smtplib.SMTPException as e:
        raise HTTPException(
            status_code=400,
            detail=f'SMTP error: {str(e)}'
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f'Failed to send test email: {str(e)}'
        )


@router.get("/export")
async def export_config(user: dict = Depends(require_role("read_only"))):
    """Export configuration as JSON file"""
    try:
        # Load and redact sensitive fields
        config = load_config()
        redacted = redact_sensitive_fields(config)

        # Create temporary file with exported config
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.json',
            delete=False
        ) as tmp:
            json.dump(redacted, tmp, indent=2)
            tmp_path = tmp.name

        # Create filename with timestamp
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        filename = f"otto_bgp_config_{timestamp}.json"

        audit_log(
            'config_exported',
            user=user.get('sub'),
            resource=filename
        )

        return FileResponse(
            tmp_path,
            media_type='application/json',
            filename=filename,
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"'
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f'Failed to export configuration: {str(e)}'
        )


@router.post("/import")
async def import_config(
    file: UploadFile = File(...),
    user: dict = Depends(require_role("admin"))
):
    """Import configuration with automatic backup and rollback on failure"""
    if not file.filename.endswith('.json'):
        raise HTTPException(
            status_code=400,
            detail='Only JSON files are allowed'
        )

    # Create backup before import
    backup_dir, backed_up_files = create_timestamped_backup(
        [CONFIG_PATH, CONFIG_DIR / 'devices.csv', CONFIG_DIR / 'otto.env'],
        DATA_DIR / 'backups'
    )

    audit_log(
        'config_import_backup_created',
        user=user.get('sub'),
        resource=str(backup_dir)
    )

    try:
        # Read and validate JSON
        raw = await file.read()
        try:
            new_config = json.loads(raw)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=400,
                detail=f'Invalid JSON: {str(e)}'
            )

        # Write new config
        save_config(new_config)

        # Verify config can be loaded
        test_config = load_config()
        if not test_config:
            raise RuntimeError('Failed to reload configuration after import')

        audit_log(
            'config_imported_successfully',
            user=user.get('sub'),
            resource=file.filename
        )

        return {
            "success": True,
            "message": "Configuration imported successfully",
            "backup_id": backup_dir.name
        }

    except HTTPException:
        raise
    except Exception as e:
        # Rollback on failure
        try:
            restore_backup(backup_dir, CONFIG_DIR)
            audit_log(
                'config_import_rollback_completed',
                user=user.get('sub'),
                resource=str(backup_dir)
            )
        except Exception as rollback_error:
            audit_log(
                'config_import_rollback_failed',
                user=user.get('sub'),
                resource=str(rollback_error)
            )

        raise HTTPException(
            status_code=500,
            detail=f'Import failed and was rolled back: {str(e)}'
        )


@router.get("/backups")
async def list_backups(user: dict = Depends(require_role("admin"))):
    """List available configuration backups"""
    try:
        backup_root = DATA_DIR / 'backups'

        if not backup_root.exists():
            return {"backups": []}

        backups = []
        for backup_dir in sorted(backup_root.iterdir(), reverse=True):
            if backup_dir.is_dir():
                # Get backup info
                backup_info = {
                    "id": backup_dir.name,
                    "timestamp": backup_dir.name,
                    "files": []
                }

                # List files in backup
                for file_path in backup_dir.iterdir():
                    if file_path.is_file():
                        backup_info["files"].append({
                            "name": file_path.name,
                            "size": file_path.stat().st_size
                        })

                backups.append(backup_info)

        # Limit to most recent 50 backups
        backups = backups[:50]

        audit_log(
            'backup_list_viewed',
            user=user.get('sub')
        )

        return {"backups": backups}

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f'Failed to list backups: {str(e)}'
        )


@router.post("/restore")
async def restore_config_backup(
    request: Request,
    user: dict = Depends(require_role("admin"))
):
    """Restore configuration from a backup"""
    try:
        data = await request.json()
        backup_id = data.get('backup_id')

        if not backup_id:
            raise HTTPException(
                status_code=400,
                detail='backup_id is required'
            )

        backup_dir = DATA_DIR / 'backups' / backup_id

        if not backup_dir.exists():
            raise HTTPException(
                status_code=404,
                detail=f'Backup {backup_id} not found'
            )

        # Create a backup of current state before restoring
        current_backup_dir, _ = create_timestamped_backup(
            [CONFIG_PATH, CONFIG_DIR / 'devices.csv', CONFIG_DIR / 'otto.env'],
            DATA_DIR / 'backups'
        )

        # Restore from backup
        restore_backup(backup_dir, CONFIG_DIR)

        # Reload and verify
        test_config = load_config()
        if not test_config:
            # Rollback if restore failed
            restore_backup(current_backup_dir, CONFIG_DIR)
            raise RuntimeError('Failed to reload configuration after restore')

        audit_log(
            'config_restored_from_backup',
            user=user.get('sub'),
            resource=backup_id
        )

        return {
            "success": True,
            "message": f"Configuration restored from backup {backup_id}",
            "previous_backup_id": current_backup_dir.name
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f'Failed to restore backup: {str(e)}'
        )

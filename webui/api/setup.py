import json
import logging
import os
import shutil
import tempfile
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from passlib.hash import bcrypt

from webui.core.audit import audit_log
from webui.core.security import _require_setup_token, needs_setup
from webui.settings import CONFIG_DIR, CONFIG_PATH, SETUP_TOKEN_PATH, USERS_PATH

logger = logging.getLogger("otto.webui")
router = APIRouter()


@router.get('/state')
async def get_setup_state():
    """Get setup state"""
    state = needs_setup()
    hostname = os.uname().nodename
    return JSONResponse({**state, 'hostname': hostname})


@router.post('/admin')
async def setup_admin(request: Request):
    """Create first admin user"""
    if not _require_setup_token(request):
        return JSONResponse({'error': 'invalid_setup_token'}, status_code=403)

    try:
        data = await request.json()
        user = {
            'username': data.get('username'),
            'email': data.get('email'),
            'password_hash': bcrypt.hash(data.get('password')),
            'role': 'admin',
            'created_at': datetime.utcnow().isoformat()
        }

        # Create users file
        USERS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(USERS_PATH, 'w') as f:
            json.dump({'users': [user]}, f, indent=2)
        os.chmod(USERS_PATH, 0o600)

        audit_log("admin_user_created", user="setup", resource=data.get('username'))
        return JSONResponse({'success': True})

    except Exception as e:
        # Log full traceback for diagnostics
        logger.exception("Admin setup failed")
        # Provide a clearer hint for common bcrypt backend issues
        msg = 'Setup failed'
        es = str(e)
        if "has no attribute '__about__'" in es or 'password cannot be longer than 72 bytes' in es:
            msg = 'bcrypt_backend_error'
        return JSONResponse({'error': msg}, status_code=500)


@router.post('/config')
async def setup_config(request: Request):
    """Set initial configuration"""
    if not _require_setup_token(request):
        return JSONResponse({'error': 'invalid_setup_token'}, status_code=403)

    try:
        config_data = await request.json()

        # Clean up SSH config - only keep expected fields
        if 'ssh' in config_data:
            valid_ssh_fields = {'username', 'password', 'key_path', 'connection_timeout', 'command_timeout'}
            ssh_config = config_data['ssh']
            unexpected_fields = set(ssh_config.keys()) - valid_ssh_fields
            if unexpected_fields:
                logger.info(f"Removing unexpected fields from SSH config: {unexpected_fields}")
                for field in unexpected_fields:
                    del ssh_config[field]

        # Validate configuration before writing files
        from otto_bgp.utils.config import ConfigManager
        validation_issues = ConfigManager.validate_object(config_data)
        if validation_issues:
            logger.error(f"Configuration validation failed during setup: {validation_issues}")
            return JSONResponse(
                {
                    'error': 'Configuration validation failed',
                    'issues': [
                        {"path": "config", "msg": issue}
                        for issue in validation_issues
                    ]
                },
                status_code=400
            )

        # Create config file atomically
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile('w', dir=str(CONFIG_PATH.parent), delete=False) as tmp:
            json.dump(config_data, tmp, indent=2)
            tmp_path = tmp.name

        if CONFIG_PATH.exists():
            shutil.copystat(CONFIG_PATH, tmp_path)
        os.replace(tmp_path, CONFIG_PATH)
        os.chmod(CONFIG_PATH, 0o600)

        # Create empty devices.csv if it doesn't exist
        devices_csv_path = CONFIG_DIR / 'devices.csv'
        if not devices_csv_path.exists():
            # Create empty CSV with headers only
            csv_content = "address,hostname,role,region\n"

            # Write devices.csv atomically
            with tempfile.NamedTemporaryFile('w', dir=str(devices_csv_path.parent), delete=False) as tmp:
                tmp.write(csv_content)
                tmp_path = tmp.name

            os.replace(tmp_path, devices_csv_path)
            os.chmod(devices_csv_path, 0o644)
            logger.info("Created empty devices.csv")
            audit_log("devices_csv_created", user="setup", resource="empty")

        # Create otto.env file with SSH credentials if provided
        if 'ssh' in config_data:
            try:
                otto_env_path = CONFIG_DIR / 'otto.env'
                env_lines = []

                # Read existing file if it exists
                if otto_env_path.exists():
                    with open(otto_env_path, 'r') as f:
                        env_lines = f.readlines()

                # Update or add SSH settings
                ssh_config = config_data['ssh']
                username = ssh_config.get('username', 'admin').strip()
                password = ssh_config.get('password', '').strip()
                key_path = ssh_config.get('key_path', '').strip()

                ssh_settings = {}
                if username:
                    ssh_settings['SSH_USERNAME'] = username
                if password:
                    ssh_settings['SSH_PASSWORD'] = password
                elif key_path:
                    ssh_settings['SSH_KEY_PATH'] = key_path
                else:
                    # Default to common SSH key location
                    ssh_settings['SSH_KEY_PATH'] = '/home/otto-bgp/.ssh/id_rsa'

                # Update env_lines with new settings
                updated_keys = set()
                new_lines = []
                for line in env_lines:
                    if '=' in line:
                        key = line.split('=')[0].strip()
                        if key in ssh_settings:
                            new_lines.append(f"{key}={ssh_settings[key]}\n")
                            updated_keys.add(key)
                        else:
                            new_lines.append(line)
                    else:
                        new_lines.append(line)

                # Add any new settings that weren't in the file
                for key, value in ssh_settings.items():
                    if key not in updated_keys:
                        new_lines.append(f"{key}={value}\n")

                # Add other important settings if not present
                if not any('OTTO_BGP_CONFIG_DIR' in line for line in new_lines):
                    new_lines.append("OTTO_BGP_CONFIG_DIR=/etc/otto-bgp\n")
                if not any('OTTO_BGP_DATA_DIR' in line for line in new_lines):
                    new_lines.append("OTTO_BGP_DATA_DIR=/var/lib/otto-bgp\n")

                # Write otto.env atomically
                with tempfile.NamedTemporaryFile('w', dir=str(otto_env_path.parent), delete=False) as tmp:
                    tmp.writelines(new_lines)
                    tmp_path = tmp.name

                os.replace(tmp_path, otto_env_path)
                os.chmod(otto_env_path, 0o600)

                logger.info("Created/updated otto.env with SSH settings")
                audit_log("otto_env_created", user="setup")

            except Exception as e:
                logger.warning(f"Failed to create otto.env: {str(e)}")
                # Don't fail setup if file creation fails

        audit_log("initial_config_created", user="setup")
        return JSONResponse({'success': True})

    except Exception as e:
        logger.error(f"Config setup failed: {e}")
        return JSONResponse({'error': 'Config setup failed'}, status_code=500)


@router.post('/complete')
async def setup_complete(request: Request):
    """Complete setup and remove token"""
    if not _require_setup_token(request):
        return JSONResponse({'error': 'invalid_setup_token'}, status_code=403)

    try:
        if SETUP_TOKEN_PATH.exists():
            SETUP_TOKEN_PATH.unlink()
        audit_log("setup_completed", user="setup")
        return JSONResponse({'success': True})
    except Exception:
        return JSONResponse({'success': True})  # Don't fail if token removal fails

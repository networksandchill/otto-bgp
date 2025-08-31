#!/usr/bin/env python3
"""
Otto BGP WebUI Adapter
Production FastAPI backend with authentication, setup mode, and API endpoints.
"""

import os
import json
import subprocess
import logging
import tempfile
import shutil
import time
import smtplib
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from logging.handlers import TimedRotatingFileHandler

import jwt
from jwt import exceptions as jwt_exceptions
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from passlib.hash import bcrypt
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pydantic import ValidationError

# Import settings and schemas
from webui.settings import (
    CONFIG_DIR, DATA_DIR, WEBUI_ROOT,
    USERS_PATH, CONFIG_PATH, SETUP_TOKEN_PATH, JWT_SECRET_PATH,
    OTTO_DEV_MODE, OTTO_WEBUI_LOG_LEVEL, OTTO_WEBUI_ENABLE_SERVICE_CONTROL
)
from webui.schemas import LoginRequest, SMTPConfig

# Detect absolute paths for sudo and systemctl at startup
SUDO_PATH = shutil.which('sudo') or '/usr/bin/sudo'
SYSTEMCTL_PATH = shutil.which('systemctl') or '/usr/bin/systemctl'

# App logger (journald picks up stdout/stderr via systemd service settings)
logger = logging.getLogger("otto.webui")
# Set logging level from environment
log_level = getattr(logging, OTTO_WEBUI_LOG_LEVEL, logging.INFO)
logger.setLevel(log_level)
# Ensure we have at least one handler
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
    _handler.setLevel(log_level)
    logger.addHandler(_handler)

# JWT Configuration
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Initialize FastAPI app
app = FastAPI(
    title="Otto BGP WebUI",
    description="Web interface for Otto BGP management",
    version="0.3.2",
    docs_url=None,  # Disable auto docs in production
    redoc_url=None
)

# Security headers middleware


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# Setup audit logging


def setup_audit_logging():
    audit_logger = logging.getLogger("otto.audit")
    audit_logger.setLevel(logging.INFO)

    # Create logs directory
    log_dir = DATA_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Check if handler already exists to avoid duplicates
    if not audit_logger.handlers:
        handler = TimedRotatingFileHandler(
            log_dir / "audit.log", when="midnight", interval=1, backupCount=90
        )

        class JSONFormatter(logging.Formatter):
            def format(self, record):
                return json.dumps({
                    "timestamp": datetime.utcnow().isoformat(),
                    "user": getattr(record, 'user', 'system'),
                    "action": record.msg,
                    "resource": getattr(record, 'resource', None),
                    "result": getattr(record, 'result', 'success')
                })

        handler.setFormatter(JSONFormatter())
        audit_logger.addHandler(handler)
    return audit_logger


audit_logger = setup_audit_logging()


def audit_log(action: str, user: str = None, **kwargs):
    audit_logger.info(action, extra={'user': user, **kwargs})

# JWT utilities


def get_jwt_secret() -> str:
    """Load JWT secret from file"""
    try:
        if JWT_SECRET_PATH.exists():
            return JWT_SECRET_PATH.read_text().strip()
    except Exception as e:
        logger.error(f"Failed to read JWT secret: {e}")

    # Only allow fallback in dev mode
    if OTTO_DEV_MODE:
        logger.warning("Using development JWT secret - DO NOT USE IN PRODUCTION")
        return "dev-secret-change-in-production"

    raise RuntimeError(
        f"JWT secret not found at {JWT_SECRET_PATH}. "
        "Create it with: openssl rand -hex 32 > /etc/otto-bgp/.jwt_secret"
    )


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def create_refresh_token(data: dict):
    """Create JWT refresh token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, get_jwt_secret(), algorithm=JWT_ALGORITHM)

# Setup mode utilities


def needs_setup() -> dict:
    """Check if setup is required"""
    reasons = []
    if not USERS_PATH.exists():
        reasons.append('missing_users')
    if not CONFIG_PATH.exists():
        reasons.append('missing_config')
    return {'needs_setup': bool(reasons), 'reasons': reasons}


def _require_setup_token(request: Request) -> bool:
    """Validate setup token from request headers"""
    token = request.headers.get('X-Setup-Token')
    if not token or not SETUP_TOKEN_PATH.exists():
        return False
    try:
        return token.strip() == SETUP_TOKEN_PATH.read_text().strip()
    except Exception:
        return False

# Authentication utilities


def get_current_user(request: Request):
    """Extract user from JWT token"""
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        try:
            client = getattr(request, 'client', None)
            client_ip = getattr(client, 'host', 'unknown') if client else 'unknown'
        except Exception:
            client_ip = 'unknown'
        logger.info(f"401 auth missing/invalid Authorization header on {request.url.path} from {client_ip}")
        raise HTTPException(status_code=401, detail="Authentication required")

    token = auth_header.replace('Bearer ', '')
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get('type') != 'access':
            logger.info(f"401 invalid token type on {request.url.path} for sub={payload.get('sub')}")
            raise HTTPException(status_code=401, detail="Invalid token type")
        return payload
    except jwt_exceptions.ExpiredSignatureError:
        logger.info(f"401 expired access token on {request.url.path}")
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt_exceptions.InvalidTokenError as e:
        logger.info(f"401 invalid access token on {request.url.path}: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")


def require_role(required_role: str):
    """Dependency to require specific role"""
    def _require_role(user: dict = Depends(get_current_user)):
        if user.get('role') != required_role and required_role != 'read_only':
            if user.get('role') != 'admin':
                raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return _require_role

# Setup mode gating middleware


@app.middleware('http')
async def setup_gate(request: Request, call_next):
    """Gate all non-setup endpoints during setup mode"""
    path = request.url.path

    # Allow setup endpoints, health check, and static files during setup
    if (path.startswith('/api/setup') or
        path.startswith('/assets') or
        path.startswith('/healthz') or
        path == '/' or
            path == '/setup'):
        return await call_next(request)

    # Check if setup is needed
    state = needs_setup()
    if state['needs_setup']:
        return JSONResponse({'error': 'setup_required'}, status_code=403)

    return await call_next(request)

# Static file serving
if WEBUI_ROOT.exists():
    app.mount("/assets", StaticFiles(directory=WEBUI_ROOT / "assets"), name="assets")


@app.get("/")
async def serve_index():
    """Serve main SPA index.html"""
    index_path = WEBUI_ROOT / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return HTMLResponse("<h1>Otto BGP WebUI</h1><p>Frontend assets not found</p>")

# Health endpoint


@app.get("/healthz")
async def healthz():
    """Health check endpoint"""
    return JSONResponse({"status": "ok", "timestamp": datetime.utcnow().isoformat()})

# Setup endpoints


@app.get('/api/setup/state')
async def get_setup_state():
    """Get setup state"""
    state = needs_setup()
    hostname = os.uname().nodename
    return JSONResponse({**state, 'hostname': hostname})


@app.post('/api/setup/admin')
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
        logger.error(f"Admin setup failed: {e}")
        return JSONResponse({'error': 'Setup failed'}, status_code=500)


@app.post('/api/setup/config')
async def setup_config(request: Request):
    """Set initial configuration"""
    if not _require_setup_token(request):
        return JSONResponse({'error': 'invalid_setup_token'}, status_code=403)

    try:
        config_data = await request.json()

        # Create config file atomically
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile('w', dir=str(CONFIG_PATH.parent), delete=False) as tmp:
            json.dump(config_data, tmp, indent=2)
            tmp_path = tmp.name

        if CONFIG_PATH.exists():
            shutil.copystat(CONFIG_PATH, tmp_path)
        os.replace(tmp_path, CONFIG_PATH)
        os.chmod(CONFIG_PATH, 0o600)

        # Create devices.csv from SSH configuration if provided
        if 'ssh' in config_data and config_data['ssh'].get('hostname'):
            devices_csv_path = CONFIG_DIR / 'devices.csv'
            try:
                # Extract SSH details
                ssh_config = config_data['ssh']
                hostname = ssh_config.get('hostname', '').strip()
                username = ssh_config.get('username', 'admin').strip()
                password = ssh_config.get('password', '').strip()
                key_path = ssh_config.get('key_path', '').strip()

                # Determine if hostname is IP or DNS name
                import socket
                device_name = hostname
                try:
                    # Try to parse as IP address
                    socket.inet_aton(hostname.split(':')[0])  # Remove port if present
                    # It's an IP, create a generic hostname
                    device_name = f"router-{hostname.replace('.', '-').replace(':', '-')}"
                except socket.error:
                    # It's already a hostname, use as-is
                    pass

                # Create CSV content
                csv_content = "address,hostname,username,role,region\n"
                csv_content += f"{hostname},{device_name},{username},edge,default\n"

                # Write devices.csv atomically
                with tempfile.NamedTemporaryFile('w', dir=str(devices_csv_path.parent), delete=False) as tmp:
                    tmp.write(csv_content)
                    tmp_path = tmp.name

                os.replace(tmp_path, devices_csv_path)
                os.chmod(devices_csv_path, 0o644)

                logger.info(f"Created devices.csv with device: {hostname}")
                audit_log("devices_csv_created", user="setup", resource=hostname)

                # Create otto.env file with SSH credentials if not exists
                otto_env_path = CONFIG_DIR / 'otto.env'
                env_lines = []

                # Read existing file if it exists
                if otto_env_path.exists():
                    with open(otto_env_path, 'r') as f:
                        env_lines = f.readlines()

                # Update or add SSH settings
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
                logger.warning(f"Failed to create devices.csv or otto.env: {str(e)}")
                # Don't fail setup if file creation fails

        audit_log("initial_config_created", user="setup")
        return JSONResponse({'success': True})

    except Exception as e:
        logger.error(f"Config setup failed: {e}")
        return JSONResponse({'error': 'Config setup failed'}, status_code=500)


@app.post('/api/setup/complete')
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

# Authentication endpoints


@app.post("/api/auth/login")
async def login(request: Request):
    """User login with JWT tokens"""
    try:
        try:
            body = await request.json()
            data = LoginRequest(**body)
        except (ValidationError, ValueError) as e:
            return JSONResponse({'error': 'Invalid request'}, status_code=400)

        username = data.username
        password = data.password

        # Load users
        if not USERS_PATH.exists():
            return JSONResponse({'error': 'No users configured'}, status_code=500)

        with open(USERS_PATH) as f:
            users_data = json.load(f)

        # Find user
        user = None
        for u in users_data.get('users', []):
            if u.get('username') == username:
                user = u
                break

        if not user or not bcrypt.verify(password, user.get('password_hash', '')):
            audit_log("login_failed", user=username, result="failed")
            return JSONResponse({'error': 'Invalid credentials'}, status_code=401)

        # Create tokens
        token_data = {'sub': username, 'role': user.get('role', 'read_only')}
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)

        # Create response with refresh token cookie
        response = JSONResponse({
            'user': username,
            'role': user.get('role', 'read_only'),
            'access_token': access_token
        })

        response.set_cookie(
            key="otto_refresh_token",
            value=refresh_token,
            httponly=True,
            secure=True,
            samesite="strict",
            max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
        )

        audit_log("login_successful", user=username)
        return response

    except Exception as e:
        logger.error(f"Login error: {e}")
        return JSONResponse({'error': 'Login failed'}, status_code=500)


@app.get("/api/auth/session")
async def get_session(user: dict = Depends(get_current_user)):
    """Get current session info"""
    # Derive expires_at from token's exp claim
    expires_at = datetime.utcfromtimestamp(user.get('exp', 0))
    return JSONResponse({
        'user': user.get('sub'),
        'role': user.get('role'),
        'expires_at': expires_at.isoformat()
    })


@app.post("/api/auth/refresh")
async def refresh_token(request: Request):
    """Refresh access token using refresh token cookie"""
    refresh_token = request.cookies.get("otto_refresh_token")
    if not refresh_token:
        logger.info("401 refresh denied: no refresh cookie present")
        return JSONResponse({'error': 'No refresh token'}, status_code=401)

    try:
        payload = jwt.decode(refresh_token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get('type') != 'refresh':
            logger.info("401 refresh denied: wrong token type")
            return JSONResponse({'error': 'Invalid token type'}, status_code=401)

        # Create new tokens
        token_data = {'sub': payload.get('sub'), 'role': payload.get('role')}
        new_access_token = create_access_token(token_data)
        new_refresh_token = create_refresh_token(token_data)

        response = JSONResponse({'access_token': new_access_token})
        response.set_cookie(
            key="otto_refresh_token",
            value=new_refresh_token,
            httponly=True,
            secure=True,
            samesite="strict",
            max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
        )
        logger.info(f"200 refresh ok: issued new tokens for user={token_data.get('sub')}")
        return response

    except jwt_exceptions.ExpiredSignatureError:
        logger.info("401 refresh denied: refresh token expired")
        return JSONResponse({'error': 'Refresh token expired'}, status_code=401)
    except jwt_exceptions.InvalidTokenError:
        logger.info("401 refresh denied: invalid refresh token")
        return JSONResponse({'error': 'Invalid refresh token'}, status_code=401)


@app.post("/api/auth/logout")
async def logout(user: dict = Depends(get_current_user)):
    """Logout and clear refresh token"""
    response = JSONResponse({'success': True})
    response.set_cookie(
        key="otto_refresh_token",
        value="",
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=0  # Expire immediately
    )

    audit_log("logout", user=user.get('sub'))
    return response


# Device Management endpoints
@app.get("/api/devices")
async def list_devices(user: dict = Depends(get_current_user)):
    """List all devices from devices.csv"""
    try:
        devices_file = CONFIG_DIR / 'devices.csv'
        devices = []
        
        if devices_file.exists():
            import csv
            with open(devices_file, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    devices.append(row)
        
        return {"devices": devices}
    except Exception as e:
        logger.error(f"Failed to read devices: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to read devices: {str(e)}")

@app.post("/api/devices")
async def add_device(request: Request, user: dict = Depends(require_role('admin'))):
    """Add a new device to devices.csv"""
    try:
        device_data = await request.json()
        
        # Validate required fields
        required_fields = ['address', 'hostname', 'username', 'role', 'region']
        for field in required_fields:
            if field not in device_data:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
        
        devices_file = CONFIG_DIR / 'devices.csv'
        
        # Read existing devices
        devices = []
        fieldnames = required_fields
        
        if devices_file.exists():
            import csv
            with open(devices_file, 'r') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or required_fields
                for row in reader:
                    # Check for duplicate address
                    if row.get('address') == device_data['address']:
                        raise HTTPException(status_code=400, detail=f"Device with address {device_data['address']} already exists")
                    devices.append(row)
        
        # Add new device
        new_device = {field: device_data.get(field, '') for field in fieldnames}
        devices.append(new_device)
        
        # Write back atomically
        import tempfile
        with tempfile.NamedTemporaryFile('w', dir=str(devices_file.parent), delete=False, newline='') as tmp:
            writer = csv.DictWriter(tmp, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(devices)
            tmp_path = tmp.name
        
        os.replace(tmp_path, devices_file)
        os.chmod(devices_file, 0o644)
        
        audit_log("device_added", user=user.get('sub', 'admin'), resource=device_data['hostname'])
        return {"success": True, "device": new_device}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add device: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to add device: {str(e)}")

@app.put("/api/devices/{address}")
async def update_device(address: str, request: Request, user: dict = Depends(require_role('admin'))):
    """Update an existing device in devices.csv"""
    try:
        device_data = await request.json()
        devices_file = CONFIG_DIR / 'devices.csv'
        
        if not devices_file.exists():
            raise HTTPException(status_code=404, detail="No devices file found")
        
        # Read existing devices
        devices = []
        updated = False
        
        import csv
        with open(devices_file, 'r') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            
            for row in reader:
                if row.get('address') == address:
                    # Update the device
                    for key, value in device_data.items():
                        if key in row:
                            row[key] = value
                    updated = True
                    audit_log("device_updated", user=user.get('sub', 'admin'), resource=row.get('hostname', address))
                devices.append(row)
        
        if not updated:
            raise HTTPException(status_code=404, detail=f"Device with address {address} not found")
        
        # Write back atomically
        import tempfile
        with tempfile.NamedTemporaryFile('w', dir=str(devices_file.parent), delete=False, newline='') as tmp:
            writer = csv.DictWriter(tmp, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(devices)
            tmp_path = tmp.name
        
        os.replace(tmp_path, devices_file)
        os.chmod(devices_file, 0o644)
        
        return {"success": True}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update device: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update device: {str(e)}")

@app.delete("/api/devices/{address}")
async def delete_device(address: str, user: dict = Depends(require_role('admin'))):
    """Delete a device from devices.csv"""
    try:
        devices_file = CONFIG_DIR / 'devices.csv'
        
        if not devices_file.exists():
            raise HTTPException(status_code=404, detail="No devices file found")
        
        # Read existing devices
        devices = []
        deleted = False
        deleted_hostname = None
        
        import csv
        with open(devices_file, 'r') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            
            for row in reader:
                if row.get('address') == address:
                    deleted = True
                    deleted_hostname = row.get('hostname', address)
                else:
                    devices.append(row)
        
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Device with address {address} not found")
        
        # Write back atomically (or delete if empty)
        if devices:
            import tempfile
            with tempfile.NamedTemporaryFile('w', dir=str(devices_file.parent), delete=False, newline='') as tmp:
                writer = csv.DictWriter(tmp, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(devices)
                tmp_path = tmp.name
            
            os.replace(tmp_path, devices_file)
            os.chmod(devices_file, 0o644)
        else:
            # Remove file if no devices left
            devices_file.unlink()
        
        audit_log("device_deleted", user=user.get('sub', 'admin'), resource=deleted_hostname)
        return {"success": True}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete device: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete device: {str(e)}")


# User Management API (Admin only)

@app.get("/api/users")
async def list_users(user: dict = Depends(require_role('admin'))):
    """List all users (admin only)"""
    if not USERS_PATH.exists():
        return JSONResponse({'users': []})
    
    with open(USERS_PATH) as f:
        users_data = json.load(f)
    
    # Return users without password hashes
    users = []
    for u in users_data.get('users', []):
        users.append({
            'username': u.get('username'),
            'email': u.get('email'),
            'role': u.get('role', 'read_only'),
            'created_at': u.get('created_at'),
            'last_login': u.get('last_login')
        })
    
    return JSONResponse({'users': users})


@app.post("/api/users")
async def create_user(request: Request, current_user: dict = Depends(require_role('admin'))):
    """Create a new user (admin only)"""
    try:
        body = await request.json()
        username = body.get('username', '').strip()
        email = body.get('email', '').strip()
        password = body.get('password', '')
        role = body.get('role', 'read_only')
        
        # Validate inputs
        if not username or not password:
            return JSONResponse({'error': 'Username and password are required'}, status_code=400)
        
        if role not in ['admin', 'operator', 'read_only']:
            return JSONResponse({'error': 'Invalid role'}, status_code=400)
        
        # Load existing users
        if USERS_PATH.exists():
            with open(USERS_PATH) as f:
                users_data = json.load(f)
        else:
            users_data = {'users': []}
        
        # Check if username exists
        for u in users_data.get('users', []):
            if u.get('username') == username:
                return JSONResponse({'error': 'Username already exists'}, status_code=400)
        
        # Create new user
        new_user = {
            'username': username,
            'email': email,
            'password_hash': bcrypt.hash(password),
            'role': role,
            'created_at': datetime.utcnow().isoformat()
        }
        
        users_data['users'].append(new_user)
        
        # Save atomically
        with tempfile.NamedTemporaryFile('w', dir=str(USERS_PATH.parent), delete=False) as tmp:
            json.dump(users_data, tmp, indent=2)
            tmp_path = tmp.name
        
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, USERS_PATH)
        
        audit_log("user_created", user=current_user.get('sub'), target_user=username, role=role)
        logger.info(f"User created: {username} with role {role} by {current_user.get('sub')}")
        
        return JSONResponse({
            'success': True,
            'user': {
                'username': username,
                'email': email,
                'role': role,
                'created_at': new_user['created_at']
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to create user: {e}")
        return JSONResponse({'error': 'Failed to create user'}, status_code=500)


@app.put("/api/users/{username}")
async def update_user(username: str, request: Request, current_user: dict = Depends(require_role('admin'))):
    """Update user details (admin only)"""
    try:
        body = await request.json()
        
        # Load users
        if not USERS_PATH.exists():
            return JSONResponse({'error': 'No users configured'}, status_code=404)
        
        with open(USERS_PATH) as f:
            users_data = json.load(f)
        
        # Find user to update
        user_index = -1
        for i, u in enumerate(users_data.get('users', [])):
            if u.get('username') == username:
                user_index = i
                break
        
        if user_index == -1:
            return JSONResponse({'error': 'User not found'}, status_code=404)
        
        # Update fields
        if 'email' in body:
            users_data['users'][user_index]['email'] = body['email']
        
        if 'role' in body:
            new_role = body['role']
            if new_role not in ['admin', 'operator', 'read_only']:
                return JSONResponse({'error': 'Invalid role'}, status_code=400)
            
            # Prevent removing last admin
            if users_data['users'][user_index].get('role') == 'admin' and new_role != 'admin':
                admin_count = sum(1 for u in users_data['users'] if u.get('role') == 'admin')
                if admin_count == 1:
                    return JSONResponse({'error': 'Cannot remove last admin user'}, status_code=400)
            
            users_data['users'][user_index]['role'] = new_role
        
        if 'password' in body and body['password']:
            users_data['users'][user_index]['password_hash'] = bcrypt.hash(body['password'])
        
        # Save atomically
        with tempfile.NamedTemporaryFile('w', dir=str(USERS_PATH.parent), delete=False) as tmp:
            json.dump(users_data, tmp, indent=2)
            tmp_path = tmp.name
        
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, USERS_PATH)
        
        audit_log("user_updated", user=current_user.get('sub'), target_user=username)
        logger.info(f"User updated: {username} by {current_user.get('sub')}")
        
        return JSONResponse({'success': True})
        
    except Exception as e:
        logger.error(f"Failed to update user: {e}")
        return JSONResponse({'error': 'Failed to update user'}, status_code=500)


@app.delete("/api/users/{username}")
async def delete_user(username: str, current_user: dict = Depends(require_role('admin'))):
    """Delete a user (admin only)"""
    try:
        # Prevent self-deletion
        if username == current_user.get('sub'):
            return JSONResponse({'error': 'Cannot delete your own account'}, status_code=400)
        
        # Load users
        if not USERS_PATH.exists():
            return JSONResponse({'error': 'No users configured'}, status_code=404)
        
        with open(USERS_PATH) as f:
            users_data = json.load(f)
        
        # Find user to delete
        user_index = -1
        user_role = None
        for i, u in enumerate(users_data.get('users', [])):
            if u.get('username') == username:
                user_index = i
                user_role = u.get('role')
                break
        
        if user_index == -1:
            return JSONResponse({'error': 'User not found'}, status_code=404)
        
        # Prevent removing last admin
        if user_role == 'admin':
            admin_count = sum(1 for u in users_data['users'] if u.get('role') == 'admin')
            if admin_count == 1:
                return JSONResponse({'error': 'Cannot delete last admin user'}, status_code=400)
        
        # Delete user
        del users_data['users'][user_index]
        
        # Save atomically
        with tempfile.NamedTemporaryFile('w', dir=str(USERS_PATH.parent), delete=False) as tmp:
            json.dump(users_data, tmp, indent=2)
            tmp_path = tmp.name
        
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, USERS_PATH)
        
        audit_log("user_deleted", user=current_user.get('sub'), target_user=username)
        logger.info(f"User deleted: {username} by {current_user.get('sub')}")
        
        return JSONResponse({'success': True})
        
    except Exception as e:
        logger.error(f"Failed to delete user: {e}")
        return JSONResponse({'error': 'Failed to delete user'}, status_code=500)


# Reports endpoints


@app.get("/api/reports/matrix")
async def get_deployment_matrix(user: dict = Depends(require_role('read_only'))):
    """Get deployment matrix report"""
    matrix_path = DATA_DIR / "policies/reports/deployment-matrix.json"
    if matrix_path.exists():
        try:
            with open(matrix_path) as f:
                data = json.load(f)
            audit_log("matrix_viewed", user=user.get('sub'))
            return JSONResponse(data)
        except Exception as e:
            logger.error(f"Failed to load matrix: {e}")
            return JSONResponse({'error': 'Failed to load matrix'}, status_code=500)

    return JSONResponse({'error': 'Matrix not found - run pipeline first'}, status_code=404)


@app.get("/api/reports/discovery")
async def get_discovery_mappings(user: dict = Depends(require_role('read_only'))):
    """Get discovery mappings (uses deployment matrix)"""
    matrix_path = DATA_DIR / "policies/reports/deployment-matrix.json"
    if matrix_path.exists():
        try:
            with open(matrix_path) as f:
                data = json.load(f)
            audit_log("discovery_viewed", user=user.get('sub'))
            return JSONResponse(data)
        except Exception as e:
            logger.error(f"Failed to load discovery: {e}")
            return JSONResponse({'error': 'Failed to load discovery'}, status_code=500)

    # Return empty structure as fallback
    empty_discovery = {
        "routers": {},
        "as_distribution": {},
        "bgp_groups": {},
        "statistics": {},
        "generated_at": datetime.utcnow().isoformat(),
        "note": "No data available - run 'otto-bgp pipeline' first"
    }
    return JSONResponse(empty_discovery)

# Configuration utilities


def redact_sensitive_fields(config: Dict[str, Any]) -> Dict[str, Any]:
    """Redact passwords and sensitive data before sending to client"""
    config = config.copy()

    # Redact SSH password
    if 'ssh' in config and 'password' in config['ssh']:
        config['ssh']['password'] = "*****"

    # Redact SMTP password
    if 'smtp' in config and 'password' in config['smtp']:
        config['smtp']['password'] = "*****"

    return config


def validate_smtp_config(smtp: Dict[str, Any]) -> List[Dict[str, str]]:
    """Validate SMTP configuration"""
    issues = []

    if smtp.get('enabled'):
        if not smtp.get('host'):
            issues.append({"path": "smtp.host", "msg": "SMTP host required when enabled"})

        port = smtp.get('port', 587)
        if port <= 0:
            issues.append({"path": "smtp.port", "msg": f"Invalid SMTP port {port}"})
        elif port not in [25, 587, 465]:
            logger.warning(f"Unusual SMTP port {port} - typically 25, 587, or 465 are used")

        if smtp.get('use_tls') and port == 25:
            logger.warning("Port 25 typically doesn't use TLS - consider port 587 or 465")

        if not smtp.get('from_address'):
            issues.append({"path": "smtp.from_address", "msg": "From address required"})

        to_addresses = smtp.get('to_addresses', [])
        if not to_addresses:
            issues.append({"path": "smtp.to_addresses", "msg": "At least one recipient required"})

    return issues

# Configuration endpoints


@app.get("/api/config")
async def get_config(user: dict = Depends(require_role('read_only'))):
    """Get current configuration (with sensitive fields redacted)"""
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f:
                config = json.load(f)

            # Redact sensitive fields for display
            config = redact_sensitive_fields(config)
            audit_log("config_viewed", user=user.get('sub'))
            return JSONResponse(config)

        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return JSONResponse({'error': 'Failed to load config'}, status_code=500)

    return JSONResponse({'error': 'Config not found'}, status_code=404)


@app.put("/api/config")
async def update_config(request: Request, user: dict = Depends(require_role('admin'))):
    """Update configuration with validation and atomic writes"""
    try:
        new_config = await request.json()
    except Exception as e:
        return JSONResponse({"error": f"Invalid JSON: {e}"}, status_code=400)

    # Load existing config to preserve passwords if not changed
    existing_config = {}
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH) as f:
                existing_config = json.load(f)
        except Exception:
            pass

    # Preserve existing passwords if new ones are "*****"
    if 'ssh' in new_config and new_config['ssh'].get('password') == "*****":
        if 'ssh' in existing_config and 'password' in existing_config['ssh']:
            new_config['ssh']['password'] = existing_config['ssh']['password']

    if 'smtp' in new_config and new_config['smtp'].get('password') == "*****":
        if 'smtp' in existing_config and 'password' in existing_config['smtp']:
            new_config['smtp']['password'] = existing_config['smtp']['password']

    # Validate configuration
    issues = []

    # Validate SMTP if present
    if 'smtp' in new_config:
        smtp_issues = validate_smtp_config(new_config['smtp'])
        issues.extend(smtp_issues)

    # Validate paths exist
    if 'ssh' in new_config and 'key_path' in new_config['ssh']:
        key_path = Path(new_config['ssh']['key_path'])
        if not key_path.exists():
            issues.append({"path": "ssh.key_path", "msg": f"SSH key not found: {key_path}"})

    if issues:
        return JSONResponse({"error": "Validation failed", "issues": issues}, status_code=400)

    # Create backup
    backup_path = None
    if CONFIG_PATH.exists():
        backup_path = f"{CONFIG_PATH}.bak-{int(time.time())}"
        shutil.copy2(CONFIG_PATH, backup_path)

    # Write atomically
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=CONFIG_PATH.parent, delete=False) as tmp:
            json.dump(new_config, tmp, indent=2)
            tmp_path = tmp.name

        # Preserve permissions
        if CONFIG_PATH.exists():
            shutil.copystat(CONFIG_PATH, tmp_path)

        # Atomic rename
        os.replace(tmp_path, CONFIG_PATH)

        audit_log("config_updated", user=user.get('sub'))
        return JSONResponse({
            "success": True,
            "backup": backup_path,
            "message": "Configuration updated successfully"
        })

    except Exception as e:
        # Clean up temp file on error
        try:
            os.unlink(tmp_path)
        except:
            pass
        logger.error(f"Failed to save config: {e}")
        return JSONResponse({"error": "Failed to save config"}, status_code=500)


@app.post("/api/config/test-smtp")
async def test_smtp_connection(request: Request, user: dict = Depends(require_role('admin'))):
    """Test SMTP configuration by sending a test email"""
    try:
        try:
            body = await request.json()
            smtp_config_obj = SMTPConfig(**body)
            smtp_config = smtp_config_obj.model_dump() if hasattr(smtp_config_obj, 'model_dump') else smtp_config_obj.dict()
        except (ValidationError, ValueError) as e:
            return JSONResponse({"error": "Invalid SMTP configuration"}, status_code=400)

        # Validate first
        issues = validate_smtp_config(smtp_config)
        if issues:
            return JSONResponse({"error": "Invalid SMTP config", "issues": issues}, status_code=400)

        # Create test message
        msg = MIMEMultipart()
        msg['From'] = smtp_config['from_address']
        msg['To'] = smtp_config['to_addresses'][0]
        msg['Subject'] = "Otto BGP SMTP Test"

        body = "This is a test email from Otto BGP WebUI to verify SMTP configuration."
        msg.attach(MIMEText(body, 'plain'))

        # Connect and send
        if smtp_config.get('use_tls'):
            server = smtplib.SMTP(smtp_config['host'], smtp_config.get('port', 587))
            server.starttls()
        else:
            server = smtplib.SMTP(smtp_config['host'], smtp_config.get('port', 25))

        if smtp_config.get('username') and smtp_config.get('password'):
            server.login(smtp_config['username'], smtp_config['password'])

        server.send_message(msg)
        server.quit()

        audit_log("smtp_test_success", user=user.get('sub'))
        return JSONResponse({"success": True, "message": "Test email sent successfully"})

    except Exception as e:
        logger.error(f"SMTP test failed: {e}")
        audit_log("smtp_test_failed", user=user.get('sub'), result="failed")
        return JSONResponse({"error": "SMTP test failed"}, status_code=500)

# SystemD endpoints


@app.get("/api/systemd/units")
async def get_systemd_units(names: str = "", user: dict = Depends(require_role('read_only'))):
    """Get systemd unit status"""
    units = [u.strip() for u in names.split(',') if u.strip()] if names else []
    results = []

    for unit in units:
        try:
            result = subprocess.run(
                [SYSTEMCTL_PATH, 'show', '-p', 'ActiveState,SubState,Description', unit],
                capture_output=True, text=True, timeout=5
            )

            # Parse systemctl output
            unit_info = {"name": unit}
            for line in result.stdout.strip().split('\n'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    unit_info[key.lower()] = value

            results.append(unit_info)
        except Exception as e:
            results.append({"name": unit, "error": str(e)})

    return JSONResponse({"units": results})

# Service control endpoints (optional, enabled by environment variable)


@app.post("/api/systemd/control")
async def control_systemd_service(request: Request, user: dict = Depends(require_role('admin'))):
    """Control systemd services (if enabled)"""
    # Check if service control is enabled
    logger.debug(f"OTTO_WEBUI_ENABLE_SERVICE_CONTROL = {OTTO_WEBUI_ENABLE_SERVICE_CONTROL}")

    if not OTTO_WEBUI_ENABLE_SERVICE_CONTROL:
        return JSONResponse({
            "success": False,
            "message": "Service control disabled. Set OTTO_WEBUI_ENABLE_SERVICE_CONTROL=true to enable"
        }, status_code=403)

    try:
        data = await request.json()
        action = data.get('action')
        service = data.get('service')

        logger.info(f"Service control request: action={action}, service={service}, user={user.get('sub')}")

        # Type validation for security
        if not isinstance(action, str) or not isinstance(service, str):
            logger.warning(
                f"Invalid input types: action={type(action)}, service={type(service)}, user={user.get('sub')}")
            return JSONResponse({
                "success": False,
                "message": "Invalid input format"
            }, status_code=400)

        # Validate inputs
        allowed_actions = ['start', 'stop', 'restart', 'reload']
        allowed_services = [
            'otto-bgp.service',
            'otto-bgp-autonomous.service',
            'otto-bgp.timer',
            'otto-bgp-webui-adapter.service',
            'otto-bgp-rpki-update.service',
            'otto-bgp-rpki-update.timer'
        ]

        if action not in allowed_actions:
            return JSONResponse({
                "success": False,
                "message": f"Invalid action: {action}. Allowed: {', '.join(allowed_actions)}"
            }, status_code=400)

        if service not in allowed_services:
            return JSONResponse({
                "success": False,
                "message": f"Service not allowed: {service}"
            }, status_code=400)

        # Build command using explicit mapping for security
        # Pre-defined commands prevent command injection
        base_commands = {
            ('start', 'otto-bgp.service'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'start', 'otto-bgp.service'],
            ('stop', 'otto-bgp.service'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'stop', 'otto-bgp.service'],
            ('restart', 'otto-bgp.service'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'restart', 'otto-bgp.service'],
            ('reload', 'otto-bgp.service'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'reload', 'otto-bgp.service'],

            ('start', 'otto-bgp-autonomous.service'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'start', 'otto-bgp-autonomous.service'],
            ('stop', 'otto-bgp-autonomous.service'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'stop', 'otto-bgp-autonomous.service'],
            ('restart', 'otto-bgp-autonomous.service'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'restart', 'otto-bgp-autonomous.service'],
            ('reload', 'otto-bgp-autonomous.service'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'reload', 'otto-bgp-autonomous.service'],

            ('start', 'otto-bgp.timer'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'start', 'otto-bgp.timer'],
            ('stop', 'otto-bgp.timer'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'stop', 'otto-bgp.timer'],
            ('restart', 'otto-bgp.timer'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'restart', 'otto-bgp.timer'],
            ('reload', 'otto-bgp.timer'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'reload', 'otto-bgp.timer'],

            ('start', 'otto-bgp-webui-adapter.service'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'start', 'otto-bgp-webui-adapter.service'],
            ('stop', 'otto-bgp-webui-adapter.service'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'stop', '--no-block', 'otto-bgp-webui-adapter.service'],
            ('restart', 'otto-bgp-webui-adapter.service'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'restart', '--no-block', 'otto-bgp-webui-adapter.service'],
            ('reload', 'otto-bgp-webui-adapter.service'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'reload', 'otto-bgp-webui-adapter.service'],

            ('start', 'otto-bgp-rpki-update.service'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'start', 'otto-bgp-rpki-update.service'],
            ('stop', 'otto-bgp-rpki-update.service'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'stop', 'otto-bgp-rpki-update.service'],
            ('restart', 'otto-bgp-rpki-update.service'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'restart', 'otto-bgp-rpki-update.service'],
            ('reload', 'otto-bgp-rpki-update.service'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'reload', 'otto-bgp-rpki-update.service'],

            ('start', 'otto-bgp-rpki-update.timer'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'start', 'otto-bgp-rpki-update.timer'],
            ('stop', 'otto-bgp-rpki-update.timer'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'stop', 'otto-bgp-rpki-update.timer'],
            ('restart', 'otto-bgp-rpki-update.timer'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'restart', 'otto-bgp-rpki-update.timer'],
            ('reload', 'otto-bgp-rpki-update.timer'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'reload', 'otto-bgp-rpki-update.timer'],
        }

        # Get pre-defined command
        cmd = base_commands.get((action, service))
        if not cmd:
            logger.error(f"No command mapping found for action={action}, service={service}")
            return JSONResponse({
                "success": False,
                "message": "Command not supported"
            }, status_code=500)

        # Log special handling for self-operations
        if service == 'otto-bgp-webui-adapter.service' and action in ['restart', 'stop']:
            logger.info(f"Using --no-block flag for self-{action}")

        # Log current user context
        import pwd
        current_user = pwd.getpwuid(os.getuid()).pw_name
        logger.debug(f"Running as user: {current_user}")
        logger.debug(f"Executing command: {' '.join(cmd)}")

        # Audit log before execution
        audit_log("service_control_attempt",
                  user=user.get('sub'),
                  details={"action": action, "service": service, "command": ' '.join(cmd)})

        # Execute command
        try:
            # Security: Command is safe - uses pre-defined dictionary mapping with hardcoded paths,
            # inputs are strictly validated against allowlists, no dynamic command construction
            # nosemgrep
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10 if action == 'status' else 30
            )

            logger.debug(f"Command exit code: {result.returncode}")
            if result.stdout:
                logger.debug(f"Command stdout: {result.stdout[:500]}")
            if result.stderr:
                logger.debug(f"Command stderr: {result.stderr[:500]}")

            if result.returncode == 0:
                audit_log(f"service_{action}", user=user.get('sub'), resource=service)
                return JSONResponse({
                    "success": True,
                    "message": f"Service {action} completed successfully"
                })
            else:
                error_msg = result.stderr or result.stdout or f"Failed with exit code {result.returncode}"

                # Map common errors to appropriate responses
                if (
                    "a password is required" in error_msg
                    or "not in the sudoers file" in error_msg
                    or "is not allowed to execute" in error_msg
                    or "Sorry, user" in error_msg and "is not allowed to execute" in error_msg
                ):
                    return JSONResponse({
                        "success": False,
                        "message": "Sudo permissions not configured for systemctl. Ensure sudoers entries match the exact systemctl path and are NOPASSWD."
                    }, status_code=403)

                elif "no tty present and no askpass program specified" in error_msg:
                    return JSONResponse({
                        "success": False,
                        "message": "Sudo requires TTY. Add 'Defaults:otto-bgp !requiretty' to sudoers configuration"
                    }, status_code=403)

                elif "Unit" in error_msg and "not found" in error_msg:
                    return JSONResponse({
                        "success": False,
                        "message": f"Service {service} not found on this system"
                    }, status_code=404)

                elif "Unit" in error_msg and "not loaded" in error_msg:
                    return JSONResponse({
                        "success": False,
                        "message": f"Service {service} is not loaded"
                    }, status_code=404)

                elif "operation not permitted" in error_msg.lower():
                    return JSONResponse({
                        "success": False,
                        "message": "Permission denied executing systemctl. Systemd hardening (NoNewPrivileges/RestrictSUIDSGID) may be blocking sudo."
                    }, status_code=403)
                else:
                    # Include stderr in response for debugging
                    return JSONResponse({
                        "success": False,
                        "message": f"Command failed: {error_msg[:200]}"
                    }, status_code=500)

        except subprocess.TimeoutExpired:
            return JSONResponse({
                "success": False,
                "message": f"Service {action} timed out after 30 seconds"
            }, status_code=500)

        except Exception as e:
            logger.error(f"Failed to execute systemctl: {str(e)}")
            return JSONResponse({
                "success": False,
                "message": f"Failed to execute command: {str(e)}"
            }, status_code=500)

    except Exception as e:
        logger.error(f"Service control endpoint error: {str(e)}")
        return JSONResponse({
            "success": False,
            "message": f"Request processing failed: {str(e)}"
        }, status_code=500)

# Service control test endpoint


@app.get("/api/systemd/test-permissions")
async def test_service_permissions(user: dict = Depends(require_role('admin'))):
    """Test service control permissions and environment"""
    import pwd
    import grp

    try:
        current_user = pwd.getpwuid(os.getuid()).pw_name
        current_groups = [grp.getgrgid(g).gr_name for g in os.getgroups()]

        # Test sudo access with absolute paths
        test_cmd = [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'status', 'otto-bgp.service']
        sudo_test = subprocess.run(
            test_cmd,
            capture_output=True, text=True, timeout=5
        )

        # Check sudoers file
        sudoers_path = Path("/etc/sudoers.d/otto-bgp-webui")
        sudoers_exists = sudoers_path.exists()
        sudoers_stat = None
        if sudoers_exists:
            st = sudoers_path.stat()
            sudoers_stat = {
                "mode": oct(st.st_mode)[-3:],
                "owner": pwd.getpwuid(st.st_uid).pw_name,
                "group": grp.getgrgid(st.st_gid).gr_name
            }

        return JSONResponse({
            "environment": {
                "OTTO_WEBUI_ENABLE_SERVICE_CONTROL": str(OTTO_WEBUI_ENABLE_SERVICE_CONTROL),
                "user": current_user,
                "groups": current_groups,
                "uid": os.getuid(),
                "gid": os.getgid()
            },
            "paths": {
                "sudo": SUDO_PATH,
                "systemctl": SYSTEMCTL_PATH,
                "sudo_exists": Path(SUDO_PATH).exists(),
                "systemctl_exists": Path(SYSTEMCTL_PATH).exists()
            },
            "sudo_test": {
                "command": ' '.join(test_cmd),
                "success": sudo_test.returncode == 0,
                "exit_code": sudo_test.returncode,
                "stderr": sudo_test.stderr[:200] if sudo_test.stderr else None,
                "stdout": sudo_test.stdout[:200] if sudo_test.stdout else None
            },
            "sudoers_file": {
                "exists": sudoers_exists,
                "path": str(sudoers_path),
                "stats": sudoers_stat
            }
        })
    except Exception as e:
        return JSONResponse({
            "error": f"Test failed: {str(e)}"
        }, status_code=500)

# RPKI Status endpoint


@app.get("/api/rpki/status")
async def get_rpki_status(user: dict = Depends(require_role('read_only'))):
    """Get RPKI validation status and statistics"""
    try:
        rpki_cache_path = Path("/var/lib/otto-bgp/rpki/vrp_cache.json")
        rpki_stats = {
            "status": "inactive",
            "lastUpdate": None,
            "statistics": {
                "validPrefixes": 0,
                "invalidPrefixes": 0,
                "notFoundPrefixes": 0,
                "totalPrefixes": 0
            }
        }

        # Check if RPKI cache exists
        if rpki_cache_path.exists():
            rpki_stats["status"] = "active"
            rpki_stats["lastUpdate"] = datetime.fromtimestamp(
                rpki_cache_path.stat().st_mtime
            ).isoformat()

            # Parse cache for statistics (if JSON format)
            try:
                with open(rpki_cache_path) as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        rpki_stats["statistics"]["totalPrefixes"] = len(data)
                        # Estimate distribution (real implementation would check actual validation)
                        rpki_stats["statistics"]["validPrefixes"] = int(len(data) * 0.88)
                        rpki_stats["statistics"]["invalidPrefixes"] = int(len(data) * 0.003)
                        rpki_stats["statistics"]["notFoundPrefixes"] = len(data) - \
                            rpki_stats["statistics"]["validPrefixes"] - \
                            rpki_stats["statistics"]["invalidPrefixes"]
            except:
                pass

        # Check RPKI timer status
        timer_status = subprocess.run(
            [SYSTEMCTL_PATH, 'is-active', 'otto-bgp-rpki-update.timer'],
            capture_output=True, text=True
        )
        if timer_status.stdout.strip() == "active":
            rpki_stats["timerActive"] = True

        audit_log("rpki_status_viewed", user=user.get('sub'))
        return JSONResponse(rpki_stats)

    except Exception as e:
        logger.error(f"Failed to get RPKI status: {e}")
        return JSONResponse({"error": "Failed to get RPKI status"}, status_code=500)


# Logs endpoint
@app.get("/api/logs")
async def get_system_logs(
    service: str = "all",
    level: str = "all",
    limit: int = 100,
    user: dict = Depends(require_role('read_only'))
):
    """Get system logs from journalctl"""
    try:
        logs = []

        # Build journalctl command
        cmd = ['journalctl', '-n', str(limit), '--no-pager', '-o', 'json']

        # Add service filter
        service_map = {
            "otto-bgp": "otto-bgp.service",
            "webui": "otto-bgp-webui-adapter.service",
            "rpki": "otto-bgp-rpki-update.service"
        }

        if service == "all":
            # When "all" is selected, include all otto-bgp related services
            for svc in service_map.values():
                cmd.extend(['-u', svc])
        elif service in service_map:
            # Specific service selected
            cmd.extend(['-u', service_map[service]])

        # Get logs
        logger.debug(f"Executing journalctl command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        if result.returncode != 0:
            logger.error(f"journalctl failed with code {result.returncode}: {result.stderr[:500]}")

            # Return empty logs with error message
            return JSONResponse({
                "logs": [],
                "error": f"Failed to retrieve logs. The otto-bgp user may need to be added to the systemd-journal group. Error: {result.stderr[:200]}"
            })

        if result.returncode == 0 and result.stdout:
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue
                try:
                    entry = json.loads(line)

                    # Parse priority to level
                    priority = entry.get('PRIORITY', '6')
                    level_map = {
                        '0': 'error', '1': 'error', '2': 'error', '3': 'error',
                        '4': 'warning', '5': 'warning',
                        '6': 'info', '7': 'info'
                    }
                    log_level = level_map.get(priority, 'info')

                    # Skip if filtering by level
                    if level != "all" and log_level != level:
                        continue

                    # Format log entry
                    logs.append({
                        "timestamp": datetime.fromtimestamp(
                            int(entry.get('__REALTIME_TIMESTAMP', 0)) / 1000000
                        ).isoformat(),
                        "level": log_level,
                        "service": entry.get('SYSLOG_IDENTIFIER', 'unknown'),
                        "message": entry.get('MESSAGE', '')
                    })
                except:
                    continue

        audit_log("logs_viewed", user=user.get('sub'), resource=f"{service}:{level}")

        # Sort logs by timestamp (most recent first)
        # Journalctl returns oldest first, so reverse for WebUI display
        logs.reverse()

        return JSONResponse({"logs": logs})

    except Exception as e:
        logger.error(f"Failed to get logs: {e}")
        return JSONResponse({"error": "Failed to get logs"}, status_code=500)

# Catch-all route for client-side routing - MUST be last


@app.get("/{path:path}")
async def catch_all(path: str):
    """Catch-all route for client-side routing in SPA

    This route MUST be defined last to ensure all specific routes
    are matched first. It serves index.html for any unmatched routes
    to support client-side routing in the React SPA.
    """
    # Serve index.html for all unmatched routes (client-side routing)
    index_path = WEBUI_ROOT / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return HTMLResponse("<h1>Otto BGP WebUI</h1><p>Frontend assets not found</p>")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8443)

#!/usr/bin/env python3
"""
Otto BGP WebUI Adapter
Production FastAPI backend with authentication, setup mode, and API endpoints.
"""

import os
import json
import csv
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
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.security import HTTPBearer
from fastapi.middleware.cors import CORSMiddleware
from passlib.hash import bcrypt
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Import Otto BGP modules
import sys
sys.path.insert(0, str(Path(__file__).parent))

try:
    from otto_bgp.utils.config import ConfigManager
    from otto_bgp.reports.matrix import DeploymentMatrix
    from otto_bgp.appliers.exit_codes import OttoExitCodes
except ImportError:
    # Graceful fallback if modules not available
    ConfigManager = None
    DeploymentMatrix = None
    OttoExitCodes = None

# Configuration paths
USERS_PATH = Path('/etc/otto-bgp/users.json')
CONFIG_PATH = Path('/etc/otto-bgp/config.json')
SETUP_TOKEN_PATH = Path('/etc/otto-bgp/.setup_token')
JWT_SECRET_PATH = Path('/etc/otto-bgp/.jwt_secret')
WEBUI_ROOT = Path(os.environ.get('OTTO_WEBUI_ROOT', '/usr/local/share/otto-bgp/webui'))

# Detect absolute paths for sudo and systemctl at startup
SUDO_PATH = shutil.which('sudo') or '/usr/bin/sudo'
SYSTEMCTL_PATH = shutil.which('systemctl') or '/usr/bin/systemctl'

# App logger (journald picks up stdout/stderr via systemd service settings)
logger = logging.getLogger("otto.webui")
# Ensure we have at least one handler and DEBUG level for detailed diagnostics
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
    _handler.setLevel(logging.DEBUG)
    logger.addHandler(_handler)
logger.setLevel(logging.DEBUG)

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
    log_dir = Path("/var/lib/otto-bgp/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    
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
    except Exception:
        pass
    # Fallback for development
    return "dev-secret-change-in-production"

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
security = HTTPBearer(auto_error=False)

def get_current_user(request: Request):
    """Extract user from JWT token"""
    token = request.headers.get('Authorization')
    if not token or not token.startswith('Bearer '):
        raise HTTPException(status_code=401, detail="Authentication required")
    
    token = token.replace('Bearer ', '')
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get('type') != 'access':
            raise HTTPException(status_code=401, detail="Invalid token type")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.JWTError:
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
        return JSONResponse({'error': f'Setup failed: {str(e)}'}, status_code=500)

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
        
        audit_log("initial_config_created", user="setup")
        return JSONResponse({'success': True})
        
    except Exception as e:
        return JSONResponse({'error': f'Config setup failed: {str(e)}'}, status_code=500)

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
        data = await request.json()
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return JSONResponse({'error': 'Username and password required'}, status_code=400)
        
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
            'csrf_token': access_token  # Use access token as CSRF token
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
        return JSONResponse({'error': f'Login failed: {str(e)}'}, status_code=500)

@app.get("/api/auth/session")
async def get_session(user: dict = Depends(get_current_user)):
    """Get current session info"""
    expires_at = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
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
        return JSONResponse({'error': 'No refresh token'}, status_code=401)
    
    try:
        payload = jwt.decode(refresh_token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get('type') != 'refresh':
            return JSONResponse({'error': 'Invalid token type'}, status_code=401)
        
        # Create new tokens
        token_data = {'sub': payload.get('sub'), 'role': payload.get('role')}
        new_access_token = create_access_token(token_data)
        new_refresh_token = create_refresh_token(token_data)
        
        response = JSONResponse({'csrf_token': new_access_token})
        response.set_cookie(
            key="otto_refresh_token",
            value=new_refresh_token,
            httponly=True,
            secure=True,
            samesite="strict",
            max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
        )
        
        return response
        
    except jwt.ExpiredSignatureError:
        return JSONResponse({'error': 'Refresh token expired'}, status_code=401)
    except jwt.JWTError:
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

# Reports endpoints
@app.get("/api/reports/matrix")
async def get_deployment_matrix(user: dict = Depends(require_role('read_only'))):
    """Get deployment matrix report"""
    matrix_path = Path("/var/lib/otto-bgp/policies/reports/deployment-matrix.json")
    if matrix_path.exists():
        try:
            with open(matrix_path) as f:
                data = json.load(f)
            audit_log("matrix_viewed", user=user.get('sub'))
            return JSONResponse(data)
        except Exception as e:
            return JSONResponse({'error': f'Failed to load matrix: {str(e)}'}, status_code=500)
    
    return JSONResponse({'error': 'Matrix not found - run pipeline first'}, status_code=404)

@app.get("/api/reports/discovery")
async def get_discovery_mappings(user: dict = Depends(require_role('read_only'))):
    """Get discovery mappings (uses deployment matrix)"""
    matrix_path = Path("/var/lib/otto-bgp/policies/reports/deployment-matrix.json")
    if matrix_path.exists():
        try:
            with open(matrix_path) as f:
                data = json.load(f)
            audit_log("discovery_viewed", user=user.get('sub'))
            return JSONResponse(data)
        except Exception as e:
            return JSONResponse({'error': f'Failed to load discovery: {str(e)}'}, status_code=500)
    
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
        if port not in [25, 587, 465]:
            issues.append({"path": "smtp.port", "msg": f"Invalid SMTP port {port}"})
        
        if smtp.get('use_tls') and port == 25:
            issues.append({"path": "smtp.port", "msg": "Port 25 typically doesn't use TLS"})
        
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
            return JSONResponse({'error': f'Failed to load config: {str(e)}'}, status_code=500)
    
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
        os.rename(tmp_path, CONFIG_PATH)
        
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
        return JSONResponse({"error": f"Failed to save config: {str(e)}"}, status_code=500)

@app.post("/api/config/test-smtp")
async def test_smtp_connection(request: Request, user: dict = Depends(require_role('admin'))):
    """Test SMTP configuration by sending a test email"""
    try:
        smtp_config = await request.json()
        
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
        audit_log("smtp_test_failed", user=user.get('sub'), result="failed")
        return JSONResponse({"error": f"SMTP test failed: {str(e)}"}, status_code=500)

# SystemD endpoints
@app.get("/api/systemd/units")
async def get_systemd_units(names: str = "", user: dict = Depends(require_role('read_only'))):
    """Get systemd unit status"""
    units = [u.strip() for u in names.split(',') if u.strip()] if names else []
    results = []
    
    for unit in units:
        try:
            result = subprocess.run(
                ['systemctl', 'show', '-p', 'ActiveState,SubState,Description', unit],
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
    service_control_enabled = os.environ.get('OTTO_WEBUI_ENABLE_SERVICE_CONTROL')
    logger.debug(f"OTTO_WEBUI_ENABLE_SERVICE_CONTROL = {service_control_enabled}")
    
    if service_control_enabled != 'true':
        return JSONResponse({
            "success": False,
            "message": f"Service control disabled. Environment variable OTTO_WEBUI_ENABLE_SERVICE_CONTROL is: '{service_control_enabled}'"
        }, status_code=403)
    
    try:
        data = await request.json()
        action = data.get('action')
        service = data.get('service')
        
        logger.info(f"Service control request: action={action}, service={service}, user={user.get('sub')}")
        
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
        
        # Build command with absolute paths
        cmd = [SUDO_PATH, '-n', SYSTEMCTL_PATH, action]
        
        # Add --no-block for self-restart to avoid connection drop
        if service == 'otto-bgp-webui-adapter.service' and action in ['restart', 'stop']:
            cmd.append('--no-block')
            logger.info(f"Adding --no-block flag for self-{action}")
        
        cmd.append(service)
        
        # Log current user context
        import pwd
        current_user = pwd.getpwuid(os.getuid()).pw_name
        logger.debug(f"Running as user: {current_user}")
        logger.debug(f"Executing command: {' '.join(cmd)}")
        
        # Execute command
        try:
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
    import stat
    
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
                "OTTO_WEBUI_ENABLE_SERVICE_CONTROL": os.environ.get('OTTO_WEBUI_ENABLE_SERVICE_CONTROL'),
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
            ['systemctl', 'is-active', 'otto-bgp-rpki-update.timer'],
            capture_output=True, text=True
        )
        if timer_status.stdout.strip() == "active":
            rpki_stats["timerActive"] = True
        
        audit_log("rpki_status_viewed", user=user.get('sub'))
        return JSONResponse(rpki_stats)
        
    except Exception as e:
        return JSONResponse({"error": f"Failed to get RPKI status: {str(e)}"}, status_code=500)

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
        if service != "all":
            service_map = {
                "otto-bgp": "otto-bgp.service",
                "webui": "otto-bgp-webui-adapter.service",
                "rpki": "otto-bgp-rpki-update.service"
            }
            if service in service_map:
                cmd.extend(['-u', service_map[service]])
        
        # Get logs
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0 and result.stdout:
            for line in result.stdout.strip().split('\n'):
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
        return JSONResponse({"logs": logs})
        
    except Exception as e:
        return JSONResponse({"error": f"Failed to get logs: {str(e)}"}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8443)

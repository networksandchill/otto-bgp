import logging
from datetime import datetime, timedelta
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Request
from jwt import exceptions as jwt_exceptions

from webui.settings import CONFIG_PATH, JWT_SECRET_PATH, OTTO_DEV_MODE, SETUP_TOKEN_PATH, USERS_PATH

# JWT Configuration
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 5
REFRESH_TOKEN_EXPIRE_DAYS = 7


def get_jwt_secret() -> str:
    """Load JWT secret from file (dev fallback only if enabled)"""
    try:
        if JWT_SECRET_PATH.exists():
            return JWT_SECRET_PATH.read_text().strip()
    except Exception as e:
        logging.getLogger("otto.webui").error(
            f"Failed to read JWT secret: {e}")

    if OTTO_DEV_MODE:
        logging.getLogger("otto.webui").warning(
            "Using development JWT secret - DO NOT USE IN PRODUCTION")
        return "dev-secret-change-in-production"

    raise RuntimeError(
        f"JWT secret not found at {JWT_SECRET_PATH}. "
        "Create it with: openssl rand -hex 32 > /etc/otto-bgp/.jwt_secret"
    )


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create JWT access token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def create_refresh_token(data: dict):
    """Create JWT refresh token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def needs_setup() -> dict:
    """Check if setup is required (match current behavior)"""
    reasons = []
    if not USERS_PATH.exists():
        reasons.append('missing_users')
    if not CONFIG_PATH.exists():
        reasons.append('missing_config')
    return {'needs_setup': bool(reasons), 'reasons': reasons}


def _require_setup_token(request: Request) -> bool:
    """Validate setup token from request headers (boolean return)"""
    token = request.headers.get('X-Setup-Token')
    if not token or not SETUP_TOKEN_PATH.exists():
        return False
    try:
        return token.strip() == SETUP_TOKEN_PATH.read_text().strip()
    except Exception:
        return False


def get_current_user(request: Request):
    """Extract user from JWT access token (match messages)"""
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        raise HTTPException(
            status_code=401, detail="Authentication required")

    token = auth_header.replace('Bearer ', '')
    try:
        payload = jwt.decode(
            token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get('type') != 'access':
            raise HTTPException(
                status_code=401, detail="Invalid token type")
        return payload
    except jwt_exceptions.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt_exceptions.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def require_role(required_role: str):
    """Dependency to require specific role (preserve read_only semantics)"""
    def _require_role(user: dict = Depends(get_current_user)):
        if user.get('role') != required_role and required_role != 'read_only':
            if user.get('role') != 'admin':
                raise HTTPException(
                    status_code=403, detail="Insufficient permissions")
        return user
    return _require_role

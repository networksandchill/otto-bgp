from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from passlib.hash import bcrypt
import jwt
from jwt import exceptions as jwt_exceptions
from webui.core.security import (
    get_current_user, create_access_token, create_refresh_token,
    get_jwt_secret, JWT_ALGORITHM, REFRESH_TOKEN_EXPIRE_DAYS
)
from webui.core.audit import audit_log
from webui.core.users import get_user
import logging

logger = logging.getLogger("otto.webui")
router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(request: Request, data: LoginRequest):
    """User login with JWT tokens"""
    try:
        username = data.username
        password = data.password

        # Get user and verify password
        user = get_user(username)
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


@router.get("/session")
async def get_session(user: dict = Depends(get_current_user)):
    """Get current session info"""
    # Derive expires_at from token's exp claim
    expires_at = datetime.utcfromtimestamp(user.get('exp', 0))
    return JSONResponse({
        'user': user.get('sub'),
        'role': user.get('role'),
        'expires_at': expires_at.isoformat()
    })


@router.post("/refresh")
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


@router.post("/logout")
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
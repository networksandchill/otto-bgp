import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from passlib.hash import bcrypt

from webui.core.audit import audit_log
from webui.core.fileops import atomic_write_json
from webui.core.security import get_current_user
from webui.settings import USERS_PATH

logger = logging.getLogger("otto.webui")
router = APIRouter()


@router.get("/")
async def get_profile(user: dict = Depends(get_current_user)):
    """Get current user's profile"""
    try:
        username = user.get('sub')

        # Load users file
        if not USERS_PATH.exists():
            raise HTTPException(status_code=404, detail="User not found")

        with open(USERS_PATH) as f:
            users_data = json.load(f)

        # Find user
        for u in users_data.get('users', []):
            if u.get('username') == username:
                return JSONResponse({
                    'username': u.get('username'),
                    'email': u.get('email', ''),
                    'role': u.get('role'),
                    'created_at': u.get('created_at')
                })

        raise HTTPException(status_code=404, detail="User not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to get profile")


@router.put("/")
async def update_profile(request: Request, user: dict = Depends(get_current_user)):
    """Update current user's profile (email and/or password)"""
    try:
        data = await request.json()
        username = user.get('sub')

        # Load users file
        if not USERS_PATH.exists():
            raise HTTPException(status_code=404, detail="User not found")

        with open(USERS_PATH) as f:
            users_data = json.load(f)

        # Find and update user
        user_found = False
        for u in users_data.get('users', []):
            if u.get('username') == username:
                user_found = True

                # Verify current password if changing password
                if 'new_password' in data:
                    if not data.get('current_password'):
                        raise HTTPException(status_code=400, detail="Current password required")

                    if not bcrypt.verify(data['current_password'], u['password_hash']):
                        raise HTTPException(status_code=400, detail="Current password is incorrect")

                    # Update password
                    u['password_hash'] = bcrypt.hash(data['new_password'])
                    audit_log("password_changed", user=username)

                # Update email if provided
                if 'email' in data:
                    u['email'] = data['email']
                    audit_log("email_updated", user=username, resource=data['email'])

                break

        if not user_found:
            raise HTTPException(status_code=404, detail="User not found")

        # Save updated users file atomically
        atomic_write_json(USERS_PATH, users_data, mode=0o600)

        return JSONResponse({'success': True})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to update profile")
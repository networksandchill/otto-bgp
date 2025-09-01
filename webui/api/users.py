from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from webui.core.security import require_role
from webui.core.users import (
    load_users, create_user, update_user, delete_user
)
from webui.core.audit import audit_log


class UserCreate(BaseModel):
    username: str
    password: str
    email: Optional[str] = ""
    role: str = "read_only"


class UserUpdate(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None


router = APIRouter()


@router.get("/")
async def get_users(user: dict = Depends(require_role("admin"))):
    """Get all users (without password hashes)"""
    users_data = load_users()
    users = []
    for u in users_data.get("users", []):
        users.append({k: v for k, v in u.items() if k != "password_hash"})
    audit_log("list_users", user=user.get("sub"))
    return {"users": users}


@router.post("/")
async def create_user_endpoint(
    user_data: UserCreate,
    user: dict = Depends(require_role("admin"))
):
    """Create new user"""
    try:
        new_user = create_user(user_data.username, user_data.password, user_data.role, user_data.email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    audit_log("user_created", user=user.get("sub"), target_user=user_data.username)
    return new_user


@router.put("/{username}")
async def update_user_endpoint(
    username: str,
    updates: UserUpdate,
    user: dict = Depends(require_role("admin"))
):
    """Update user"""
    update_dict = {k: v for k, v in updates.dict().items() if v is not None}
    try:
        updated = update_user(username, update_dict)
    except (ValueError, PermissionError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    audit_log("user_updated", user=user.get("sub"), target_user=username)
    return updated


@router.delete("/{username}")
async def delete_user_endpoint(
    username: str,
    user: dict = Depends(require_role("admin"))
):
    """Delete user"""
    # Prevent self-deletion at API layer
    if username == user.get("sub"):
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    try:
        deleted = delete_user(username)
    except PermissionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail="User not found")
    audit_log("user_deleted", user=user.get("sub"), target_user=username)
    return {"success": True}

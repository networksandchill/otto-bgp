import json
import secrets
from datetime import datetime
from typing import Dict, Optional

from passlib.hash import bcrypt

from webui.core.fileops import atomic_write_json
from webui.settings import USERS_PATH


def generate_password() -> str:
    """Generate secure random password"""
    return secrets.token_urlsafe(16)


def load_users() -> Dict:
    """Load users from JSON file"""
    if not USERS_PATH.exists():
        return {"users": []}
    with open(USERS_PATH) as f:
        return json.load(f)


def save_users(users_data: Dict):
    """Save users to JSON file atomically with 0600 perms"""
    atomic_write_json(USERS_PATH, users_data, mode=0o600)


def get_user(username: str) -> Optional[Dict]:
    """Get user by username"""
    users_data = load_users()
    for user in users_data.get("users", []):
        if user.get("username") == username:
            return user
    return None


def create_user(username: str, password: str, role: str = "read_only", email: str = "") -> Dict:
    """Create new user with bcrypt password hash"""
    users_data = load_users()
    # Prevent duplicates
    for u in users_data.get("users", []):
        if u.get("username") == username:
            raise ValueError("Username already exists")
    new_user = {
        "username": username,
        "email": email,
        "password_hash": bcrypt.hash(password),
        "role": role,
        "created_at": datetime.utcnow().isoformat()
    }
    users_data.setdefault("users", []).append(new_user)
    save_users(users_data)
    # Do not return password_hash to callers
    return {k: v for k, v in new_user.items() if k != "password_hash"}


def update_user(username: str, updates: Dict) -> Optional[Dict]:
    """Update existing user, enforcing admin safety constraints"""
    users_data = load_users()
    user_index = -1
    for i, u in enumerate(users_data.get("users", [])):
        if u.get("username") == username:
            user_index = i
            break
    if user_index == -1:
        return None

    # Role update validation (prevent removing last admin)
    if "role" in updates:
        new_role = updates["role"]
        if new_role not in ["admin", "operator", "read_only"]:
            raise ValueError("Invalid role")
        if users_data["users"][user_index].get("role") == "admin" and new_role != "admin":
            admin_count = sum(1 for u in users_data["users"] if u.get("role") == "admin")
            if admin_count == 1:
                raise PermissionError("Cannot remove last admin user")

    if "password" in updates and updates["password"]:
        users_data["users"][user_index]["password_hash"] = bcrypt.hash(updates.pop("password"))
    if "email" in updates:
        users_data["users"][user_index]["email"] = updates["email"]
    if "role" in updates:
        users_data["users"][user_index]["role"] = updates["role"]

    save_users(users_data)
    redacted = users_data["users"][user_index].copy()
    redacted.pop("password_hash", None)
    return redacted


def delete_user(username: str) -> bool:
    """Delete user, disallow removing last admin"""
    users_data = load_users()
    user_index = -1
    user_role = None
    for i, u in enumerate(users_data.get("users", [])):
        if u.get("username") == username:
            user_index = i
            user_role = u.get("role")
            break
    if user_index == -1:
        return False
    if user_role == "admin":
        admin_count = sum(1 for u in users_data["users"] if u.get("role") == "admin")
        if admin_count == 1:
            raise PermissionError("Cannot delete last admin user")
    del users_data["users"][user_index]
    save_users(users_data)
    return True


def validate_credentials(username: str, password: str) -> Optional[Dict]:
    """Validate user credentials via bcrypt"""
    user = get_user(username)
    if user and bcrypt.verify(password, user.get("password_hash", "")):
        redacted = user.copy()
        redacted.pop("password_hash", None)
        return redacted
    return None

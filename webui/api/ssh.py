"""SSH API endpoints for Otto BGP WebUI"""
from pathlib import Path
from time import time
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from webui.core.security import require_role
from webui.core.audit import audit_log
from webui.core.ssh_keys import (
    generate_keypair, get_public_key, get_fingerprints,
    upload_private_key, read_known_hosts, add_known_host,
    fetch_host_key, remove_known_host
)
from webui.settings import DATA_DIR

router = APIRouter()

# Rate limiting storage
RATE_LIMITS = {}

# Default paths
DEFAULT_KEY_PATH = DATA_DIR / 'ssh-keys' / 'id_ed25519'
DEFAULT_KNOWN_HOSTS = DATA_DIR / 'ssh-keys' / 'known_hosts'


class GenerateKeyRequest(BaseModel):
    key_type: str = 'ed25519'
    path: Optional[str] = None


class AddKnownHostRequest(BaseModel):
    entry: str


class FetchHostKeyRequest(BaseModel):
    host: str
    port: int = 22


class RemoveKnownHostRequest(BaseModel):
    line_number: int


@router.post('/generate-key')
async def generate_key(
    request: GenerateKeyRequest,
    user: dict = Depends(require_role('admin'))
):
    """Generate new SSH keypair with rate limiting"""
    # Rate limiting - 1 key per minute per user
    key = f"keygen:{user.get('sub')}"
    now = time()
    last = RATE_LIMITS.get(key, 0)

    if now - last < 60:
        raise HTTPException(
            status_code=429,
            detail="Too many key generation requests; try again later"
        )

    # Validate key type
    if request.key_type not in ['rsa', 'ed25519', 'ecdsa']:
        raise HTTPException(
            status_code=400,
            detail="Invalid key type. Must be rsa, ed25519, or ecdsa"
        )

    # Determine path
    key_path = Path(request.path) if request.path else DEFAULT_KEY_PATH

    # Generate keypair
    success, message = generate_keypair(key_path, request.key_type)

    if success:
        RATE_LIMITS[key] = now
        audit_log(
            'ssh_key_generated',
            user=user.get('sub'),
            key_type=request.key_type,
            path=str(key_path)
        )

        # Get public key and fingerprints
        pubkey = get_public_key(key_path)
        fingerprints = get_fingerprints(pubkey) if pubkey else {}

        return {
            "success": True,
            "message": message,
            "public_key": pubkey,
            "fingerprints": fingerprints
        }
    else:
        raise HTTPException(status_code=500, detail=message)


@router.get('/public-key')
async def get_ssh_public_key(
    path: Optional[str] = None,
    user: dict = Depends(require_role('read_only'))
):
    """Get public key and fingerprints"""
    key_path = Path(path) if path else DEFAULT_KEY_PATH

    if not key_path.exists():
        raise HTTPException(
            status_code=404,
            detail="SSH key not found at specified path"
        )

    pubkey = get_public_key(key_path)
    if not pubkey:
        raise HTTPException(
            status_code=404,
            detail="Public key not found"
        )

    fingerprints = get_fingerprints(pubkey)

    audit_log('ssh_public_key_viewed', user=user.get('sub'))

    return {
        "public_key": pubkey,
        "fingerprints": fingerprints,
        "path": str(key_path)
    }


@router.post('/upload-key')
async def upload_key(
    file: UploadFile = File(...),
    path: Optional[str] = None,
    user: dict = Depends(require_role('admin'))
):
    """Upload private SSH key with rate limiting"""
    # Rate limiting - 1 upload per minute per user
    key = f"keyupload:{user.get('sub')}"
    now = time()
    last = RATE_LIMITS.get(key, 0)

    if now - last < 60:
        raise HTTPException(
            status_code=429,
            detail="Too many key upload requests; try again later"
        )

    # Read file content
    content = await file.read()

    # Determine path
    key_path = Path(path) if path else DEFAULT_KEY_PATH

    # Upload and validate
    success, message = upload_private_key(content, key_path)

    if success:
        RATE_LIMITS[key] = now
        audit_log(
            'ssh_key_uploaded',
            user=user.get('sub'),
            path=str(key_path)
        )

        # Get public key and fingerprints
        pubkey = get_public_key(key_path)
        fingerprints = get_fingerprints(pubkey) if pubkey else {}

        return {
            "success": True,
            "message": message,
            "public_key": pubkey,
            "fingerprints": fingerprints
        }
    else:
        raise HTTPException(status_code=400, detail=message)


@router.get('/known-hosts')
async def get_known_hosts(
    path: Optional[str] = None,
    user: dict = Depends(require_role('read_only'))
):
    """Get known hosts entries"""
    hosts_path = Path(path) if path else DEFAULT_KNOWN_HOSTS

    entries = read_known_hosts(hosts_path)

    audit_log('ssh_known_hosts_viewed', user=user.get('sub'))

    return {
        "entries": entries,
        "path": str(hosts_path)
    }


@router.post('/known-hosts/add')
async def add_host(
    request: AddKnownHostRequest,
    path: Optional[str] = None,
    user: dict = Depends(require_role('admin'))
):
    """Add entry to known_hosts"""
    hosts_path = Path(path) if path else DEFAULT_KNOWN_HOSTS

    success, message = add_known_host(hosts_path, request.entry)

    if success:
        audit_log(
            'ssh_known_host_added',
            user=user.get('sub'),
            entry=request.entry[:100]  # Log first 100 chars
        )
        return {"success": True, "message": message}
    else:
        raise HTTPException(status_code=400, detail=message)


@router.post('/known-hosts/fetch')
async def fetch_host(
    request: FetchHostKeyRequest,
    user: dict = Depends(require_role('admin'))
):
    """Fetch SSH host key with timeout"""
    # Validate port
    if request.port < 1 or request.port > 65535:
        raise HTTPException(
            status_code=400,
            detail="Invalid port number"
        )

    success, key_entry, message = fetch_host_key(
        request.host,
        request.port
    )

    if success:
        audit_log(
            'ssh_host_key_fetched',
            user=user.get('sub'),
            host=request.host,
            port=request.port
        )

        # Parse key for fingerprint
        parts = key_entry.split(None, 2)
        if len(parts) >= 3:
            import base64
            import hashlib
            try:
                key_data = base64.b64decode(parts[2].split()[0])
                sha256_hash = hashlib.sha256(key_data).digest()
                fingerprint = base64.b64encode(sha256_hash).decode(
                    'ascii').rstrip('=')
                fingerprint = f'SHA256:{fingerprint}'
            except Exception:
                fingerprint = 'unknown'
        else:
            fingerprint = 'unknown'

        return {
            "success": True,
            "key_entry": key_entry,
            "fingerprint": fingerprint,
            "message": message
        }
    else:
        raise HTTPException(status_code=400, detail=message)


@router.delete('/known-hosts/remove')
async def remove_host(
    request: RemoveKnownHostRequest,
    path: Optional[str] = None,
    user: dict = Depends(require_role('admin'))
):
    """Remove entry from known_hosts"""
    hosts_path = Path(path) if path else DEFAULT_KNOWN_HOSTS

    success, message = remove_known_host(hosts_path, request.line_number)

    if success:
        audit_log(
            'ssh_known_host_removed',
            user=user.get('sub'),
            line=request.line_number
        )
        return {"success": True, "message": message}
    else:
        raise HTTPException(status_code=400, detail=message)

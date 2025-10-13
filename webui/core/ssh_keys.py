"""SSH key management for Otto BGP WebUI"""
import base64
import hashlib
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Rate limiting storage
RATE_LIMITS: Dict[str, float] = {}


def generate_keypair(path: Path,
                     key_type: str = 'ed25519') -> Tuple[bool, str]:
    """
    Generate SSH keypair at specified path

    Args:
        path: Path where private key will be stored
        key_type: Key type (rsa, ed25519, ecdsa)

    Returns:
        (success, message) tuple
    """
    try:
        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        # Remove existing key if present
        if path.exists():
            path.unlink()
        if path.with_suffix('.pub').exists():
            path.with_suffix('.pub').unlink()

        # Generate new keypair
        cmd = [
            'ssh-keygen',
            '-t', key_type,
            '-f', str(path),
            '-N', '',  # No passphrase
            '-C', f'otto-bgp@{os.uname().nodename}'
        ]

        if key_type == 'rsa':
            cmd.extend(['-b', '4096'])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            # Set proper permissions
            os.chmod(path, 0o600)
            os.chmod(path.with_suffix('.pub'), 0o644)
            return True, f"Generated {key_type} keypair successfully"
        else:
            return False, f"Failed to generate keypair: {result.stderr}"

    except subprocess.TimeoutExpired:
        return False, "Key generation timed out"
    except Exception as e:
        return False, f"Error generating keypair: {str(e)}"


def get_public_key(path: Path) -> Optional[str]:
    """
    Read public key from private key path

    Args:
        path: Path to private key

    Returns:
        Public key content or None if not found
    """
    pub_path = path.with_suffix('.pub')
    if pub_path.exists():
        return pub_path.read_text().strip()
    return None


def get_fingerprints(pubkey: str) -> Dict[str, str]:
    """
    Calculate SSH key fingerprints

    Args:
        pubkey: Public key content

    Returns:
        Dictionary with sha256 and md5 fingerprints
    """
    try:
        # Parse the public key
        parts = pubkey.split()
        if len(parts) < 2:
            return {}

        key_data = base64.b64decode(parts[1])

        # Calculate SHA256
        sha256_hash = hashlib.sha256(key_data).digest()
        sha256_b64 = base64.b64encode(sha256_hash).decode('ascii').rstrip('=')

        # Calculate MD5
        md5_hash = hashlib.md5(key_data).digest()
        md5_hex = ':'.join(f'{b:02x}' for b in md5_hash)

        return {
            'sha256': f'SHA256:{sha256_b64}',
            'md5': f'MD5:{md5_hex}'
        }
    except Exception:
        return {}


def upload_private_key(content: bytes, path: Path) -> Tuple[bool, str]:
    """
    Upload and validate private key

    Args:
        content: Private key content
        path: Path where key will be stored

    Returns:
        (success, message) tuple
    """
    try:
        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        # Write to temporary file first
        with tempfile.NamedTemporaryFile(
            mode='wb',
            dir=path.parent,
            delete=False
        ) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        # Validate key format
        result = subprocess.run(
            ['ssh-keygen', '-y', '-f', str(tmp_path)],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode != 0:
            tmp_path.unlink()
            return False, "Invalid private key format"

        # Extract public key and save it
        pub_key = result.stdout.strip()
        pub_path = path.with_suffix('.pub')
        pub_path.write_text(pub_key + '\n')

        # Move validated key to final location
        tmp_path.rename(path)
        os.chmod(path, 0o600)
        os.chmod(pub_path, 0o644)

        return True, "Private key uploaded successfully"

    except subprocess.TimeoutExpired:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()
        return False, "Key validation timed out"
    except Exception as e:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()
        return False, f"Error uploading key: {str(e)}"


def read_known_hosts(path: Path) -> List[Dict[str, str]]:
    """
    Read and parse SSH known_hosts file

    Args:
        path: Path to known_hosts file

    Returns:
        List of parsed known host entries
    """
    entries = []

    if not path.exists():
        return entries

    try:
        with open(path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                parts = line.split(None, 2)
                if len(parts) >= 3:
                    host, key_type, key = parts[0], parts[1], parts[2]

                    # Calculate fingerprint
                    try:
                        key_data = base64.b64decode(key.split()[0])
                        sha256_hash = hashlib.sha256(key_data).digest()
                        fingerprint = base64.b64encode(sha256_hash).decode(
                            'ascii').rstrip('=')
                    except Exception:
                        fingerprint = 'unknown'

                    entries.append({
                        'line': line_num,
                        'host': host,
                        'key_type': key_type,
                        'fingerprint': f'SHA256:{fingerprint}',
                        'raw': line
                    })
    except Exception:
        pass

    return entries


def add_known_host(path: Path, entry: str) -> Tuple[bool, str]:
    """
    Add entry to known_hosts file

    Args:
        path: Path to known_hosts file
        entry: Host key entry to add

    Returns:
        (success, message) tuple
    """
    try:
        # Validate entry format
        parts = entry.strip().split(None, 2)
        if len(parts) < 3:
            return False, "Invalid host key format"

        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        # Check if host already exists
        existing = read_known_hosts(path)
        host = parts[0]
        for e in existing:
            if e['host'] == host:
                return False, f"Host {host} already exists in known_hosts"

        # Append to file
        with open(path, 'a') as f:
            f.write(entry.strip() + '\n')

        return True, f"Added {host} to known_hosts"

    except Exception as e:
        return False, f"Error adding host: {str(e)}"


def fetch_host_key(host: str, port: int = 22) -> Tuple[bool, str, str]:
    """
    Fetch SSH host key using ssh-keyscan

    Args:
        host: Hostname or IP address
        port: SSH port

    Returns:
        (success, key_entry, message) tuple
    """
    try:
        cmd = [
            'ssh-keyscan',
            '-T', '5',  # 5 second timeout
            '-p', str(port),
            host
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0 and result.stdout:
            # Parse the output for valid keys
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if not line.startswith('#') and line.strip():
                    return True, line.strip(), f"Fetched key for {host}"

            return False, '', f"No valid keys found for {host}"
        else:
            error_msg = result.stderr or "Failed to fetch host key"
            return False, '', error_msg

    except subprocess.TimeoutExpired:
        return False, '', f"Timeout fetching key for {host}"
    except Exception as e:
        return False, '', f"Error fetching host key: {str(e)}"


def remove_known_host(path: Path, line_num: int) -> Tuple[bool, str]:
    """
    Remove entry from known_hosts by line number

    Args:
        path: Path to known_hosts file
        line_num: Line number to remove (1-based)

    Returns:
        (success, message) tuple
    """
    try:
        if not path.exists():
            return False, "known_hosts file not found"

        lines = path.read_text().splitlines()

        if line_num < 1 or line_num > len(lines):
            return False, "Invalid line number"

        # Remove the line (convert to 0-based index)
        removed_line = lines[line_num - 1]
        del lines[line_num - 1]

        # Write back
        path.write_text('\n'.join(lines) + '\n' if lines else '')

        # Extract host from removed line
        host = removed_line.split()[0] if removed_line else 'unknown'
        return True, f"Removed {host} from known_hosts"

    except Exception as e:
        return False, f"Error removing host: {str(e)}"

import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends

from webui.core.audit import audit_log
from webui.core.rpki import RPKI_CACHE_PATH, get_rpki_status
from webui.core.security import require_role
from webui.settings import DATA_DIR

router = APIRouter()


@router.get("/status")
async def rpki_status(user: dict = Depends(require_role("read_only"))):
    data = get_rpki_status()
    audit_log("rpki_status_viewed", user=user.get("sub"))
    return data


@router.post("/refresh")
async def refresh_cache(user: dict = Depends(require_role("admin"))):
    """Trigger a one-shot VRP cache refresh via systemd or rpki-client."""
    attempted = False
    ok = False
    try:
        import subprocess
        result = subprocess.run(
            ["/usr/bin/systemctl", "start", "otto-bgp-rpki-update.service"],
            capture_output=True, text=True
        )
        attempted = True
        ok = (result.returncode == 0)
    except Exception:
        ok = False
    if not ok:
        try:
            import shutil
            import subprocess
            if shutil.which("rpki-client"):
                result = subprocess.run(
                    ["rpki-client", "-j", "-o", str(RPKI_CACHE_PATH)],
                    capture_output=True, text=True
                )
                attempted = True
                ok = (result.returncode == 0)
        except Exception:
            ok = False
    audit_log('rpki_cache_refresh', user=user.get('sub'))
    return {"attempted": attempted, "ok": ok}


@router.post("/validate-cache")
async def validate_cache(user: dict = Depends(require_role("admin"))):
    """Validate RPKI cache freshness and structure"""
    issues = []
    is_stale = True  # Default to stale if no cache

    # Check if cache file exists
    if not RPKI_CACHE_PATH.exists():
        issues.append('VRP cache file not found')
    else:
        try:
            # Check if cache is valid JSON
            with open(RPKI_CACHE_PATH, 'r') as f:
                data = json.load(f)
            
            # Check if it's a list
            if not isinstance(data, list):
                issues.append('VRP cache is not a list')
            elif len(data) == 0:
                issues.append('VRP cache is empty')
            else:
                # Check cache age
                cache_stat = RPKI_CACHE_PATH.stat()
                cache_age = datetime.now() - datetime.fromtimestamp(
                    cache_stat.st_mtime
                )
                # Replace hardcoded 48h by reading config if available
                is_stale = cache_age > timedelta(hours=48)
                try:
                    from otto_bgp.utils.config import get_config_manager
                    _cfg = get_config_manager().get_config()
                    _max_age_h = getattr(
                        getattr(_cfg, 'rpki', None), 'max_vrp_age_hours', 48
                    )
                    is_stale = cache_age > timedelta(hours=_max_age_h)
                except Exception:
                    pass
                if is_stale:
                    issues.append(
                        f'VRP cache is stale '
                        f'({int(cache_age.total_seconds() / 3600)} hours old)'
                    )
                
                # Check for required fields in first entry
                if data:
                    sample = data[0]
                    required_fields = ['prefix', 'asn', 'maxLength']
                    missing = [
                        f for f in required_fields if f not in sample
                    ]
                    if missing:
                        issues.append(
                            f'Missing required fields: {", ".join(missing)}'
                        )
        
        except json.JSONDecodeError as e:
            issues.append(f'Invalid JSON in cache file: {str(e)}')
        except Exception as e:
            issues.append(f'Error reading cache: {str(e)}')
    
    # Check CSV cache if exists
    csv_cache = DATA_DIR / 'rpki' / 'vrp_cache.csv'
    if csv_cache.exists():
        try:
            with open(csv_cache, 'r') as f:
                first_line = f.readline().strip()
                if not first_line.startswith('URI,ASN,IP Prefix,Max Length'):
                    issues.append('CSV cache has invalid header format')
        except Exception:
            pass  # CSV is optional
    
    audit_log('rpki_cache_validated', user=user.get('sub'))

    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "cache_path": str(RPKI_CACHE_PATH),
        "cache_exists": RPKI_CACHE_PATH.exists(),
        "stale": is_stale
    }

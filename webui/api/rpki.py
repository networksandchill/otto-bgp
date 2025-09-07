import json
from pathlib import Path
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from webui.core.security import require_role
from webui.core.rpki import get_rpki_status, RPKI_CACHE_PATH
from webui.core.audit import audit_log
from webui.settings import DATA_DIR

router = APIRouter()


@router.get("/status")
async def rpki_status(user: dict = Depends(require_role("read_only"))):
    data = get_rpki_status()
    audit_log("rpki_status_viewed", user=user.get("sub"))
    return data


@router.post("/validate-cache")
async def validate_cache(user: dict = Depends(require_role("admin"))):
    """Validate RPKI cache freshness and structure"""
    issues = []
    
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
                if cache_age > timedelta(hours=48):
                    issues.append(
                        f'VRP cache is stale ({int(cache_age.total_seconds() / 3600)} hours old)'
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
        "cache_exists": RPKI_CACHE_PATH.exists()
    }

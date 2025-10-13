import json
from datetime import datetime

from fastapi import APIRouter, Depends

from webui.core.audit import audit_log
from webui.core.security import require_role
from webui.settings import DATA_DIR

router = APIRouter()


@router.get("/matrix")
async def get_deployment_matrix(user: dict = Depends(require_role("read_only"))):
    matrix_path = DATA_DIR / "policies/reports/deployment-matrix.json"
    if matrix_path.exists():
        data = json.loads(matrix_path.read_text())
        audit_log("matrix_viewed", user=user.get('sub'))
        return data
    return {"error": "Matrix not found - run pipeline first"}


@router.get("/discovery")
async def get_discovery_mappings(user: dict = Depends(require_role("read_only"))):
    matrix_path = DATA_DIR / "policies/reports/deployment-matrix.json"
    if matrix_path.exists():
        data = json.loads(matrix_path.read_text())
        audit_log("discovery_viewed", user=user.get('sub'))
        return data
    empty = {
        "routers": {}, "as_distribution": {}, "bgp_groups": {},
        "statistics": {}, "generated_at": datetime.utcnow().isoformat()
    }
    return empty

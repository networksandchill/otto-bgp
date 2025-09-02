from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from webui.core.security import get_current_user, require_role
from webui.core.devices import (
    load_devices, create_device, update_device, delete_device
)
from webui.core.audit import audit_log


class DeviceModel(BaseModel):
    address: str
    hostname: str
    role: str
    region: str


router = APIRouter()


@router.get("/")
async def get_devices(user: dict = Depends(get_current_user)):
    """Get all devices"""
    devices = load_devices()
    audit_log("list_devices", user=user.get("sub"))
    return {"devices": devices}


@router.post("/")
async def create_device_endpoint(
    device_data: DeviceModel,
    user: dict = Depends(require_role("admin"))
):
    """Create new device"""
    try:
        device = create_device(device_data.dict())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    audit_log("device_added", user=user.get("sub"), resource=device_data.hostname)
    return {"success": True, "device": device}


@router.put("/{address}")
async def update_device_endpoint(
    address: str,
    device_data: DeviceModel,
    user: dict = Depends(require_role("admin"))
):
    """Update device"""
    updated = update_device(address, device_data.dict())
    if not updated:
        raise HTTPException(status_code=404, detail="Device not found")
    audit_log("device_updated", user=user.get("sub"), resource=address)
    return {"success": True}


@router.delete("/{address}")
async def delete_device_endpoint(
    address: str,
    user: dict = Depends(require_role("admin"))
):
    """Delete device"""
    if not delete_device(address):
        raise HTTPException(status_code=404, detail="Device not found")
    audit_log("device_deleted", user=user.get("sub"), resource=address)
    return {"success": True}

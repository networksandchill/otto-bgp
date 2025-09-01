import csv
import io
from pathlib import Path
from typing import List, Dict, Optional
from webui.settings import CONFIG_DIR
from webui.core.fileops import atomic_write_text

DEVICES_CSV_PATH = CONFIG_DIR / 'devices.csv'

REQUIRED_FIELDS = ["address", "hostname", "role", "region"]


def load_devices() -> List[Dict]:
    """Load devices from CSV file"""
    if not DEVICES_CSV_PATH.exists():
        return []
    devices: List[Dict] = []
    with open(DEVICES_CSV_PATH, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            devices.append(row)
    return devices


def save_devices(devices: List[Dict], fieldnames: Optional[List[str]] = None):
    """Save devices to CSV file atomically"""
    if not fieldnames:
        fieldnames = REQUIRED_FIELDS
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(devices)
    atomic_write_text(DEVICES_CSV_PATH, output.getvalue(), mode=0o644)


def get_device_by_address(address: str) -> Optional[Dict]:
    """Get device by address"""
    for device in load_devices():
        if device.get("address") == address:
            return device
    return None


def create_device(device_data: Dict) -> Dict:
    """Create new device (requires REQUIRED_FIELDS)"""
    devices = load_devices()
    # Prevent duplicate by address
    for d in devices:
        if d.get("address") == device_data.get("address"):
            raise ValueError(f"Device with address {device_data.get('address')} already exists")
    # Maintain header from existing file if present
    fieldnames = devices and list(devices[0].keys()) or REQUIRED_FIELDS
    devices.append({k: device_data.get(k, "") for k in fieldnames})
    save_devices(devices, fieldnames)
    return device_data


def update_device(address: str, updates: Dict) -> Optional[Dict]:
    """Update existing device by address"""
    devices = load_devices()
    if not devices:
        return None
    fieldnames = list(devices[0].keys())
    updated = None
    new_list: List[Dict] = []
    for row in devices:
        if row.get('address') == address:
            for k, v in updates.items():
                if k in row:
                    row[k] = v
            updated = row
        new_list.append(row)
    if not updated:
        return None
    save_devices(new_list, fieldnames)
    return updated


def delete_device(address: str) -> bool:
    """Delete device by address"""
    devices = load_devices()
    if not devices:
        return False
    fieldnames = list(devices[0].keys())
    new_list = [d for d in devices if d.get('address') != address]
    if len(new_list) == len(devices):
        return False
    if new_list:
        save_devices(new_list, fieldnames)
    else:
        # Write empty file with header to preserve schema
        save_devices([], fieldnames)
    return True

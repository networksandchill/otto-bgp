import subprocess
import os
from pathlib import Path
from typing import Dict, List, Optional

# Absolute binary paths resolved at runtime (align with adapter)
SUDO_PATH = "/usr/bin/sudo"
SYSTEMCTL_PATH = "/usr/bin/systemctl"

ALLOWED_ACTIONS = ['start', 'stop', 'restart', 'reload']
ALLOWED_SERVICES = [
    'otto-bgp.service',
    'otto-bgp-autonomous.service',
    'otto-bgp.timer',
    'otto-bgp-webui-adapter.service',
    'otto-bgp-rpki-update.service',
    'otto-bgp-rpki-update.timer',
    'otto-bgp-rpki-preflight.service',
]

BASE_COMMANDS = {
    ('start', 'otto-bgp.service'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'start', 'otto-bgp.service'],
    ('stop', 'otto-bgp.service'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'stop', 'otto-bgp.service'],
    ('restart', 'otto-bgp.service'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'restart', 'otto-bgp.service'],
    ('reload', 'otto-bgp.service'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'reload', 'otto-bgp.service'],

    ('start', 'otto-bgp-autonomous.service'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'start', 'otto-bgp-autonomous.service'],
    ('stop', 'otto-bgp-autonomous.service'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'stop', 'otto-bgp-autonomous.service'],
    ('restart', 'otto-bgp-autonomous.service'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'restart', 'otto-bgp-autonomous.service'],
    ('reload', 'otto-bgp-autonomous.service'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'reload', 'otto-bgp-autonomous.service'],

    ('start', 'otto-bgp.timer'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'start', 'otto-bgp.timer'],
    ('stop', 'otto-bgp.timer'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'stop', 'otto-bgp.timer'],
    ('restart', 'otto-bgp.timer'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'restart', 'otto-bgp.timer'],
    ('reload', 'otto-bgp.timer'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'reload', 'otto-bgp.timer'],

    ('start', 'otto-bgp-webui-adapter.service'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'start', 'otto-bgp-webui-adapter.service'],
    ('stop', 'otto-bgp-webui-adapter.service'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'stop', '--no-block', 'otto-bgp-webui-adapter.service'],
    ('restart', 'otto-bgp-webui-adapter.service'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'restart', '--no-block', 'otto-bgp-webui-adapter.service'],
    ('reload', 'otto-bgp-webui-adapter.service'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'reload', 'otto-bgp-webui-adapter.service'],

    ('start', 'otto-bgp-rpki-update.service'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'start', 'otto-bgp-rpki-update.service'],
    ('stop', 'otto-bgp-rpki-update.service'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'stop', 'otto-bgp-rpki-update.service'],
    ('restart', 'otto-bgp-rpki-update.service'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'restart', 'otto-bgp-rpki-update.service'],
    ('reload', 'otto-bgp-rpki-update.service'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'reload', 'otto-bgp-rpki-update.service'],

    ('start', 'otto-bgp-rpki-update.timer'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'start', 'otto-bgp-rpki-update.timer'],
    ('stop', 'otto-bgp-rpki-update.timer'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'stop', 'otto-bgp-rpki-update.timer'],
    ('restart', 'otto-bgp-rpki-update.timer'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'restart', 'otto-bgp-rpki-update.timer'],
    ('reload', 'otto-bgp-rpki-update.timer'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'reload', 'otto-bgp-rpki-update.timer'],

    ('start', 'otto-bgp-rpki-preflight.service'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'start', 'otto-bgp-rpki-preflight.service'],
    ('stop', 'otto-bgp-rpki-preflight.service'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'stop', 'otto-bgp-rpki-preflight.service'],
    ('restart', 'otto-bgp-rpki-preflight.service'): [SUDO_PATH, '-n', SYSTEMCTL_PATH, 'restart', 'otto-bgp-rpki-preflight.service'],
}


def systemd_units_status(units: List[str]) -> List[Dict]:
    results: List[Dict] = []
    for unit in units:
        try:
            result = subprocess.run(
                [SYSTEMCTL_PATH, 'show', '-p', 'ActiveState,SubState,Description', unit],
                capture_output=True, text=True, timeout=5
            )
            info = {"name": unit}
            for line in result.stdout.strip().split('\n'):
                if '=' in line:
                    k, v = line.split('=', 1)
                    info[k.lower()] = v
            results.append(info)
        except Exception as e:
            results.append({"name": unit, "error": str(e)})
    return results


def control_service(action: str, service: str) -> Dict:
    # Check if service control is enabled
    from webui.settings import OTTO_WEBUI_ENABLE_SERVICE_CONTROL
    if not OTTO_WEBUI_ENABLE_SERVICE_CONTROL:
        return {"success": False, "message": "Service control is disabled. Set OTTO_WEBUI_ENABLE_SERVICE_CONTROL=true in otto.env to enable."}
    
    if action not in ALLOWED_ACTIONS or service not in ALLOWED_SERVICES:
        return {"success": False, "message": "Invalid action or service"}
    cmd = BASE_COMMANDS.get((action, service))
    if not cmd:
        return {"success": False, "message": "Command not supported"}
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return {"success": True}
        # Check if it's a sudo permission issue
        error_msg = (result.stderr or result.stdout)[:500]
        if "sudo:" in error_msg.lower() or "password" in error_msg.lower() or result.returncode == 1:
            return {"success": False, "message": "Service control requires sudo permissions. Please configure sudoers for the otto-bgp user or set OTTO_WEBUI_ENABLE_SERVICE_CONTROL=false in otto.env"}
        return {"success": False, "message": error_msg[:200]}
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "Command timed out"}

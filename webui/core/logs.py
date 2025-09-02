import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from webui.settings import DATA_DIR

LOG_DIR = DATA_DIR / "logs"


def parse_json_log_line(line: str) -> Dict:
    """Parse JSON format log line"""
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return {"raw": line}


def parse_delimited_log_line(line: str, delimiter: str = " - ") -> Dict:
    """Parse delimited format log line"""
    parts = line.split(delimiter, 2)
    if len(parts) >= 3:
        return {
            "timestamp": parts[0],
            "level": parts[1],
            "message": parts[2]
        }
    return {"raw": line}


def get_log_files() -> List[Dict]:
    """Get list of available log files"""
    if not LOG_DIR.exists():
        return []

    files = []
    for path in LOG_DIR.iterdir():
        if path.is_file() and path.suffix == ".log":
            stats = path.stat()
            files.append({
                "name": path.name,
                "size": stats.st_size,
                "modified": datetime.fromtimestamp(stats.st_mtime).isoformat()
            })
    return sorted(files, key=lambda x: x["name"])


def read_log_file(filename: str, lines: int = 100, offset: int = 0) -> Dict:
    """Read log file with pagination"""
    log_path = LOG_DIR / filename
    if not log_path.exists():
        return {"error": "File not found"}

    with open(log_path, 'r') as f:
        all_lines = f.readlines()

    total = len(all_lines)
    start = max(0, total - offset - lines)
    end = total - offset

    entries = []
    # Reverse to show newest first
    for line in reversed(all_lines[start:end]):
        if filename == "audit.log":
            entries.append(parse_json_log_line(line.strip()))
        else:
            entries.append(parse_delimited_log_line(line.strip()))

    return {
        "filename": filename,
        "total_lines": total,
        "offset": offset,
        "lines": lines,
        "entries": entries,
        "has_more": offset + lines < total
    }


def get_journalctl_logs(unit: str = None, lines: int = 100) -> List[str]:
    """Get systemd journal logs (newest first)"""
    cmd = ["journalctl", "--no-pager", "-r", "-o", "json", f"-n{lines}"]
    if unit:
        cmd.extend(["-u", unit])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip().split('\n')
    except Exception:
        pass
    return []

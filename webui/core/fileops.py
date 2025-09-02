import os
import json
import tempfile
from pathlib import Path
from typing import Any, Dict

def atomic_write_json(path: Path, data: Dict[str, Any], mode: int = 0o600):
    """Atomically write JSON file with specified permissions"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=str(path.parent), delete=False) as tmp:
        json.dump(data, tmp, indent=2)
    tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)
    os.chmod(path, mode)

def atomic_write_text(path: Path, content: str, mode: int = 0o600):
    """Atomically write text file with specified permissions"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=str(path.parent), delete=False) as tmp:
        tmp.write(content)
    tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)
    os.chmod(path, mode)

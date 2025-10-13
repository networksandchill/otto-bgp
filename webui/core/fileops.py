import json
import os
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional


def atomic_write_json(path: Path, data: Dict[str, Any], mode: int = 0o600):
    """Atomically write JSON file with specified permissions"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
            'w', dir=str(path.parent), delete=False) as tmp:
        json.dump(data, tmp, indent=2)
    tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)
    os.chmod(path, mode)


def atomic_write_text(path: Path, content: str, mode: int = 0o600):
    """Atomically write text file with specified permissions"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
            'w', dir=str(path.parent), delete=False) as tmp:
        tmp.write(content)
    tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)
    os.chmod(path, mode)


def backup_file(src: Path, dst_dir: Path,
                preserve_structure: bool = False) -> Optional[Path]:
    """
    Create a backup of a file in the destination directory.

    Args:
        src: Source file to backup
        dst_dir: Destination directory for backup
        preserve_structure: If True, preserve directory structure in backup

    Returns:
        Path to the backup file, or None if source doesn't exist
    """
    if not src.exists():
        return None

    dst_dir.mkdir(parents=True, exist_ok=True)

    if preserve_structure:
        # Preserve the relative path structure
        dst_file = dst_dir / src.name
    else:
        dst_file = dst_dir / src.name

    shutil.copy2(src, dst_file)
    return dst_file


def create_timestamped_backup(
        files_to_backup: list[Path],
        backup_root: Path) -> tuple[Path, list[Path]]:
    """
    Create a timestamped backup of multiple files.

    Args:
        files_to_backup: List of files to backup
        backup_root: Root directory for backups

    Returns:
        Tuple of (backup directory path, list of backed up file paths)
    """
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    backup_dir = backup_root / timestamp
    backup_dir.mkdir(parents=True, exist_ok=True)

    backed_up = []
    for file_path in files_to_backup:
        if file_path.exists():
            backup_path = backup_file(file_path, backup_dir)
            if backup_path:
                backed_up.append(backup_path)

    return backup_dir, backed_up


def cleanup_old_backups(backup_root: Path, days: int = 30, keep_minimum: int = 5):
    """
    Clean up old backup directories while keeping a minimum number.

    Args:
        backup_root: Root directory containing timestamped backup folders
        days: Remove backups older than this many days
        keep_minimum: Always keep at least this many backups
    """
    if not backup_root.exists():
        return

    # Get all backup directories (assuming YYYYMMDD_HHMMSS format)
    backup_dirs = []
    for item in backup_root.iterdir():
        if item.is_dir() and len(item.name) == 15 and item.name[8] == '_':
            try:
                # Parse timestamp from directory name
                timestamp_str = item.name
                timestamp = datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
                backup_dirs.append((timestamp, item))
            except ValueError:
                # Skip directories that don't match the expected format
                continue

    # Sort by timestamp (newest first)
    backup_dirs.sort(key=lambda x: x[0], reverse=True)

    # Keep minimum number of backups
    if len(backup_dirs) <= keep_minimum:
        return

    # Calculate cutoff date
    cutoff_date = datetime.utcnow() - timedelta(days=days)

    # Remove old backups (but keep minimum)
    for i, (timestamp, backup_dir) in enumerate(backup_dirs):
        if i < keep_minimum:
            continue
        if timestamp < cutoff_date:
            shutil.rmtree(backup_dir, ignore_errors=True)


def restore_backup(backup_dir: Path, restore_targets: dict[Path, Path]) -> list[Path]:
    """
    Restore files from a backup directory.

    Args:
        backup_dir: Directory containing the backup files
        restore_targets: Dictionary mapping backup filenames to restore destinations

    Returns:
        List of successfully restored file paths
    """
    restored = []

    for backup_name, restore_path in restore_targets.items():
        backup_file_path = backup_dir / backup_name.name if isinstance(backup_name, Path) else backup_dir / backup_name
        if backup_file_path.exists():
            restore_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_file_path, restore_path)
            restored.append(restore_path)

    return restored

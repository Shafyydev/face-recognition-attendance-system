"""
Automated SQLite Database Backup Utility
Safely creates timestamped copies of the attendance database using SQLite's
online backup API (WAL-safe, lock-safe, without interrupting live app operations).
"""

import os
import sys
import sqlite3
from datetime import datetime

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("ATTENDANCE_DB_PATH", os.path.join(APP_DIR, "attendance.db"))
BACKUP_DIR = os.path.join(APP_DIR, "backups")


def backup_database(destination_dir: str = BACKUP_DIR, max_backups: int = 10) -> str:
    """Create a point-in-time backup of the attendance database.
    
    Args:
        destination_dir: Directory where backup files will be saved.
        max_backups: Maximum number of recent backups to retain (older ones are pruned).
        
    Returns:
        The file path to the newly created backup.
    """
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"Source database not found at: {DB_PATH}")

    os.makedirs(destination_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"attendance_backup_{timestamp}.db"
    backup_filepath = os.path.join(destination_dir, backup_filename)

    print(f"[BACKUP] Starting online backup of: {DB_PATH}")
    src_conn = sqlite3.connect(DB_PATH)
    dst_conn = sqlite3.connect(backup_filepath)

    try:
        # Use SQLite's online backup API for safe snapshot during live reads/writes
        src_conn.backup(dst_conn)
        print(f"[BACKUP] Snapshot completed successfully.")
    finally:
        dst_conn.close()
        src_conn.close()

    size_bytes = os.path.getsize(backup_filepath)
    size_kb = size_bytes / 1024.0
    print(f"[BACKUP] Saved to: {backup_filepath} ({size_kb:.2f} KB)")

    # Rotate old backups
    prune_old_backups(destination_dir, max_backups=max_backups)
    return backup_filepath


def prune_old_backups(destination_dir: str, max_backups: int = 10):
    """Keep only the latest `max_backups` files in destination_dir."""
    if max_backups <= 0:
        return

    backups = []
    for fname in os.listdir(destination_dir):
        if fname.startswith("attendance_backup_") and fname.endswith(".db"):
            fpath = os.path.join(destination_dir, fname)
            if os.path.isfile(fpath):
                backups.append((os.path.getmtime(fpath), fpath))

    backups.sort(key=lambda x: x[0], reverse=True)

    if len(backups) > max_backups:
        for _, old_path in backups[max_backups:]:
            try:
                os.remove(old_path)
                print(f"[BACKUP] Pruned old backup: {os.path.basename(old_path)}")
            except Exception as exc:
                print(f"[BACKUP] Failed to prune {old_path}: {exc}")


if __name__ == "__main__":
    try:
        backup_database()
    except Exception as err:
        print(f"[ERROR] Backup failed: {err}", file=sys.stderr)
        sys.exit(1)

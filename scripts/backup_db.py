"""
Automated SQLite Database Backup Utility
Creates a timestamped copy of instance/seamaster.db in instance/backups/
"""
import os
import shutil
import sqlite3
from datetime import datetime

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(ROOT_DIR, 'instance')
DB_PATH = os.path.join(INSTANCE_DIR, 'seamaster.db')
BACKUP_DIR = os.path.join(INSTANCE_DIR, 'backups')

def backup_database():
    if not os.path.exists(DB_PATH):
        print(f"Error: Main database not found at {DB_PATH}")
        return False

    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = os.path.join(BACKUP_DIR, f'seamaster_backup_{timestamp}.db')

    print(f"Creating safe online SQLite backup of {DB_PATH} -> {backup_file}...")
    try:
        # Use SQLite's online backup API for zero downtime and consistency
        src_conn = sqlite3.connect(DB_PATH)
        dst_conn = sqlite3.connect(backup_file)
        
        with dst_conn:
            src_conn.backup(dst_conn, pages=100)
            
        dst_conn.close()
        src_conn.close()

        size_bytes = os.path.getsize(backup_file)
        print(f"Backup created successfully: {os.path.basename(backup_file)} ({size_bytes / 1024:.1f} KB)")
        
        # Keep only the last 10 backups to save space
        backups = sorted([os.path.join(BACKUP_DIR, f) for f in os.listdir(BACKUP_DIR) if f.startswith('seamaster_backup_')])
        if len(backups) > 10:
            for old_backup in backups[:-10]:
                os.remove(old_backup)
                print(f"Removed old backup: {os.path.basename(old_backup)}")
                
        return True
    except Exception as e:
        print(f"Backup failed: {e}")
        return False

if __name__ == '__main__':
    backup_database()

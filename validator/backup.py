import shutil
import sqlite3
import json
from datetime import datetime
from pathlib import Path
import logging
from typing import Optional, List
import tarfile
import os

from .config import get_settings
from .logging_config import logger

settings = get_settings()

class BackupManager:
    def __init__(self, backup_dir: str = "backups"):
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(exist_ok=True)
        self.db_path = Path(settings.DATABASE_URL)
        self.metrics_path = Path("logs/metrics.json")
        self.env_path = Path(".env")

    def create_backup(self, description: Optional[str] = None) -> str:
        """Create a backup of the database and configuration"""
        try:
            # Create timestamp for backup name
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"validator_backup_{timestamp}"
            if description:
                backup_name += f"_{description}"
            
            backup_path = self.backup_dir / backup_name
            backup_path.mkdir(exist_ok=True)

            # Backup database
            if self.db_path.exists():
                self._backup_database(backup_path / "tokens.db")

            # Backup metrics
            if self.metrics_path.exists():
                shutil.copy2(self.metrics_path, backup_path / "metrics.json")

            # Backup environment configuration
            if self.env_path.exists():
                shutil.copy2(self.env_path, backup_path / ".env")

            # Create archive
            archive_path = f"{backup_path}.tar.gz"
            with tarfile.open(archive_path, "w:gz") as tar:
                tar.add(backup_path, arcname=backup_name)

            # Clean up temporary directory
            shutil.rmtree(backup_path)

            logger.info(f"Backup created successfully: {archive_path}")
            return archive_path

        except Exception as e:
            logger.error(f"Error creating backup: {str(e)}")
            raise

    def restore_backup(self, backup_path: str) -> bool:
        """Restore from a backup archive"""
        try:
            backup_path = Path(backup_path)
            if not backup_path.exists():
                raise FileNotFoundError(f"Backup file not found: {backup_path}")

            # Create temporary directory for extraction
            temp_dir = self.backup_dir / "temp_restore"
            temp_dir.mkdir(exist_ok=True)

            # Extract archive
            with tarfile.open(backup_path, "r:gz") as tar:
                tar.extractall(temp_dir)

            # Get extracted directory
            backup_name = backup_path.stem.replace(".tar", "")
            extracted_dir = temp_dir / backup_name

            # Restore database
            db_backup = extracted_dir / "tokens.db"
            if db_backup.exists():
                self._restore_database(db_backup)

            # Restore metrics
            metrics_backup = extracted_dir / "metrics.json"
            if metrics_backup.exists():
                shutil.copy2(metrics_backup, self.metrics_path)

            # Restore environment configuration
            env_backup = extracted_dir / ".env"
            if env_backup.exists():
                shutil.copy2(env_backup, self.env_path)

            # Clean up
            shutil.rmtree(temp_dir)

            logger.info(f"Backup restored successfully from: {backup_path}")
            return True

        except Exception as e:
            logger.error(f"Error restoring backup: {str(e)}")
            raise
        finally:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)

    def list_backups(self) -> List[dict]:
        """List all available backups"""
        backups = []
        for backup in self.backup_dir.glob("*.tar.gz"):
            try:
                stat = backup.stat()
                backups.append({
                    "name": backup.name,
                    "size": stat.st_size,
                    "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    "path": str(backup)
                })
            except Exception as e:
                logger.error(f"Error reading backup {backup}: {str(e)}")

        return sorted(backups, key=lambda x: x["created"], reverse=True)

    def _backup_database(self, backup_path: Path):
        """Create a backup of the SQLite database"""
        try:
            # Create a new backup using SQLite's backup API
            with sqlite3.connect(self.db_path) as src, \
                 sqlite3.connect(backup_path) as dst:
                src.backup(dst)
        except Exception as e:
            logger.error(f"Error backing up database: {str(e)}")
            raise

    def _restore_database(self, backup_path: Path):
        """Restore the SQLite database from backup"""
        try:
            # Stop any active connections
            with sqlite3.connect(self.db_path) as conn:
                conn.close()

            # Replace current database with backup
            shutil.copy2(backup_path, self.db_path)
        except Exception as e:
            logger.error(f"Error restoring database: {str(e)}")
            raise

# Create global instance
backup_manager = BackupManager() 
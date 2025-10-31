import threading
import time
import os
from datetime import timedelta

from database import Database
from logging_config import logger


def _run_cleanup(db: Database, interval_seconds: int):
    logger.info("background: starting cleanup loop, interval=%s", interval_seconds)
    while True:
        try:
            deleted = db.delete_expired_offers()
            if deleted:
                logger.info("background: deleted %s expired offers", deleted)
        except Exception as e:
            logger.exception("background cleanup failed: %s", e)
        time.sleep(interval_seconds)


def _run_daily_backup(db: Database, interval_seconds: int):
    logger.info("background: starting backup loop, interval=%s", interval_seconds)
    while True:
        try:
            backup_file = db.backup_database()
            logger.info("background: backup created %s", backup_file)
        except Exception as e:
            logger.exception("background backup failed: %s", e)
        time.sleep(interval_seconds)


def start_background_tasks(db: Database = None):
    """Start background threads for cleanup and backups. Non-blocking.

    Use small intervals for testing; override with environment variables:
      CLEANUP_INTERVAL_SECONDS, BACKUP_INTERVAL_SECONDS
    """
    if db is None:
        db = Database()

    cleanup_interval = int(os.environ.get('CLEANUP_INTERVAL_SECONDS', 300))
    backup_interval = int(os.environ.get('BACKUP_INTERVAL_SECONDS', 86400))

    t1 = threading.Thread(target=_run_cleanup, args=(db, cleanup_interval), daemon=True)
    t1.start()

    t2 = threading.Thread(target=_run_daily_backup, args=(db, backup_interval), daemon=True)
    t2.start()

    logger.info("background tasks started")

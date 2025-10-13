"""Core database connection and schema management with thread-safe pooling"""
import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from .exceptions import SchemaError

logger = logging.getLogger('otto_bgp.database.core')

# Schema version for migrations
SCHEMA_VERSION = 1


class DatabaseManager:
    """Thread-safe SQLite database manager with connection pooling"""

    _instance = None
    _lock = threading.Lock()
    _local = threading.local()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # Support configurable DB path
        db_path_str = os.getenv('OTTO_DB_PATH')
        if db_path_str:
            self.db_path = Path(db_path_str)
        elif os.getenv('OTTO_BGP_MODE') == 'system':
            self.db_path = Path('/var/lib/otto-bgp/otto.db')
        else:
            # Development mode - use local path
            self.db_path = Path('./otto.db')

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()
        self._initialized = True

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection"""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                str(self.db_path),
                isolation_level='DEFERRED',
                timeout=30.0
            )
            self._local.conn.execute('PRAGMA journal_mode=WAL')
            self._local.conn.execute('PRAGMA foreign_keys=ON')
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_database(self):
        """Initialize database with schema and migrations"""
        conn = sqlite3.connect(str(self.db_path))
        try:
            # Check current version
            current_version = conn.execute('PRAGMA user_version').fetchone()[0]

            if current_version < SCHEMA_VERSION:
                self._migrate_schema(conn, current_version)

            conn.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
            conn.commit()
            logger.info(f"Database initialized at version {SCHEMA_VERSION}")
        except sqlite3.Error as e:
            raise SchemaError(f"Failed to initialize database: {e}")
        finally:
            conn.close()

    def _migrate_schema(self, conn: sqlite3.Connection, from_version: int):
        """Run schema migrations"""
        if from_version < 1:
            # Initial schema
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS rpki_overrides (
                    as_number INTEGER PRIMARY KEY
                        CHECK(as_number >= 0 AND
                              as_number <= 4294967295),
                    rpki_enabled BOOLEAN NOT NULL DEFAULT 1,
                    reason TEXT CHECK(length(reason) <= 500),
                    modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    modified_by TEXT CHECK(length(modified_by) <= 100)
                );

                CREATE TABLE IF NOT EXISTS rpki_override_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    as_number INTEGER NOT NULL
                        CHECK(as_number >= 0 AND
                              as_number <= 4294967295),
                    action TEXT NOT NULL
                        CHECK(action IN ('enable', 'disable')),
                    reason TEXT CHECK(length(reason) <= 500),
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    user TEXT CHECK(length(user) <= 100),
                    ip_address TEXT CHECK(length(ip_address) <= 45)
                );

                CREATE INDEX IF NOT EXISTS idx_rpki_enabled
                    ON rpki_overrides(rpki_enabled);
                CREATE INDEX IF NOT EXISTS idx_history_as
                    ON rpki_override_history(as_number);
                CREATE INDEX IF NOT EXISTS idx_history_date
                    ON rpki_override_history(timestamp);

                -- Multi-router coordination tables
                CREATE TABLE IF NOT EXISTS rollout_runs (
                    run_id TEXT PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT NOT NULL
                        CHECK(status IN ('planning', 'active', 'paused', 'completed', 'failed', 'aborted')),
                    initiated_by TEXT CHECK(length(initiated_by) <= 100)
                );

                CREATE TABLE IF NOT EXISTS rollout_stages (
                    stage_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    sequencing INTEGER NOT NULL,
                    name TEXT NOT NULL CHECK(length(name) <= 200),
                    guardrail_snapshot TEXT,
                    FOREIGN KEY(run_id) REFERENCES rollout_runs(run_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS rollout_targets (
                    target_id TEXT PRIMARY KEY,
                    stage_id TEXT NOT NULL,
                    hostname TEXT NOT NULL CHECK(length(hostname) <= 255),
                    policy_hash TEXT CHECK(length(policy_hash) <= 64),
                    state TEXT NOT NULL
                        CHECK(state IN ('pending', 'in_progress', 'completed', 'failed', 'skipped')),
                    last_error TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(stage_id) REFERENCES rollout_stages(stage_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS rollout_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    event_type TEXT NOT NULL CHECK(length(event_type) <= 100),
                    payload TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(run_id) REFERENCES rollout_runs(run_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_rollout_runs_status
                    ON rollout_runs(status);
                CREATE INDEX IF NOT EXISTS idx_rollout_runs_created
                    ON rollout_runs(created_at);
                CREATE INDEX IF NOT EXISTS idx_rollout_stages_run
                    ON rollout_stages(run_id, sequencing);
                CREATE INDEX IF NOT EXISTS idx_rollout_targets_stage
                    ON rollout_targets(stage_id, state);
                CREATE INDEX IF NOT EXISTS idx_rollout_targets_hostname
                    ON rollout_targets(hostname);
                CREATE INDEX IF NOT EXISTS idx_rollout_events_run
                    ON rollout_events(run_id, timestamp);
            ''')
            logger.info("Applied migration: initial schema with multi-router coordination")

    @contextmanager
    def transaction(self):
        """Context manager for atomic transactions"""
        conn = self._get_connection()
        savepoint = f"sp_{threading.get_ident()}_{id(conn)}"
        try:
            conn.execute(f"SAVEPOINT {savepoint}")
            yield conn
            conn.execute(f"RELEASE {savepoint}")
            conn.commit()
        except Exception:
            conn.execute(f"ROLLBACK TO {savepoint}")
            raise

    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a query with automatic transaction handling"""
        with self.transaction() as conn:
            return conn.execute(query, params)

    def fetchone(
            self, query: str, params: tuple = ()
    ) -> Optional[sqlite3.Row]:
        """Fetch one row"""
        conn = self._get_connection()
        return conn.execute(query, params).fetchone()

    def fetchall(self, query: str, params: tuple = ()) -> list:
        """Fetch all rows"""
        conn = self._get_connection()
        return conn.execute(query, params).fetchall()


# Backward compatibility
OttoDB = DatabaseManager


def get_db() -> DatabaseManager:
    """Get database instance"""
    return DatabaseManager()

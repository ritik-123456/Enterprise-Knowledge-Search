import os
import sqlite3
import time
from typing import Optional


class PersistentRateLimiter:
    """
    Persistent, multi-process SQLite-backed sliding window rate limiter.
    Ensures upload rate limits are shared and enforced across all worker processes,
    server reloads, and container threads.
    """
    def __init__(self, db_path: Optional[str] = None, max_requests: int = 15, window_seconds: float = 60.0):
        if db_path is None:
            # Place in Backend/storage directory
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            storage_dir = os.path.join(base_dir, "storage")
            os.makedirs(storage_dir, exist_ok=True)
            db_path = os.path.join(storage_dir, "rate_limits.sqlite3")

        self.db_path = db_path
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_db(self) -> None:
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS upload_rate_limits (
                        user_id TEXT NOT NULL,
                        timestamp REAL NOT NULL
                    );
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_user_timestamp
                    ON upload_rate_limits(user_id, timestamp);
                """)
        except Exception:
            pass

    def check_and_record(self, user_id: str) -> bool:
        """
        Atomically checks if user is within the rate limit and logs current upload attempt.
        Returns True if permitted, False if limit exceeded.
        """
        now = time.time()
        cutoff = now - self.window_seconds
        try:
            with self._get_connection() as conn:
                # Clean expired records for this user
                conn.execute("DELETE FROM upload_rate_limits WHERE user_id = ? AND timestamp < ?", (user_id, cutoff))
                # Count recent requests
                cursor = conn.execute("SELECT COUNT(*) FROM upload_rate_limits WHERE user_id = ?", (user_id,))
                count = cursor.fetchone()[0]
                if count >= self.max_requests:
                    return False
                # Record current request
                conn.execute("INSERT INTO upload_rate_limits (user_id, timestamp) VALUES (?, ?)", (user_id, now))
                return True
        except Exception:
            # Fallback to allow if storage error occurs
            return True

    def reset_user(self, user_id: str) -> None:
        """Resets rate limit entries for a specific user (useful for test fixtures)."""
        try:
            with self._get_connection() as conn:
                conn.execute("DELETE FROM upload_rate_limits WHERE user_id = ?", (user_id,))
        except Exception:
            pass

    def clear(self) -> None:
        """Clears all rate limit entries."""
        try:
            with self._get_connection() as conn:
                conn.execute("DELETE FROM upload_rate_limits")
        except Exception:
            pass


upload_rate_limiter = PersistentRateLimiter()

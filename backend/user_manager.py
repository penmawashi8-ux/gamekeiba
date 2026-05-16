"""ユーザー管理（SQLite）"""

import sqlite3
import threading
import logging
from typing import Optional, List, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

DB_PATH = "users.db"
INITIAL_BALANCE = 10_000
BROKE_THRESHOLD = 100
RESTORE_MINUTES = 10


class UserManager:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _init_db(self):
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id      TEXT PRIMARY KEY,
                        display_name TEXT NOT NULL,
                        balance      INTEGER NOT NULL DEFAULT 10000,
                        created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
                        updated_at   TEXT DEFAULT CURRENT_TIMESTAMP,
                        broke_at     TEXT DEFAULT NULL
                    )
                """)
                conn.commit()
            finally:
                conn.close()

    def get_or_create_user(self, user_id: str, display_name: str) -> dict:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT user_id, display_name, balance FROM users WHERE user_id = ?",
                    (user_id,)
                ).fetchone()
                if row:
                    if row[1] != display_name:
                        conn.execute(
                            "UPDATE users SET display_name = ?, updated_at = ? WHERE user_id = ?",
                            (display_name, datetime.now().isoformat(), user_id)
                        )
                        conn.commit()
                    return {"user_id": row[0], "display_name": display_name, "balance": row[2]}
                conn.execute(
                    "INSERT INTO users (user_id, display_name, balance) VALUES (?, ?, ?)",
                    (user_id, display_name, INITIAL_BALANCE)
                )
                conn.commit()
                return {"user_id": user_id, "display_name": display_name, "balance": INITIAL_BALANCE}
            finally:
                conn.close()

    def get_balance(self, user_id: str) -> Optional[int]:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT balance FROM users WHERE user_id = ?", (user_id,)
                ).fetchone()
                return row[0] if row else None
            finally:
                conn.close()

    def update_balance(self, user_id: str, delta: int) -> Optional[int]:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT balance, broke_at FROM users WHERE user_id = ?", (user_id,)
                ).fetchone()
                if row is None:
                    return None
                new_balance = max(0, row[0] + delta)
                old_broke_at = row[1]
                now = datetime.now().isoformat()
                if new_balance < BROKE_THRESHOLD and old_broke_at is None:
                    broke_at = now
                elif new_balance >= BROKE_THRESHOLD:
                    broke_at = None
                else:
                    broke_at = old_broke_at
                conn.execute(
                    "UPDATE users SET balance = ?, updated_at = ?, broke_at = ? WHERE user_id = ?",
                    (new_balance, now, broke_at, user_id)
                )
                conn.commit()
                return new_balance
            finally:
                conn.close()

    def restore_broke_users(self) -> List[Tuple[str, str]]:
        threshold = (datetime.now() - timedelta(minutes=RESTORE_MINUTES)).isoformat()
        with self._lock:
            conn = self._connect()
            try:
                targets = conn.execute(
                    "SELECT user_id, display_name FROM users "
                    "WHERE broke_at IS NOT NULL AND broke_at <= ?",
                    (threshold,)
                ).fetchall()
                now = datetime.now().isoformat()
                for uid, _ in targets:
                    conn.execute(
                        "UPDATE users SET balance = ?, updated_at = ?, broke_at = NULL WHERE user_id = ?",
                        (INITIAL_BALANCE, now, uid)
                    )
                if targets:
                    conn.commit()
                return targets
            finally:
                conn.close()

    def restore_user(self, user_id: str) -> Optional[int]:
        """残高がBROKE_THRESHOLD未満のユーザーを即時リセット（手動リクエスト用）"""
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT balance FROM users WHERE user_id = ?", (user_id,)
                ).fetchone()
                if row is None or row[0] >= BROKE_THRESHOLD:
                    return None
                now = datetime.now().isoformat()
                conn.execute(
                    "UPDATE users SET balance = ?, updated_at = ?, broke_at = NULL WHERE user_id = ?",
                    (INITIAL_BALANCE, now, user_id)
                )
                conn.commit()
                return INITIAL_BALANCE
            finally:
                conn.close()

    def get_ranking(self, limit: int = 5) -> List[Tuple[str, int]]:
        with self._lock:
            conn = self._connect()
            try:
                return conn.execute(
                    "SELECT display_name, balance FROM users ORDER BY balance DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            finally:
                conn.close()

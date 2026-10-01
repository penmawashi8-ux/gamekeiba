"""ユーザー管理（Postgres / SQLite）

DATABASE_URL が設定されていれば Postgres（Neon など外部DB）に保存する。
Render の無課金プランはディスクが一時領域で、再デプロイや無通信15分の
自動スリープからの復帰でファイルが消えるため、SQLite のままだと所持金が
リセットされる。未設定ならローカル開発用に SQLite (users.db) を使う。
"""

import os
import sqlite3
import threading
import logging
from typing import Optional, List, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

DB_PATH = "users.db"
DATABASE_URL = os.environ.get("DATABASE_URL", "")
INITIAL_BALANCE = 10_000
BROKE_THRESHOLD = 100
RESTORE_MINUTES = 10


class UserManager:
    def __init__(self, db_path: str = DB_PATH, database_url: str = DATABASE_URL):
        self.db_path = db_path
        self.database_url = database_url
        self._pg = bool(database_url)
        self._lock = threading.Lock()
        # 外部DBは接続のたびにTLSハンドシェイクが走るので、接続は使い回す
        self._conn = None
        self._init_db()
        logger.info("UserManager: %s", "Postgres" if self._pg else f"SQLite ({db_path})")

    def _connect(self):
        if self._pg:
            import psycopg
            return psycopg.connect(self.database_url, connect_timeout=10)
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _run(self, fn):
        """接続を渡して fn を1トランザクションで実行する。

        外部DBは無通信が続くと接続を切る（Neon はスリープもする）ので、
        接続エラーのときは1回だけ張り直してやり直す。
        """
        with self._lock:
            for attempt in (1, 2):
                if self._conn is None:
                    self._conn = self._connect()
                try:
                    result = fn(self._conn)
                    self._conn.commit()
                    return result
                except Exception as e:
                    try:
                        self._conn.rollback()
                    except Exception:
                        pass
                    if attempt == 2 or not self._is_connection_error(e):
                        raise
                    logger.warning("DB接続を張り直します: %s", e)
                    try:
                        self._conn.close()
                    except Exception:
                        pass
                    self._conn = None

    def _is_connection_error(self, e: Exception) -> bool:
        if not self._pg:
            return False
        import psycopg
        return isinstance(e, (psycopg.OperationalError, psycopg.InterfaceError))

    def _sql(self, query: str) -> str:
        # クエリは SQLite の ? で書き、Postgres では %s に置き換える
        return query.replace("?", "%s") if self._pg else query

    def _exec(self, conn, query: str, params: tuple = ()):
        cur = conn.cursor()
        cur.execute(self._sql(query), params)
        return cur

    def _init_db(self):
        # 日時は ISO 文字列で持つ（broke_at の比較も文字列で行う）
        self._run(lambda conn: self._exec(conn, """
            CREATE TABLE IF NOT EXISTS users (
                user_id      TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                balance      INTEGER NOT NULL DEFAULT 10000,
                created_at   TEXT,
                updated_at   TEXT,
                broke_at     TEXT DEFAULT NULL
            )
        """))

    def get_or_create_user(self, user_id: str, display_name: str) -> dict:
        def fn(conn):
            row = self._exec(
                conn,
                "SELECT user_id, display_name, balance FROM users WHERE user_id = ?",
                (user_id,)
            ).fetchone()
            now = datetime.now().isoformat()
            if row:
                if row[1] != display_name:
                    self._exec(
                        conn,
                        "UPDATE users SET display_name = ?, updated_at = ? WHERE user_id = ?",
                        (display_name, now, user_id)
                    )
                return {"user_id": row[0], "display_name": display_name, "balance": row[2]}
            self._exec(
                conn,
                "INSERT INTO users (user_id, display_name, balance, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, display_name, INITIAL_BALANCE, now, now)
            )
            return {"user_id": user_id, "display_name": display_name, "balance": INITIAL_BALANCE}
        return self._run(fn)

    def get_balance(self, user_id: str) -> Optional[int]:
        def fn(conn):
            row = self._exec(
                conn, "SELECT balance FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            return row[0] if row else None
        return self._run(fn)

    def update_balance(self, user_id: str, delta: int) -> Optional[int]:
        def fn(conn):
            row = self._exec(
                conn, "SELECT balance, broke_at FROM users WHERE user_id = ?", (user_id,)
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
            self._exec(
                conn,
                "UPDATE users SET balance = ?, updated_at = ?, broke_at = ? WHERE user_id = ?",
                (new_balance, now, broke_at, user_id)
            )
            return new_balance
        return self._run(fn)

    def restore_broke_users(self) -> List[Tuple[str, str]]:
        threshold = (datetime.now() - timedelta(minutes=RESTORE_MINUTES)).isoformat()

        def fn(conn):
            targets = self._exec(
                conn,
                "SELECT user_id, display_name FROM users "
                "WHERE broke_at IS NOT NULL AND broke_at <= ?",
                (threshold,)
            ).fetchall()
            now = datetime.now().isoformat()
            for uid, _ in targets:
                self._exec(
                    conn,
                    "UPDATE users SET balance = ?, updated_at = ?, broke_at = NULL WHERE user_id = ?",
                    (INITIAL_BALANCE, now, uid)
                )
            return [tuple(t) for t in targets]
        return self._run(fn)

    def restore_user(self, user_id: str) -> Optional[int]:
        """残高がBROKE_THRESHOLD未満のユーザーを即時リセット（手動リクエスト用）"""
        def fn(conn):
            row = self._exec(
                conn, "SELECT balance FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            if row is None or row[0] >= BROKE_THRESHOLD:
                return None
            self._exec(
                conn,
                "UPDATE users SET balance = ?, updated_at = ?, broke_at = NULL WHERE user_id = ?",
                (INITIAL_BALANCE, datetime.now().isoformat(), user_id)
            )
            return INITIAL_BALANCE
        return self._run(fn)

    def get_ranking(self, limit: int = 5) -> List[Tuple[str, int]]:
        return self._run(lambda conn: [tuple(r) for r in self._exec(
            conn,
            "SELECT display_name, balance FROM users ORDER BY balance DESC LIMIT ?",
            (limit,)
        ).fetchall()])

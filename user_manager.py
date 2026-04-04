"""
ユーザー管理モジュール

YouTubeのchannel_idをキーにSQLiteでユーザーを永続管理する。
初回コメント時に自動登録し、残高10,000円を付与する。
"""

import sqlite3
import threading
import logging
from typing import Optional, List, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = "users.db"
INITIAL_BALANCE = 10_000  # 初期残高


class UserManager:
    """ユーザー管理クラス（スレッドセーフ）"""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    # ──────────────────────────────────────────────
    # 内部ユーティリティ
    # ──────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        """DB接続を返す（check_same_thread=Falseで複数スレッドから使用可）"""
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _init_db(self):
        """テーブルが無ければ作成する"""
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        channel_id   TEXT PRIMARY KEY,
                        display_name TEXT NOT NULL,
                        balance      INTEGER NOT NULL DEFAULT 10000,
                        created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
                        updated_at   TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
                logger.info("データベースを初期化しました: %s", self.db_path)
            finally:
                conn.close()

    # ──────────────────────────────────────────────
    # 公開API
    # ──────────────────────────────────────────────

    def get_or_create_user(self, channel_id: str, display_name: str) -> dict:
        """
        ユーザーを取得または新規作成する。

        初回コメント時に残高 INITIAL_BALANCE で自動登録。
        表示名が変わった場合は上書き更新する。

        Returns:
            dict: {channel_id, display_name, balance}
        """
        with self._lock:
            conn = self._connect()
            try:
                cursor = conn.execute(
                    "SELECT channel_id, display_name, balance FROM users WHERE channel_id = ?",
                    (channel_id,)
                )
                row = cursor.fetchone()

                if row:
                    # 表示名が変わっていたら更新
                    if row[1] != display_name:
                        conn.execute(
                            "UPDATE users SET display_name = ?, updated_at = ? WHERE channel_id = ?",
                            (display_name, datetime.now().isoformat(), channel_id)
                        )
                        conn.commit()
                    return {"channel_id": row[0], "display_name": display_name, "balance": row[2]}
                else:
                    # 新規登録
                    conn.execute(
                        "INSERT INTO users (channel_id, display_name, balance) VALUES (?, ?, ?)",
                        (channel_id, display_name, INITIAL_BALANCE)
                    )
                    conn.commit()
                    logger.info("新規ユーザー登録: %s (%s)", display_name, channel_id)
                    return {
                        "channel_id": channel_id,
                        "display_name": display_name,
                        "balance": INITIAL_BALANCE,
                    }
            finally:
                conn.close()

    def get_balance(self, channel_id: str) -> Optional[int]:
        """指定ユーザーの残高を返す（未登録なら None）"""
        with self._lock:
            conn = self._connect()
            try:
                cursor = conn.execute(
                    "SELECT balance FROM users WHERE channel_id = ?",
                    (channel_id,)
                )
                row = cursor.fetchone()
                return row[0] if row else None
            finally:
                conn.close()

    def update_balance(self, channel_id: str, delta: int) -> Optional[int]:
        """
        残高を差分更新する。

        Args:
            channel_id: ユーザーID
            delta: 正なら増加、負なら減少（残高は0未満にならない）

        Returns:
            更新後の残高。ユーザーが存在しない場合は None。
        """
        with self._lock:
            conn = self._connect()
            try:
                cursor = conn.execute(
                    "SELECT balance FROM users WHERE channel_id = ?",
                    (channel_id,)
                )
                row = cursor.fetchone()
                if row is None:
                    return None

                new_balance = max(0, row[0] + delta)
                conn.execute(
                    "UPDATE users SET balance = ?, updated_at = ? WHERE channel_id = ?",
                    (new_balance, datetime.now().isoformat(), channel_id)
                )
                conn.commit()
                return new_balance
            finally:
                conn.close()

    def get_ranking(self, limit: int = 5) -> List[Tuple[str, int]]:
        """
        残高ランキングを返す。

        Returns:
            [(display_name, balance), ...] の降順リスト
        """
        with self._lock:
            conn = self._connect()
            try:
                cursor = conn.execute(
                    "SELECT display_name, balance FROM users ORDER BY balance DESC LIMIT ?",
                    (limit,)
                )
                return cursor.fetchall()
            finally:
                conn.close()

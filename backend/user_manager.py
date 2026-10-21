"""ユーザー管理（Postgres / SQLite）

DATABASE_URL が設定されていれば Postgres（Neon など外部DB）に保存する。
Render の無課金プランはディスクが一時領域で、再デプロイや無通信15分の
自動スリープからの復帰でファイルが消えるため、SQLite のままだと所持金が
リセットされる。未設定ならローカル開発用に SQLite (users.db) を使う。
"""

import hashlib
import os
import sqlite3
import threading
import time
import logging
from typing import Optional, List, Tuple, Dict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

DB_PATH = "users.db"
DATABASE_URL = os.environ.get("DATABASE_URL", "")
INITIAL_BALANCE = 10_000
BROKE_THRESHOLD = 100
RESTORE_MINUTES = 10

# 無通信がこの秒数続いたらPostgresの接続を閉じる。
#
# Neon は「5分間なにも無ければコンピュートを止める（scale to zero）」が、
# 接続が開いたままだと活動中とみなされて止まらないことがある。
# こちらのバックエンドはRenderで24時間動いていて、DBを触るのはレースの
# 精算とランキング更新のときだけなのに、接続を張りっぱなしにしていた。
# それだとコンピュートが24時間動き続け、無料枠（月100 CU時間）を
# 最小構成の0.25 CUでも月182時間ぶん使ってしまう計算になる。
#
# Neonの5分より十分手前で閉じておけば、誰も遊んでいない間は止まる。
# 閉じたあとの再接続は _run が面倒をみる（TLSハンドシェイクのぶん
# 最初の1クエリが遅くなるだけ）。
PG_IDLE_CLOSE_SECONDS = int(os.environ.get("PG_IDLE_CLOSE_SECONDS", "60"))

# 変更をまとめてDBへ書き出す間隔。
#
# Neon の無料枠は「コンピュートが起きていた時間（CU時間）」で消費される。
# クエリの回数ではないので、問い合わせを軽くしても減らない。減らすには
# DBをまったく触らない時間を5分以上つくり、Neonをスリープさせるしかない。
#
# そこで users テーブルを丸ごとメモリに載せ、読み取りは全部メモリから返し、
# 書き込みは溜めてこの間隔でまとめて流す。人が遊んでいる間もDBは
# 「この間隔に1回、数秒」しか触らないので、残りはスリープできる。
#
# 代償は、プロセスが落ちたとき最後の書き出しから後の増減が失われること。
# デプロイや通常終了では shutdown で書き出すので、落ちるのは異常終了のときだけ。
FLUSH_SECONDS = int(os.environ.get("DB_FLUSH_SECONDS", "0")) or None


def public_id(user_id: str) -> str:
    """他のプレイヤーに見せてよい識別子。

    user_id はブラウザの localStorage に入っているセッションIDそのもので、
    知られるとその人として入れてしまう。ランキングや払い戻し一覧など全員に
    配る情報には、元に戻せないこの値を使う（名前は重複しうるので見分けに使えない）。
    """
    return hashlib.sha256(user_id.encode()).hexdigest()[:12]


class UserManager:
    def __init__(self, db_path: str = DB_PATH, database_url: str = DATABASE_URL):
        self.db_path = db_path
        self.database_url = database_url
        self._pg = bool(database_url)
        self._lock = threading.Lock()
        # 外部DBは接続のたびにTLSハンドシェイクが走るので、接続は使い回す。
        # ただし張りっぱなしだとNeonがスリープできないので、
        # 無通信が続いたら閉じる（_idle_closer）。
        self._conn = None
        self._last_used = time.monotonic()

        # users テーブルの内容をまるごと持つ。読み取りはここからだけ。
        # {user_id: {"display_name", "balance", "created_at", "updated_at", "broke_at"}}
        self._cache: Dict[str, dict] = {}
        self._dirty: set = set()
        # DBから読み込めているか。読めていないまま書き出すと、
        # 既存ユーザーの残高を初期値で上書きしてしまうので書き出さない。
        self._loaded = False
        self._cache_lock = threading.Lock()

        self._init_db()
        self._load_all()

        self._flush_seconds = FLUSH_SECONDS or (1800 if self._pg else 5)
        threading.Thread(target=self._flusher, daemon=True).start()
        if self._pg and PG_IDLE_CLOSE_SECONDS > 0:
            threading.Thread(target=self._idle_closer, daemon=True).start()
        logger.info("UserManager: %s / %d件 読み込み / %d秒ごとに書き出し",
                    "Postgres" if self._pg else f"SQLite ({db_path})",
                    len(self._cache), self._flush_seconds)

    def connection_state(self) -> dict:
        """接続の状態。/health から見て、Neonがスリープできているかを確認する。

        ロックは取らない。_run がクエリ中に握っているので、
        ここで待つと /health がクエリに巻き込まれて遅くなる。
        読むのは2つの値だけで、ずれても判断を誤らせない。
        """
        return {
            "backend": "postgres" if self._pg else "sqlite",
            "open": self._conn is not None,
            "idle_sec": int(time.monotonic() - self._last_used),
            "close_after_sec": PG_IDLE_CLOSE_SECONDS if self._pg else None,
        }

    def close_if_idle(self) -> bool:
        """無通信が続いていれば接続を閉じる。閉じたら True。"""
        with self._lock:
            if self._conn is None:
                return False
            if time.monotonic() - self._last_used < PG_IDLE_CLOSE_SECONDS:
                return False
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
            logger.info("DB接続を閉じた（%d秒以上の無通信）", PG_IDLE_CLOSE_SECONDS)
            return True

    def _idle_closer(self):
        # 見張る間隔はしきい値の1/3程度。短すぎても無駄なので1秒以上、
        # 長すぎると閉じるのが遅れるので30秒以下にする。
        # 既定の60秒なら20秒おき。
        interval = max(1, min(PG_IDLE_CLOSE_SECONDS // 3, 30))
        while True:
            time.sleep(interval)
            try:
                self.close_if_idle()
            except Exception as e:  # 見張り役がここで死なないように
                logger.warning("接続のクローズに失敗: %s", e)

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
            self._last_used = time.monotonic()
            for attempt in (1, 2):
                try:
                    # 接続を張るところも再試行の対象にする。無通信で閉じたあとは
                    # ほぼ毎回ここで張り直すので、一瞬の失敗で処理ごと落とさない
                    if self._conn is None:
                        self._conn = self._connect()
                    result = fn(self._conn)
                    self._conn.commit()
                    self._last_used = time.monotonic()
                    return result
                except Exception as e:
                    try:
                        if self._conn is not None:
                            self._conn.rollback()
                    except Exception:
                        pass
                    if attempt == 2 or not self._is_connection_error(e):
                        raise
                    logger.warning("DB接続を張り直します: %s", e)
                    try:
                        if self._conn is not None:
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
        """テーブルが無ければ作る。

        DBが落ちていても起動できるように、失敗しても例外は投げない。
        本番ではテーブルは既にあるので、ここで作れなくても支障はない。
        作れていない状態での書き出しは flush 側が _loaded で止める。
        """
        try:
            self._create_table()
        except Exception as e:
            logger.warning("テーブルを用意できません（DBが落ちている可能性）: %s", e)

    def _create_table(self):
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

    # ── メモリ上の users（読み取りは全部ここから） ────────────────────

    def _load_all(self):
        """起動時に users テーブルを丸ごと読み込む。

        失敗しても例外は投げない（DBが落ちていてもゲームは遊べるようにする）。
        読めていない間は書き出しもしない。既存ユーザーの残高を
        初期値で上書きしてしまうため。
        """
        try:
            rows = self._run(lambda conn: self._exec(
                conn,
                "SELECT user_id, display_name, balance, created_at, updated_at, broke_at FROM users",
            ).fetchall())
        except Exception as e:
            logger.warning("usersを読み込めません（DBが落ちている可能性）: %s", e)
            return
        with self._cache_lock:
            for uid, name, balance, created, updated, broke in rows:
                # DBにある値を正とする。読めていなかった間にメモリだけで
                # 作られた人は、DBに無ければそのまま残す（次の書き出しで入る）
                self._cache[uid] = {
                    "display_name": name, "balance": balance,
                    "created_at": created, "updated_at": updated, "broke_at": broke,
                }
                self._dirty.discard(uid)
            self._loaded = True

    def _flusher(self):
        while True:
            time.sleep(max(1, self._flush_seconds))
            try:
                self.flush()
            except Exception as e:
                logger.warning("書き出しに失敗（次回また試す）: %s", e)

    def flush(self) -> int:
        """溜まっている変更をまとめてDBへ書く。書いた件数を返す。

        1回の接続・1トランザクションで済ませる。これが済めば
        _idle_closer が接続を閉じ、Neonはスリープに入れる。
        """
        if not self._loaded:
            # 読み込めていないので、まず読み込みから
            self._load_all()
            if not self._loaded:
                return 0
        with self._cache_lock:
            targets = [(uid, dict(self._cache[uid])) for uid in self._dirty if uid in self._cache]
        if not targets:
            return 0

        def fn(conn):
            for uid, u in targets:
                # 無ければINSERT、あればUPDATE（SQLiteとPostgresの両対応で素朴に書く）
                exists = self._exec(
                    conn, "SELECT 1 FROM users WHERE user_id = ?", (uid,)
                ).fetchone()
                if exists:
                    self._exec(
                        conn,
                        "UPDATE users SET display_name = ?, balance = ?, "
                        "updated_at = ?, broke_at = ? WHERE user_id = ?",
                        (u["display_name"], u["balance"], u["updated_at"], u["broke_at"], uid),
                    )
                else:
                    self._exec(
                        conn,
                        "INSERT INTO users (user_id, display_name, balance, created_at, updated_at, broke_at) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (uid, u["display_name"], u["balance"],
                         u["created_at"], u["updated_at"], u["broke_at"]),
                    )
            return len(targets)

        written = self._run(fn)
        with self._cache_lock:
            for uid, _ in targets:
                self._dirty.discard(uid)
        logger.info("%d件をDBへ書き出した", written)
        return written

    def pending_writes(self) -> int:
        with self._cache_lock:
            return len(self._dirty)

    def _touch(self, user_id: str, **changes):
        """メモリ上の1件を更新して、書き出し対象に入れる。呼び出し側でロックを握ること。"""
        u = self._cache[user_id]
        u.update(changes)
        u["updated_at"] = datetime.now().isoformat()
        self._dirty.add(user_id)

    # ── 以下、外から使う操作（すべてメモリ上で完結する） ──────────────

    def get_or_create_user(self, user_id: str, display_name: str) -> dict:
        with self._cache_lock:
            u = self._cache.get(user_id)
            if u is None:
                now = datetime.now().isoformat()
                self._cache[user_id] = {
                    "display_name": display_name, "balance": INITIAL_BALANCE,
                    "created_at": now, "updated_at": now, "broke_at": None,
                }
                self._dirty.add(user_id)
                return {"user_id": user_id, "display_name": display_name,
                        "balance": INITIAL_BALANCE}
            if u["display_name"] != display_name:
                self._touch(user_id, display_name=display_name)
            return {"user_id": user_id, "display_name": display_name,
                    "balance": u["balance"]}

    def get_balance(self, user_id: str) -> Optional[int]:
        with self._cache_lock:
            u = self._cache.get(user_id)
            return u["balance"] if u else None

    def update_balance(self, user_id: str, delta: int) -> Optional[int]:
        with self._cache_lock:
            u = self._cache.get(user_id)
            if u is None:
                return None
            new_balance = max(0, u["balance"] + delta)
            if new_balance < BROKE_THRESHOLD and u["broke_at"] is None:
                broke_at = datetime.now().isoformat()
            elif new_balance >= BROKE_THRESHOLD:
                broke_at = None
            else:
                broke_at = u["broke_at"]
            self._touch(user_id, balance=new_balance, broke_at=broke_at)
            return new_balance

    def restore_broke_users(self) -> List[Tuple[str, str]]:
        threshold = (datetime.now() - timedelta(minutes=RESTORE_MINUTES)).isoformat()
        restored = []
        with self._cache_lock:
            for uid, u in self._cache.items():
                if u["broke_at"] is not None and u["broke_at"] <= threshold:
                    restored.append((uid, u["display_name"]))
            for uid, _ in restored:
                self._touch(uid, balance=INITIAL_BALANCE, broke_at=None)
        return restored

    def restore_user(self, user_id: str) -> Optional[int]:
        """残高がBROKE_THRESHOLD未満のユーザーを即時リセット（手動リクエスト用）"""
        with self._cache_lock:
            u = self._cache.get(user_id)
            if u is None or u["balance"] >= BROKE_THRESHOLD:
                return None
            self._touch(user_id, balance=INITIAL_BALANCE, broke_at=None)
            return INITIAL_BALANCE

    def get_ranking(
        self, limit: int = 5, user_ids: Optional[List[str]] = None
    ) -> List[Tuple[str, int, str]]:
        """残高ランキング [(表示名, 残高, public_id)]。user_ids を渡すとその中だけで順位をつける（オンライン中の人など）"""
        if user_ids is not None and not user_ids:
            return []
        with self._cache_lock:
            if user_ids is None:
                items = list(self._cache.items())
            else:
                wanted = set(user_ids)
                items = [(uid, u) for uid, u in self._cache.items() if uid in wanted]
            items.sort(key=lambda kv: kv[1]["balance"], reverse=True)
            return [(u["display_name"], u["balance"], public_id(uid))
                    for uid, u in items[:limit]]

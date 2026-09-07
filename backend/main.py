"""FastAPI WebSocket サーバー"""

import asyncio
import datetime
import json
import logging
import os
import time
import uuid
from typing import Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from game_engine import GameEngine

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="競馬ゲーム API")

ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Connection manager ────────────────────────────────────────────────

class ConnManager:
    def __init__(self):
        self._conns: Dict[str, WebSocket] = {}

    async def send(self, user_id: str, msg: dict):
        ws = self._conns.get(user_id)
        if not ws:
            return
        try:
            await ws.send_text(json.dumps(msg, ensure_ascii=False))
        except Exception:
            self._conns.pop(user_id, None)

    async def broadcast(self, msg: dict):
        data = json.dumps(msg, ensure_ascii=False)
        dead = []
        for uid, ws in list(self._conns.items()):
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(uid)
        for uid in dead:
            self._conns.pop(uid, None)

    async def close_all(self, msg: dict | None = None):
        for uid, ws in list(self._conns.items()):
            try:
                if msg:
                    await ws.send_text(json.dumps(msg, ensure_ascii=False))
                await ws.close(code=1001)
            except Exception:
                pass
            self._conns.pop(uid, None)

    def add(self, user_id: str, ws: WebSocket):
        self._conns[user_id] = ws

    def remove(self, user_id: str):
        self._conns.pop(user_id, None)

    @property
    def count(self) -> int:
        return len(self._conns)


manager = ConnManager()
engine: GameEngine = None   # type: ignore[assignment]

MAX_RUNTIME_HOURS     = float(os.environ.get("MAX_RUNTIME_HOURS",     "0"))
IDLE_SHUTDOWN_MINUTES = float(os.environ.get("IDLE_SHUTDOWN_MINUTES", "0"))

# 休止のしかた。
#   0 (既定, Render): プロセスは生かしたままレースだけ止める「休止モード」。
#   1 (Railway など): 従来どおり os._exit(0) でプロセスごと終了する。
# Render はプロセスが終了すると "Application exited early" の障害アラートを送り、
# インスタンスを自動再起動する。起動直後にまた終了すると再起動ループになるため、
# Render では終了させないのが正しい。無課金プランは無通信15分で自動スリープする
# ので、休止モードでもインスタンス時間は消費しない。
EXIT_ON_SHUTDOWN = os.environ.get("EXIT_ON_SHUTDOWN", "0") == "1"

# JST夜間停止（例: 1〜8時）。0にすると無効。
# 既定は無効。Railway では停止＝課金停止だったが、Render の無課金プランは
# 無通信15分で自動スリープするため、夜間に止めても何も節約できない。
# 一方で「おやすみ中」画面の時間帯 (01:00-08:00 JST) は米国太平洋時間の
# 09:00-16:00 にあたり、AdSense の審査担当者にゲームが動かない状態を
# 見せることになるので、24時間動かしておく。
_JST = datetime.timezone(datetime.timedelta(hours=9))
NIGHT_START_JST = int(os.environ.get("NIGHT_START_JST", "0"))
NIGHT_END_JST   = int(os.environ.get("NIGHT_END_JST",   "8"))


def _is_night_jst() -> bool:
    hour = datetime.datetime.now(_JST).hour
    return NIGHT_START_JST > 0 and NIGHT_START_JST <= hour < NIGHT_END_JST


_idle_since: float | None = None
_had_users  = False
# 休止中はその理由が入る（"night" / "idle" / "max_runtime"）。None なら稼働中
_dormant_reason: str | None = None


def _set_dormant(reason: str):
    """レースを止めて休止する。EXIT_ON_SHUTDOWN=1 のときだけプロセスを終了する。"""
    global _dormant_reason
    if EXIT_ON_SHUTDOWN:
        logger.info("シャットダウンします (%s)", reason)
        os._exit(0)
    if _dormant_reason:
        return
    _dormant_reason = reason
    if engine:
        engine.paused = True
    logger.info("休止モードに入りました (%s)", reason)


def _wake():
    global _dormant_reason
    if not _dormant_reason:
        return
    logger.info("休止モードを解除しました (%s から復帰)", _dormant_reason)
    _dormant_reason = None
    if engine:
        engine.paused = False


def _on_user_connect():
    global _idle_since, _had_users
    _had_users = True
    _idle_since = None


def _on_user_disconnect():
    global _idle_since
    if manager.count == 0 and _had_users:
        _idle_since = time.monotonic()


async def _auto_shutdown():
    if MAX_RUNTIME_HOURS <= 0:
        return
    await asyncio.sleep(MAX_RUNTIME_HOURS * 3600)
    _set_dormant("max_runtime")


async def _night_watcher():
    if NIGHT_START_JST <= 0:
        return
    while True:
        await asyncio.sleep(60)
        if _is_night_jst():
            if _dormant_reason != "night":
                _set_dormant("night")
                # 接続中のクライアントを切る（フロントは未接続なら「おやすみ中」を出す）
                await manager.close_all({"type": "night"})
        elif _dormant_reason == "night":
            _wake()


async def _idle_shutdown_watcher():
    if IDLE_SHUTDOWN_MINUTES <= 0:
        return
    while True:
        await asyncio.sleep(30)
        if _idle_since is not None and _dormant_reason is None:
            elapsed_min = (time.monotonic() - _idle_since) / 60
            if elapsed_min >= IDLE_SHUTDOWN_MINUTES:
                _set_dormant("idle")


@app.on_event("startup")
async def startup():
    global engine
    engine = GameEngine(manager.broadcast, manager.send)
    if _is_night_jst():
        # 夜間に起動した場合は休止状態で待機する（従来はここでプロセスを終了していた）
        _set_dormant("night")
    asyncio.create_task(engine.run())
    asyncio.create_task(_auto_shutdown())
    asyncio.create_task(_idle_shutdown_watcher())
    asyncio.create_task(_night_watcher())
    logger.info("Game engine started")


@app.get("/health")
def health():
    return {"status": "ok", "dormant": _dormant_reason}


# ── WebSocket endpoint ────────────────────────────────────────────────

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    user_id: str = ""

    if _is_night_jst():
        # 夜間は接続を受けない。フロントは未接続なら「おやすみ中」画面を出す
        await websocket.send_text(json.dumps({"type": "night"}, ensure_ascii=False))
        await websocket.close(code=1001)
        return

    # アイドル休止中に誰か来たら再開する
    if _dormant_reason in ("idle", "max_runtime"):
        _wake()

    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
        msg = json.loads(raw)

        if msg.get("type") != "join":
            await websocket.close(code=1003)
            return

        name       = str(msg.get("name", "名無し"))[:20].strip() or "名無し"
        session_id = str(msg.get("session_id", ""))[:36]
        user_id    = session_id if session_id else str(uuid.uuid4())

        manager.add(user_id, websocket)
        _on_user_connect()
        user = engine.users.get_or_create_user(user_id, name)

        await websocket.send_text(json.dumps({
            "type":         "joined",
            "user_id":      user_id,
            "display_name": name,
            "balance":      user["balance"],
            "online":       manager.count,
        }, ensure_ascii=False))

        await websocket.send_text(json.dumps(engine.get_snapshot(), ensure_ascii=False))
        await manager.broadcast({"type": "online_update", "online": manager.count})

        while True:
            raw = await websocket.receive_text()
            await _handle_msg(websocket, user_id, name, json.loads(raw))

    except WebSocketDisconnect:
        pass
    except asyncio.TimeoutError:
        await websocket.close(code=1000)
    except Exception:
        logger.exception("WebSocket error (user_id=%s)", user_id)
    finally:
        if user_id:
            manager.remove(user_id)
            _on_user_disconnect()
            await manager.broadcast({"type": "online_update", "online": manager.count})


async def _handle_msg(ws: WebSocket, user_id: str, display_name: str, msg: dict):
    t = msg.get("type")

    if t == "bet":
        bet_type = msg.get("bet_type", "win")
        if bet_type not in ("win", "show"):
            await ws.send_text(json.dumps(
                {"type": "bet_result", "ok": False, "error": "無効な馬券種別"},
                ensure_ascii=False
            ))
            return
        try:
            horse  = int(msg["horse"])
            amount = int(msg["amount"])
        except (KeyError, ValueError, TypeError):
            await ws.send_text(json.dumps(
                {"type": "bet_result", "ok": False, "error": "無効な値"},
                ensure_ascii=False
            ))
            return
        result = await engine.handle_bet(user_id, display_name, bet_type, horse, amount)
        await ws.send_text(json.dumps({"type": "bet_result", **result}, ensure_ascii=False))

    elif t == "get_bets":
        bets = engine.betting.get_bets_by_user(user_id)
        await ws.send_text(json.dumps({
            "type": "my_bets",
            "bets": [{"bet_type": b.bet_type, "horse": b.horse, "amount": b.amount}
                     for b in bets],
        }, ensure_ascii=False))

    elif t == "restore_request":
        if engine.phase == "betting" and engine.betting.get_bets_by_user(user_id):
            await ws.send_text(json.dumps(
                {"type": "restore_denied", "error": "馬券購入中はリセットできません"},
                ensure_ascii=False
            ))
            return
        balance = engine.users.restore_user(user_id)
        if balance is not None:
            await ws.send_text(json.dumps({"type": "restored", "balance": balance}, ensure_ascii=False))

    elif t == "ping":
        await ws.send_text(json.dumps({"type": "pong"}, ensure_ascii=False))

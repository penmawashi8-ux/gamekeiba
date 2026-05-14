"""FastAPI WebSocket サーバー"""

import asyncio
import json
import logging
import os
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

    def add(self, user_id: str, ws: WebSocket):
        self._conns[user_id] = ws

    def remove(self, user_id: str):
        self._conns.pop(user_id, None)

    @property
    def count(self) -> int:
        return len(self._conns)


manager = ConnManager()
engine: GameEngine = None   # type: ignore[assignment]


@app.on_event("startup")
async def startup():
    global engine
    engine = GameEngine(manager.broadcast, manager.send)
    asyncio.create_task(engine.run())
    logger.info("Game engine started")


@app.get("/health")
def health():
    return {"status": "ok"}


# ── WebSocket endpoint ────────────────────────────────────────────────

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    user_id: str = ""

    try:
        # 最初のメッセージで join を待つ（30秒タイムアウト）
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
        msg = json.loads(raw)

        if msg.get("type") != "join":
            await websocket.close(code=1003)
            return

        name       = str(msg.get("name", "名無し"))[:20].strip() or "名無し"
        session_id = str(msg.get("session_id", ""))[:36]
        user_id    = session_id if session_id else f"u_{name}"

        manager.add(user_id, websocket)
        user = engine.users.get_or_create_user(user_id, name)

        # ウェルカムメッセージ
        await websocket.send_text(json.dumps({
            "type":         "joined",
            "user_id":      user_id,
            "display_name": name,
            "balance":      user["balance"],
            "online":       manager.count,
        }, ensure_ascii=False))

        # 現在のゲーム状態を送信
        await websocket.send_text(json.dumps(engine.get_snapshot(), ensure_ascii=False))

        # オンライン人数を全員に通知
        await manager.broadcast({"type": "online_update", "online": manager.count})

        # メッセージループ
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

    elif t == "ping":
        await ws.send_text(json.dumps({"type": "pong"}, ensure_ascii=False))

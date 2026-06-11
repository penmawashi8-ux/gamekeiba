#!/usr/bin/env python3
"""競馬ゲームを自動プレイし、Playwrightで録画 + イベントログを記録する"""
import asyncio
import json
import os
import shutil
import time

import websockets
from playwright.async_api import async_playwright

WS_URL = "ws://localhost:8000/ws"
APP_URL = "http://localhost:3000"
CHROME = os.environ.get("CHROME_PATH") or None  # 未指定ならPlaywright標準のChromium
OUT = os.environ.get("VIDEO_OUT", "/home/user/video_work")
PLAYER_NAME = "クロードAI"

events = []
state = {"phase": None, "countdown": None, "horses": [], "win_odds": {}, "show_odds": {}}


def log(kind, payload=None):
    events.append({"t": time.time(), "kind": kind, "data": payload})
    print(f"[{time.strftime('%H:%M:%S')}] {kind}")


async def spy_task():
    async with websockets.connect(WS_URL) as ws:
        await ws.send(json.dumps({"type": "join", "name": "ギャラリー", "session_id": "spy-00000000"}))
        async for raw in ws:
            msg = json.loads(raw)
            mt = msg.get("type")
            if mt == "game_state":
                state.update(phase=msg["phase"], countdown=msg["countdown"],
                             horses=msg["horses"], win_odds=msg["win_odds"], show_odds=msg["show_odds"])
                if msg["horses"] and not any(e["kind"] == "horses" for e in events):
                    log("horses", msg["horses"])
                events.append({"t": time.time(), "kind": "tick",
                               "data": {"phase": msg["phase"], "countdown": msg["countdown"]}})
            elif mt == "odds_update":
                state.update(win_odds=msg["win_odds"], show_odds=msg["show_odds"])
                log("odds", {"win": msg["win_odds"], "show": msg["show_odds"]})
            elif mt == "race_update":
                if state["phase"] != "racing":
                    log("race_start")
                state["phase"] = "racing"
                events.append({"t": time.time(), "kind": "race_update", "data": msg["positions"]})
            elif mt == "results":
                state["phase"] = "results"
                log("results", {
                    "ranking": msg["ranking"], "horses": msg["horses"],
                    "win_odds": msg["win_odds"], "show_odds": msg["show_odds"],
                    "payouts": [p for p in msg["payouts"] if not p["user_id"].startswith("bot")],
                    "leaderboard": msg["leaderboard"],
                })
            elif mt == "results_countdown":
                state.update(phase="results", countdown=msg["countdown"])
                events.append({"t": time.time(), "kind": "tick",
                               "data": {"phase": "results", "countdown": msg["countdown"]}})


async def wait_for(cond, timeout=180):
    t0 = time.time()
    while not cond():
        if time.time() - t0 > timeout:
            raise TimeoutError
        await asyncio.sleep(0.1)


def favorites():
    """単勝オッズの低い順に馬番リストを返す"""
    pairs = [(int(k), v) for k, v in state["win_odds"].items() if v and v > 0]
    pairs.sort(key=lambda kv: kv[1])
    return [k for k, _ in pairs]


async def main():
    os.makedirs(OUT, exist_ok=True)
    spy = asyncio.create_task(spy_task())

    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        ctx = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            record_video_dir=OUT, record_video_size={"width": 1280, "height": 720},
            locale="ja-JP", timezone_id="Asia/Tokyo",
        )
        page = await ctx.new_page()
        log("video_open")
        await page.goto(APP_URL)
        await page.wait_for_timeout(1500)

        # ログイン
        log("typing_name")
        await page.get_by_placeholder("プレイヤー名").type(PLAYER_NAME, delay=120)
        await page.wait_for_timeout(600)
        await page.get_by_role("button", name="参加する").click()
        log("joined")

        # 馬券受付フェーズ、ボットのオッズ反映を待つ
        await wait_for(lambda: state["phase"] == "betting" and state["horses"])
        await wait_for(lambda: state["countdown"] is not None and state["countdown"] <= 27 and favorites())

        favs = favorites()
        fav1, fav2 = favs[0], favs[1]
        grid = page.locator("div.grid.grid-cols-4 > button")

        # 単勝: 2番人気に5000円
        await grid.nth(fav2 - 1).click()
        await page.wait_for_timeout(800)
        await page.get_by_role("button", name="5k", exact=True).click()
        await page.wait_for_timeout(800)
        await page.get_by_role("button", name="馬券を買う").click()
        log("bet_win", {"horse": fav2, "amount": 5000, "odds": state["win_odds"].get(str(fav2))})
        await page.wait_for_timeout(2500)

        # 複勝: 1番人気に5000円
        await page.get_by_role("button", name="複勝", exact=True).click()
        await page.wait_for_timeout(800)
        await grid.nth(fav1 - 1).click()
        await page.wait_for_timeout(800)
        await page.get_by_role("button", name="馬券を買う").click()
        log("bet_show", {"horse": fav1, "amount": 5000, "odds": state["show_odds"].get(str(fav1))})

        my_session = await page.evaluate("localStorage.getItem('keiba_session_id')")
        log("my_session", my_session)

        # クリックの自動スクロールで下がった画面をトップに戻し、レースが見えるようにする
        await page.wait_for_timeout(1500)
        await page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")

        # レース終了 → 結果表示を待つ
        await wait_for(lambda: state["phase"] == "racing", timeout=120)
        await page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
        await wait_for(lambda: state["phase"] == "results", timeout=120)
        await page.wait_for_timeout(3000)
        await page.evaluate("window.scrollTo({top: 420, behavior: 'smooth'})")
        log("scrolled_results")

        # 結果フェーズの終わり際まで映して終了
        await wait_for(lambda: state["phase"] == "results" and state["countdown"] is not None
                       and state["countdown"] <= 3, timeout=60)
        await page.wait_for_timeout(1200)
        log("video_close")
        video = page.video
        await ctx.close()
        path = await video.path()
        shutil.move(path, f"{OUT}/raw.webm")
        await browser.close()

    spy.cancel()
    with open(f"{OUT}/events.json", "w") as f:
        json.dump(events, f, ensure_ascii=False)
    print("saved", f"{OUT}/raw.webm", len(events), "events")


asyncio.run(main())

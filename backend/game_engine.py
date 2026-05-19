"""非同期ゲームエンジン（状態管理・レースループ）"""

import asyncio
import logging
import random
from typing import List, Dict, Optional, Callable, Awaitable

from horse_engine import Horse, generate_race_horses, TRACK_LENGTH
from betting import BettingManager
from user_manager import UserManager

logger = logging.getLogger(__name__)

BETTING_SECONDS  = 60
RESULTS_SECONDS  = 12
RACE_DT          = 0.05

BOT_NAMES = [
    "CPU_アラシ", "CPU_カゼマル", "CPU_ホシカゲ", "CPU_タイヨウ", "CPU_ミカヅキ",
    "CPU_ナミカゼ", "CPU_イナヅマ", "CPU_フウジン", "CPU_カミナリ", "CPU_ツムジ",
]
BOT_BET_THRESHOLD = 300000
BOT_COUNT = 400


class GameEngine:
    def __init__(
        self,
        broadcast:      Callable[[dict], Awaitable[None]],
        send_personal:  Callable[[str, dict], Awaitable[None]],
    ):
        self._broadcast     = broadcast
        self._send_personal = send_personal
        self.betting  = BettingManager()
        self.users    = UserManager()

        self.phase        = "waiting"
        self.horses: List[Horse] = []
        self.race_results: List[int] = []
        self.countdown    = 0
        self.race_number  = 0
        self._last_payouts: list = []

    async def run(self):
        while True:
            try:
                await self._betting_phase()
                await self._racing_phase()
                await self._results_phase()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Game loop error")
                await asyncio.sleep(5)

    async def _betting_phase(self):
        self.race_number += 1
        self.phase = "betting"
        self.horses = generate_race_horses(8)
        self.betting.reset()
        self._last_payouts = []
        for h in self.horses:
            h.setup_race()

        self.countdown = BETTING_SECONDS
        bot_placed = False
        while self.countdown > 0:
            await self._broadcast(self._state_msg())
            await asyncio.sleep(1)
            self.countdown -= 1
            if not bot_placed and self.countdown == BETTING_SECONDS // 2:
                await self._place_bot_bets()
                bot_placed = True

    async def _racing_phase(self):
        self.phase = "racing"
        self.race_results = []

        while len(self.race_results) < len(self.horses):
            for h in self.horses:
                if not h.finished:
                    h.update(RACE_DT)
                    if h.x >= TRACK_LENGTH:
                        h.finished = True
                        h.finish_rank = len(self.race_results) + 1
                        self.race_results.append(h.number)
            await self._broadcast(self._race_update_msg())
            await asyncio.sleep(RACE_DT)

    async def _results_phase(self):
        self.phase = "results"

        if len(self.race_results) >= 3:
            payouts = self.betting.calculate_payouts(
                self.race_results[0], self.race_results[1], self.race_results[2]
            )
            self._last_payouts = [
                {
                    "user_id":       p.user_id,
                    "display_name":  p.display_name,
                    "bet_type":      p.bet_type,
                    "horse":         p.horse,
                    "bet_amount":    p.bet_amount,
                    "payout_amount": p.payout_amount,
                    "odds":          p.odds,
                }
                for p in payouts
            ]
            totals: Dict[str, int] = {}
            for p in payouts:
                self.users.update_balance(p.user_id, p.payout_amount)
                totals[p.user_id] = totals.get(p.user_id, 0) + p.payout_amount

            for uid, total in totals.items():
                balance = self.users.get_balance(uid)
                await self._send_personal(uid, {
                    "type":    "payout_notify",
                    "payout":  total,
                    "balance": balance,
                })

        for uid, name in self.users.restore_broke_users():
            await self._send_personal(uid, {
                "type":    "restored",
                "balance": 10_000,
            })

        await self._broadcast(self._results_msg())

        self.countdown = RESULTS_SECONDS
        while self.countdown > 0:
            await self._broadcast({"type": "results_countdown", "countdown": self.countdown})
            await asyncio.sleep(1)
            self.countdown -= 1

    def _state_msg(self) -> dict:
        return {
            "type":        "game_state",
            "phase":       self.phase,
            "race_number": self.race_number,
            "countdown":   self.countdown,
            "horses":      [h.to_dict() for h in self.horses],
            "win_odds":    {str(k): v for k, v in self.betting.get_win_odds().items()},
            "show_odds":   {str(k): v for k, v in self.betting.get_show_odds().items()},
            "pools":       self.betting.get_pools(),
            "leaderboard": self.users.get_ranking(5),
        }

    def _race_update_msg(self) -> dict:
        return {
            "type":  "race_update",
            "phase": "racing",
            "positions": {
                str(h.number): {
                    "progress": min(1.0, h.x / TRACK_LENGTH),
                    "finished": h.finished,
                    "rank":     h.finish_rank,
                    "anim_t":   h.anim_t,
                }
                for h in self.horses
            },
        }

    def _results_msg(self) -> dict:
        return {
            "type":        "results",
            "phase":       "results",
            "race_number": self.race_number,
            "ranking":     self.race_results,
            "horses":      [h.to_dict() for h in self.horses],
            "win_odds":    {str(k): v for k, v in self.betting.get_win_odds().items()},
            "show_odds":   {str(k): v for k, v in self.betting.get_show_odds().items()},
            "payouts":     self._last_payouts,
            "leaderboard": self.users.get_ranking(5),
        }

    def get_snapshot(self) -> dict:
        if self.phase == "betting":
            return self._state_msg()
        if self.phase == "racing":
            return self._race_update_msg()
        if self.phase == "results":
            return self._results_msg()
        return {"type": "game_state", "phase": "waiting"}

    async def _place_bot_bets(self):
        amounts = [1000, 2000, 5000, 10000, 20000]
        strength_weights = [h.strength for h in self.horses]
        for i in range(BOT_COUNT):
            bot_id   = f"bot_{i}"
            bot_name = BOT_NAMES[i % len(BOT_NAMES)]
            horse    = random.choices(self.horses, weights=strength_weights, k=1)[0]
            amount   = random.choice(amounts)
            # 単勝:複勝 = 3:2 で同じ馬選択分布を保つ → 常に単勝オッズ > 複勝オッズ
            bet_type = random.choices(["win", "show"], weights=[3, 2], k=1)[0]
            self.betting.place_bet(bot_id, bot_name, bet_type, horse.number, amount)
        await self._broadcast({
            "type":      "odds_update",
            "win_odds":  {str(k): v for k, v in self.betting.get_win_odds().items()},
            "show_odds": {str(k): v for k, v in self.betting.get_show_odds().items()},
            "pools":     self.betting.get_pools(),
        })
        logger.info("Bot bets placed (%d bots)", BOT_COUNT)

    async def handle_bet(
        self, user_id: str, display_name: str,
        bet_type: str, horse_num: int, amount: int
    ) -> dict:
        if self.phase != "betting":
            return {"ok": False, "error": "馬券受付中ではありません"}
        if horse_num < 1 or horse_num > len(self.horses):
            return {"ok": False, "error": f"馬番は1〜{len(self.horses)}で指定してください"}
        if amount < 100 or amount > 10_000_000:
            return {"ok": False, "error": "賭け金は100〜10,000,000円で指定してください"}

        balance = self.users.get_balance(user_id)
        if balance is None:
            return {"ok": False, "error": "ユーザーが見つかりません"}
        if balance < amount:
            return {"ok": False, "error": f"残高不足（残高: {balance:,}円）"}

        new_balance = self.users.update_balance(user_id, -amount)
        self.betting.place_bet(user_id, display_name, bet_type, horse_num, amount)

        await self._broadcast({
            "type":      "odds_update",
            "win_odds":  {str(k): v for k, v in self.betting.get_win_odds().items()},
            "show_odds": {str(k): v for k, v in self.betting.get_show_odds().items()},
            "pools":     self.betting.get_pools(),
        })

        return {
            "ok":       True,
            "bet_type": bet_type,
            "horse":    horse_num,
            "amount":   amount,
            "balance":  new_balance,
        }

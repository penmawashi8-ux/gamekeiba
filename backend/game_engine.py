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
# 物理は RACE_DT ごとに進めるが、送信は N ティックに1回にする。
# 2 なら 10Hz。クライアントは受信間隔を補間して描画する。
RACE_BROADCAST_EVERY = 2

BOT_NAMES = [
    "CPU_アラシ", "CPU_カゼマル", "CPU_ホシカゲ", "CPU_タイヨウ", "CPU_ミカヅキ",
    "CPU_ナミカゼ", "CPU_イナヅマ", "CPU_フウジン", "CPU_カミナリ", "CPU_ツムジ",
]
BOT_BET_THRESHOLD = 300000
BOT_COUNT = 400

# 「全払い戻し情報」に載せる明細の上限。CPUが400体いるため的中明細が
# 400件を超え、results メッセージだけで80KB前後になっていた。
MAX_BROADCAST_PAYOUTS = 60


def _trim_payouts(payouts: List["PayoutResult"]) -> List["PayoutResult"]:  # type: ignore[name-defined]
    """ブロードキャストする払い戻し明細を間引く。

    クライアントは payouts から (1) 自分の的中明細 (2) 複勝オッズ を取り出すので、
    次の2つは必ず残す:
      - 実プレイヤーの明細（1件でも欠けると「ハズレ」と誤表示される）
      - 券種×馬番ごとに最低1件（複勝オッズの対応表が欠けないように）
    残り枠は払戻額の大きいCPU明細で埋める。
    """
    humans   = [p for p in payouts if not p.user_id.startswith("bot_")]
    bots     = [p for p in payouts if p.user_id.startswith("bot_")]

    keep: List = list(humans)
    seen = {(p.bet_type, p.horse) for p in humans}
    rest: List = []
    for p in sorted(bots, key=lambda p: -p.payout_amount):
        key = (p.bet_type, p.horse)
        if key not in seen:
            seen.add(key)
            keep.append(p)
        else:
            rest.append(p)

    room = MAX_BROADCAST_PAYOUTS - len(keep)
    if room > 0:
        keep.extend(rest[:room])
    # 元の並び順（賭けられた順）を保つ
    order = {id(p): i for i, p in enumerate(payouts)}
    return sorted(keep, key=lambda p: order[id(p)])


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
        # True の間はレースを進めない（夜間休止など）。プロセスは落とさない
        self.paused       = False
        self.horses: List[Horse] = []
        self.race_results: List[int] = []
        self.countdown    = 0
        self.race_number  = 0
        self._last_payouts: list = []

    async def run(self):
        while True:
            try:
                if self.paused:
                    self.phase = "waiting"
                    await asyncio.sleep(10)
                    continue
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
        first = True
        while self.countdown > 0:
            # 投票受付の60秒間、毎秒「馬8頭の全データ＋オッズ＋プール＋ランキング」を
            # 再送すると1.7KB×60回になる。実際に変わるのは countdown だけで、
            # オッズが動いたときは別途 odds_update を投げているため、
            # 最初の1回だけ全体を送り、以降は差分（countdown）だけにする。
            # 途中参加者には接続時に get_snapshot() で全体が渡る。
            await self._broadcast(self._state_msg() if first else self._countdown_msg())
            first = False
            await asyncio.sleep(1)
            self.countdown -= 1
            if not bot_placed and self.countdown == BETTING_SECONDS // 2:
                await self._place_bot_bets()
                bot_placed = True

    async def _racing_phase(self):
        self.phase = "racing"
        self.race_results = []

        tick = 0
        while len(self.race_results) < len(self.horses):
            finished_now = False
            for h in self.horses:
                if not h.finished:
                    h.update(RACE_DT)
                    if h.x >= TRACK_LENGTH:
                        h.finished = True
                        h.finish_rank = len(self.race_results) + 1
                        self.race_results.append(h.number)
                        finished_now = True
            tick += 1
            # 物理は RACE_DT(=20Hz) のまま、送信だけ間引く。
            # クライアント側で補間するため見た目は変わらない。
            # 着順が確定したティックは、順位表示を遅らせないよう必ず送る。
            if tick % RACE_BROADCAST_EVERY == 0 or finished_now:
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
                for p in _trim_payouts(payouts)
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
            "show_odds":   {str(k): list(v) for k, v in self.betting.get_show_odds_range().items()},
            "pools":       self.betting.get_pools(),
            "leaderboard": self.users.get_ranking(5),
        }

    def _countdown_msg(self) -> dict:
        """投票受付中の毎秒更新。変化する値だけを持つ軽い game_state。

        クライアントは未指定のフィールドを前回値のまま保持する。
        """
        return {
            "type":        "game_state",
            "phase":       self.phase,
            "race_number": self.race_number,
            "countdown":   self.countdown,
        }

    def _race_update_msg(self) -> dict:
        """レース中の位置更新。

        レース中は毎秒何回も飛ぶうえ全接続へのブロードキャストなので、
        ここのサイズがそのまま転送量になる。キー名を繰り返さない配列形式にし、
        小数も表示に必要な桁で丸める。
          p[i] = [進捗(0〜1, 小数4桁), 着順(未確定は0)]  ※並びは horses と同じ
        anim_t はクライアントが自前で進めており使われていないため送らない。
        """
        return {
            "type":  "race_update",
            "phase": "racing",
            "p": [
                [round(min(1.0, h.x / TRACK_LENGTH), 4), h.finish_rank or 0]
                for h in self.horses
            ],
        }

    def _results_msg(self) -> dict:
        return {
            "type":        "results",
            "phase":       "results",
            "race_number": self.race_number,
            "ranking":     self.race_results,
            "horses":      [h.to_dict() for h in self.horses],
            "win_odds":    {str(k): v for k, v in self.betting.get_win_odds().items()},
            "show_odds":   {str(k): list(v) for k, v in self.betting.get_show_odds_range().items()},
            "payouts":     self._last_payouts,
            "leaderboard": self.users.get_ranking(5),
        }

    def get_snapshot(self) -> dict:
        if self.phase == "betting":
            return self._state_msg()
        if self.phase == "racing":
            # _race_update_msg には馬データが含まれないため、_state_msg で馬情報を送る
            # ポジションは直後の race_update ブロードキャストで更新される
            return self._state_msg()
        if self.phase == "results":
            return self._results_msg()
        return {"type": "game_state", "phase": "waiting"}

    async def _place_bot_bets(self):
        win_amounts  = [1000, 2000, 5000, 10000, 20000]
        show_amounts = [2000, 4000, 10000, 20000, 40000]
        win_weights  = [h.strength ** 3 for h in self.horses]
        show_weights = [h.strength ** 1.5 for h in self.horses]  # 複勝: 実JRA同様に均一寄りの分布
        # 全馬に最低1件ずつ（オッズが成立しない馬をなくすため）
        for h in self.horses:
            self.betting.place_bet("bot_min", "CPU_ミニマム", "win",  h.number, 500)
            self.betting.place_bet("bot_min", "CPU_ミニマム", "show", h.number, 1000)
        # 単勝: BOT_COUNT 件（強い馬に偏重）
        for i in range(BOT_COUNT):
            horse = random.choices(self.horses, weights=win_weights, k=1)[0]
            self.betting.place_bet(
                f"bot_w_{i}", BOT_NAMES[i % len(BOT_NAMES)],
                "win", horse.number, random.choice(win_amounts),
            )
        # 複勝: 2倍の件数 × 2倍の金額（単勝より強い馬への集中度が高い）
        for i in range(BOT_COUNT * 2):
            horse = random.choices(self.horses, weights=show_weights, k=1)[0]
            self.betting.place_bet(
                f"bot_s_{i}", BOT_NAMES[i % len(BOT_NAMES)],
                "show", horse.number, random.choice(show_amounts),
            )
        await self._broadcast({
            "type":      "odds_update",
            "win_odds":  {str(k): v for k, v in self.betting.get_win_odds().items()},
            "show_odds": {str(k): list(v) for k, v in self.betting.get_show_odds_range().items()},
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
            "show_odds": {str(k): list(v) for k, v in self.betting.get_show_odds_range().items()},
            "pools":     self.betting.get_pools(),
        })

        return {
            "ok":       True,
            "bet_type": bet_type,
            "horse":    horse_num,
            "amount":   amount,
            "balance":  new_balance,
        }

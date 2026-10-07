"""非同期ゲームエンジン（状態管理・レースループ）"""

import asyncio
import logging
import random
import time
from typing import List, Dict, Optional, Callable, Awaitable

from horse_engine import Horse, generate_race_horses, TRACK_LENGTH
from betting import BettingManager
from user_manager import UserManager, public_id

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


def _human_payouts(payouts: List["PayoutResult"]) -> List["PayoutResult"]:  # type: ignore[name-defined]
    """「全払い戻し情報」に載せる明細。CPU は載せず、実プレイヤーの的中だけにする。

    以前は複勝の確定オッズをこの明細から拾っていたため CPU の明細も混ぜていたが、
    確定オッズは results の show_payout_odds で別に送るようにした。
    """
    return [p for p in payouts if not p.user_id.startswith("bot_")]


def _show_payout_odds(payouts: List["PayoutResult"]) -> Dict[str, float]:  # type: ignore[name-defined]
    """複勝の確定オッズ {馬番: 倍率}。CPU の明細も含めて拾うので、的中者がいない馬は出ない。"""
    return {str(p.horse): p.odds for p in payouts if p.bet_type == "show"}


class GameEngine:
    def __init__(
        self,
        broadcast:      Callable[[dict], Awaitable[None]],
        send_personal:  Callable[[str, dict], Awaitable[None]],
        has_users:      Optional[Callable[[], bool]] = None,
        online_user_ids: Optional[Callable[[], List[str]]] = None,
    ):
        self._broadcast     = broadcast
        self._send_personal = send_personal
        self.betting  = BettingManager()
        self.users    = UserManager()

        self.phase        = "waiting"
        # True の間はレースを進めない（夜間休止など）。プロセスは落とさない
        self.paused       = False
        # 接続者がいるかを返す。誰もいない間はレースを回さないための判定に使う。
        # 判定はレースの切れ目でのみ行うので、レース中に全員抜けても中断はしない。
        self._has_users   = has_users or (lambda: True)
        # 接続中のユーザーID一覧。オンラインランキングに使う
        self._online_user_ids = online_user_ids or (lambda: [])
        # 休止から復帰させるための合図。誰か接続したら set される。
        self._resume      = asyncio.Event()
        self.horses: List[Horse] = []
        self.race_results: List[int] = []
        self.countdown    = 0
        self.race_number  = 0
        self._last_payouts: list = []
        self._last_show_payout_odds: Dict[str, float] = {}
        # このレースの馬券の払い戻しが済んだか。済んでいない馬券はサーバー停止時に返金する
        self._settled     = True
        # メンテナンス開始時刻（UNIX秒）。None なら予定なし。
        # 開始時刻を過ぎたら、次のレースの切れ目で止まる（進行中のレースは最後までやる）
        self.maintenance_at: Optional[float] = None
        self.maintenance_active = False

    def set_paused(self, value: bool) -> None:
        self.paused = value
        if not value:
            self._resume.set()

    def notify_user_joined(self) -> None:
        """接続者が現れたことを知らせて、待機中ならレースを始めさせる。"""
        self._resume.set()

    # ── メンテナンス ──────────────────────────────────────────────

    def maintenance_msg(self) -> dict:
        return {
            "type":   "maintenance",
            # ミリ秒（ブラウザの Date にそのまま渡せる形）
            "at":     int(self.maintenance_at * 1000) if self.maintenance_at else None,
            "active": self.maintenance_active,
        }

    def _maintenance_due(self) -> bool:
        return self.maintenance_at is not None and time.time() >= self.maintenance_at

    async def schedule_maintenance(self, at: float) -> None:
        """at（UNIX秒）以降の最初のレースの切れ目で止める。全員に予告を出す。"""
        self.maintenance_at = at
        await self._broadcast(self.maintenance_msg())
        # 待機中（誰もいない等）でも開始時刻の判定ができるよう起こす
        self._resume.set()

    async def cancel_maintenance(self) -> None:
        self.maintenance_at = None
        self.maintenance_active = False
        await self._broadcast(self.maintenance_msg())
        self._resume.set()

    def refund_unsettled_bets(self) -> int:
        """払い戻し前の馬券を全額返す。サーバー停止時（デプロイ等）に呼ぶ。

        馬券は買った時点で残高から引いているので、レースの途中で止まると
        賭け金だけが消えてしまう。返金した人数を返す。
        """
        if self._settled:
            return 0
        refunds: Dict[str, int] = {}
        for b in self.betting.get_all_bets():
            if b.user_id.startswith("bot_"):
                continue
            refunds[b.user_id] = refunds.get(b.user_id, 0) + b.amount
        for uid, amount in refunds.items():
            self.users.update_balance(uid, amount)
        self._settled = True
        if refunds:
            logger.info("停止前に %d 人へ返金しました（計 %d 円）", len(refunds), sum(refunds.values()))
        return len(refunds)

    async def run(self):
        while True:
            try:
                # 誰も見ていない間はレースを回さない。
                # 判定はここ（レースの切れ目）だけなので、レース中に全員が
                # 抜けても途中で止まらず、そのレースは最後まで進む。
                if self._maintenance_due():
                    # メンテナンス開始。ここはレースの切れ目なので払い戻しは済んでいる
                    self.phase = "waiting"
                    if not self.maintenance_active:
                        self.maintenance_active = True
                        logger.info("メンテナンスのため停止しました")
                        await self._broadcast(self.maintenance_msg())
                    self._resume.clear()
                    if self._maintenance_due():
                        await self._resume.wait()
                    continue
                if self.paused or not self._has_users():
                    self.phase = "waiting"
                    self._resume.clear()
                    # クリア後にもう一度見るのは、待ちに入る直前に接続された
                    # 合図を取りこぼさないため
                    if self.paused or not self._has_users():
                        await self._resume.wait()
                    continue
                await self._betting_phase()
                await self._racing_phase()
                await self._results_phase()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Game loop error")
                # 途中で落ちたレースの馬券は払い戻されないまま次のレースで消えるので返す
                self.refund_unsettled_bets()
                await asyncio.sleep(5)

    async def _betting_phase(self):
        self.race_number += 1
        self.phase = "betting"
        self.horses = generate_race_horses(8)
        self.betting.reset()
        self._settled = False
        self._last_payouts = []
        self._last_show_payout_odds = {}
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
            # この時点で払い戻しは確定扱い（以降に止まっても返金しない）
            self._settled = True
            self._last_payouts = [
                {
                    # user_id はセッションIDそのものなので全員には配らない
                    "public_id":     public_id(p.user_id),
                    "display_name":  p.display_name,
                    "bet_type":      p.bet_type,
                    "horse":         p.horse,
                    "bet_amount":    p.bet_amount,
                    "payout_amount": p.payout_amount,
                    "odds":          p.odds,
                }
                for p in _human_payouts(payouts)
            ]
            self._last_show_payout_odds = _show_payout_odds(payouts)
            totals: Dict[str, int] = {}
            for p in payouts:
                # CPU は users テーブルにいない。外部DBへの無駄な往復（1レース数百回）を避ける
                if p.user_id.startswith("bot_"):
                    continue
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

    def online_ranking(self) -> list:
        """今接続している人だけの残高ランキング"""
        return self.users.get_ranking(5, self._online_user_ids())

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
            "online_leaderboard": self.online_ranking(),
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
            "show_payout_odds": self._last_show_payout_odds,
            "leaderboard": self.users.get_ranking(5),
            "online_leaderboard": self.online_ranking(),
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

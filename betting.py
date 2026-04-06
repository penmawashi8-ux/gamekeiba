"""
馬券・オッズ計算モジュール

パリミュチュエル方式でオッズを計算し、馬券を管理する。
  - 単勝オッズ = 全単勝売上 × 0.80 ÷ その馬の単勝売上
  - 複勝オッズ = 全複勝売上 × 0.75 ÷ その馬の複勝売上
馬券が売れるたびにリアルタイムで再計算する。
"""

import threading
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 控除率
WIN_TAKEOUT  = 0.80   # 単勝: 80%払い戻し
SHOW_TAKEOUT = 0.75   # 複勝: 75%払い戻し


@dataclass
class Bet:
    """1件の馬券情報"""
    channel_id: str
    display_name: str
    bet_type: str       # "win" | "show"
    horse1: int         # 馬番（1〜8）
    horse2: Optional[int] = None  # 未使用（互換性のため残す）
    amount: int = 0


@dataclass
class PayoutResult:
    """払い戻し結果"""
    channel_id: str
    display_name: str
    bet_type: str
    horse_label: str    # 例: "3"
    bet_amount: int
    payout_amount: int  # 払い戻し金額（元金込み）
    odds: float


class BettingManager:
    """馬券管理・オッズ計算クラス（スレッドセーフ）"""

    def __init__(self):
        self._lock = threading.Lock()
        self.reset()

    # ──────────────────────────────────────────────
    # レース管理
    # ──────────────────────────────────────────────

    def reset(self):
        """レース開始前にリセットする"""
        with self._lock:
            self._bets: List[Bet] = []
            # 単勝: {馬番: 合計賭け金}
            self._win_pool: Dict[int, int] = {}
            # 複勝: {馬番: 合計賭け金}
            self._show_pool: Dict[int, int] = {}

    # ──────────────────────────────────────────────
    # 馬券購入
    # ──────────────────────────────────────────────

    def place_win_bet(self, channel_id: str, display_name: str,
                      horse: int, amount: int) -> bool:
        """
        単勝馬券を購入する。

        Args:
            channel_id:   ユーザーID
            display_name: 表示名
            horse:        馬番（1〜8）
            amount:       賭け金

        Returns:
            True: 購入成功
        """
        if amount <= 0:
            return False
        with self._lock:
            bet = Bet(channel_id, display_name, "win", horse, None, amount)
            self._bets.append(bet)
            self._win_pool[horse] = self._win_pool.get(horse, 0) + amount
            logger.debug("単勝購入: %s 馬番%d %d円", display_name, horse, amount)
        return True

    def place_show_bet(self, channel_id: str, display_name: str,
                       horse: int, amount: int) -> bool:
        """
        複勝馬券を購入する（1〜3着に入れば的中）。

        Args:
            channel_id:   ユーザーID
            display_name: 表示名
            horse:        馬番（1〜8）
            amount:       賭け金

        Returns:
            True: 購入成功
        """
        if amount <= 0:
            return False
        with self._lock:
            bet = Bet(channel_id, display_name, "show", horse, None, amount)
            self._bets.append(bet)
            self._show_pool[horse] = self._show_pool.get(horse, 0) + amount
            logger.debug("複勝購入: %s 馬番%d %d円", display_name, horse, amount)
        return True

    # ──────────────────────────────────────────────
    # オッズ計算
    # ──────────────────────────────────────────────

    def get_win_odds(self) -> Dict[int, float]:
        """
        単勝オッズを返す。

        Returns:
            {馬番: オッズ} — 誰も買っていない馬は含まない
        """
        with self._lock:
            total = sum(self._win_pool.values())
            if total == 0:
                return {}
            result = {}
            for horse, pool in self._win_pool.items():
                if pool > 0:
                    result[horse] = round(total * WIN_TAKEOUT / pool, 1)
            return result

    def get_show_odds(self) -> Dict[int, float]:
        """
        複勝オッズを返す。

        Returns:
            {馬番: オッズ} — 誰も買っていない馬は含まない
        """
        with self._lock:
            total = sum(self._show_pool.values())
            if total == 0:
                return {}
            result = {}
            for horse, pool in self._show_pool.items():
                if pool > 0:
                    result[horse] = round(total * SHOW_TAKEOUT / pool, 1)
            return result

    def get_win_pool_total(self) -> int:
        """単勝売上合計を返す"""
        with self._lock:
            return sum(self._win_pool.values())

    def get_show_pool_total(self) -> int:
        """複勝売上合計を返す"""
        with self._lock:
            return sum(self._show_pool.values())

    # ──────────────────────────────────────────────
    # 払い戻し計算
    # ──────────────────────────────────────────────

    def calculate_payouts(self, first: int, second: int,
                          third: int) -> List[PayoutResult]:
        """
        着順に基づき全馬券の払い戻し金額を計算する。

        Args:
            first:  1着馬番
            second: 2着馬番
            third:  3着馬番

        Returns:
            払い戻し対象の PayoutResult リスト
        """
        results: List[PayoutResult] = []

        win_odds  = self.get_win_odds()
        show_odds = self.get_show_odds()
        top3 = {first, second, third}

        with self._lock:
            for bet in self._bets:
                payout = 0
                odds   = 0.0
                label  = ""

                if bet.bet_type == "win" and bet.horse1 == first:
                    # 単勝的中（最低1.0倍保証・10円単位切り捨て）
                    odds   = max(1.0, win_odds.get(first, 0.0))
                    payout = (int(bet.amount * odds) // 10) * 10
                    label  = str(first)

                elif bet.bet_type == "show" and bet.horse1 in top3:
                    # 複勝的中（1〜3着いずれか）
                    odds   = max(1.0, show_odds.get(bet.horse1, 0.0))
                    payout = (int(bet.amount * odds) // 10) * 10
                    label  = str(bet.horse1)

                if payout > 0:
                    results.append(PayoutResult(
                        channel_id=bet.channel_id,
                        display_name=bet.display_name,
                        bet_type=bet.bet_type,
                        horse_label=label,
                        bet_amount=bet.amount,
                        payout_amount=payout,
                        odds=odds,
                    ))

        return results

    def get_bets_by_user(self, channel_id: str) -> List[Bet]:
        """指定ユーザーの馬券一覧を返す"""
        with self._lock:
            return [b for b in self._bets if b.channel_id == channel_id]

    def get_all_bets(self) -> List[Bet]:
        """全馬券のコピーを返す"""
        with self._lock:
            return list(self._bets)

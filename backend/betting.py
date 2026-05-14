"""馬券・オッズ計算（パリミュチュエル方式）"""

from dataclasses import dataclass
from typing import Dict, List, Optional

WIN_TAKEOUT  = 0.80
SHOW_TAKEOUT = 0.75


@dataclass
class Bet:
    user_id: str
    display_name: str
    bet_type: str   # "win" | "show"
    horse: int
    amount: int


@dataclass
class PayoutResult:
    user_id: str
    display_name: str
    bet_type: str
    horse: int
    bet_amount: int
    payout_amount: int
    odds: float


class BettingManager:
    def __init__(self):
        self.reset()

    def reset(self):
        self._bets: List[Bet] = []
        self._win_pool: Dict[int, int] = {}
        self._show_pool: Dict[int, int] = {}

    def place_bet(self, user_id: str, display_name: str,
                  bet_type: str, horse: int, amount: int) -> bool:
        if amount <= 0:
            return False
        self._bets.append(Bet(user_id, display_name, bet_type, horse, amount))
        if bet_type == "win":
            self._win_pool[horse] = self._win_pool.get(horse, 0) + amount
        else:
            self._show_pool[horse] = self._show_pool.get(horse, 0) + amount
        return True

    def get_win_odds(self) -> Dict[int, float]:
        total = sum(self._win_pool.values())
        if total == 0:
            return {}
        return {h: max(1.0, round(total * WIN_TAKEOUT / p, 1))
                for h, p in self._win_pool.items() if p > 0}

    def get_show_odds(self) -> Dict[int, float]:
        total = sum(self._show_pool.values())
        if total == 0:
            return {}
        return {h: max(1.0, round(total * SHOW_TAKEOUT / p, 1))
                for h, p in self._show_pool.items() if p > 0}

    def get_pools(self) -> dict:
        return {
            "win":  dict(self._win_pool),
            "show": dict(self._show_pool),
            "win_total":  sum(self._win_pool.values()),
            "show_total": sum(self._show_pool.values()),
        }

    def calculate_payouts(self, first: int, second: int, third: int) -> List[PayoutResult]:
        win_odds  = self.get_win_odds()
        show_odds = self.get_show_odds()
        top3 = {first, second, third}
        results: List[PayoutResult] = []
        for bet in self._bets:
            payout = 0
            odds   = 0.0
            if bet.bet_type == "win" and bet.horse == first:
                odds   = max(1.0, win_odds.get(first, 0.0))
                payout = (int(bet.amount * odds) // 10) * 10
            elif bet.bet_type == "show" and bet.horse in top3:
                odds   = max(1.0, show_odds.get(bet.horse, 0.0))
                payout = (int(bet.amount * odds) // 10) * 10
            if payout > 0:
                results.append(PayoutResult(
                    user_id=bet.user_id,
                    display_name=bet.display_name,
                    bet_type=bet.bet_type,
                    horse=bet.horse,
                    bet_amount=bet.amount,
                    payout_amount=payout,
                    odds=odds,
                ))
        return results

    def get_bets_by_user(self, user_id: str) -> List[Bet]:
        return [b for b in self._bets if b.user_id == user_id]

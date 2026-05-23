"""馬券・オッズ計算（パリミュチュエル方式）"""

from dataclasses import dataclass
from typing import Dict, List, Tuple

WIN_TAKEOUT  = 0.80
SHOW_TAKEOUT = 0.80   # JRA複勝: 80%返還


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

    def _show_odds(self, ph: int, losing: int) -> float:
        """JRA複勝オッズ: ((W + D/3) × 0.80) / W
        W = この馬の複勝売上, D = 3着外れ馬の複勝売上合計
        """
        return max(1.0, round(((ph + losing / 3) * SHOW_TAKEOUT) / ph, 1))

    def get_show_odds_range(self) -> Dict[int, Tuple[float, float]]:
        """JRA方式複勝オッズ範囲 (min倍, max倍)。
        レース前は3着以内の組み合わせ不明なため:
          min = 最人気2頭と同着した場合（D最小 → 配当最小）
          max = 最低人気2頭と同着した場合（D最大 → 配当最大）
        """
        total = sum(self._show_pool.values())
        if total == 0:
            return {}
        result: Dict[int, Tuple[float, float]] = {}
        for h, ph in self._show_pool.items():
            if ph <= 0:
                continue
            others = sorted(
                [p for hh, p in self._show_pool.items() if hh != h and p > 0],
                reverse=True,
            )
            if len(others) >= 2:
                # 最人気2頭と同着 → D（外れ馬プール）が最小
                losing_min = max(0, total - ph - others[0] - others[1])
                # 最低人気2頭と同着 → D が最大
                losing_max = max(0, total - ph - others[-2] - others[-1])
            elif len(others) == 1:
                losing_min = losing_max = max(0, total - ph - others[0])
            else:
                losing_min = losing_max = max(0, total - ph)
            result[h] = (
                self._show_odds(ph, losing_min),
                self._show_odds(ph, losing_max),
            )
        return result

    def get_pools(self) -> dict:
        return {
            "win":  dict(self._win_pool),
            "show": dict(self._show_pool),
            "win_total":  sum(self._win_pool.values()),
            "show_total": sum(self._show_pool.values()),
        }

    def calculate_payouts(self, first: int, second: int, third: int) -> List[PayoutResult]:
        win_odds = self.get_win_odds()
        top3 = {first, second, third}

        # 複勝実配当: JRA方式 ((W + D/3) × 0.80) / W
        # D = 3着外れ馬の複勝売上合計
        show_top3 = sum(self._show_pool.get(h, 0) for h in top3)
        show_losing = sum(self._show_pool.values()) - show_top3
        show_odds_cache: Dict[int, float] = {}
        for h in top3:
            ph = self._show_pool.get(h, 0)
            show_odds_cache[h] = self._show_odds(ph, show_losing) if ph > 0 else 1.0

        results: List[PayoutResult] = []
        for bet in self._bets:
            payout = 0
            odds   = 0.0
            if bet.bet_type == "win" and bet.horse == first:
                odds   = max(1.0, win_odds.get(first, 0.0))
                payout = (int(bet.amount * odds) // 10) * 10
            elif bet.bet_type == "show" and bet.horse in top3:
                odds   = show_odds_cache[bet.horse]
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

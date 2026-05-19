"""馬券・オッズ計算（パリミュチュエル方式）"""

from dataclasses import dataclass
from typing import Dict, List, Tuple

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

    def get_show_odds_range(self) -> Dict[int, Tuple[float, float]]:
        """各馬の複勝オッズ範囲 (min倍, max倍) を返す。

        JRA方式: 3着以内馬の複勝合計額でネットプールを割る。
          実配当 = 総複勝 × 0.75 / (1着複勝額 + 2着複勝額 + 3着複勝額)
        レース前は「どの2頭と3着以内に入るか」不明なため範囲で表示:
          min = 最人気2頭と同着した場合（分母最大 → 最低配当）
          max = 最低人気2頭と同着した場合（分母最小 → 最高配当）
        """
        total = sum(self._show_pool.values())
        if total == 0:
            return {}
        net = total * SHOW_TAKEOUT
        result: Dict[int, Tuple[float, float]] = {}
        for h, ph in self._show_pool.items():
            if ph <= 0:
                continue
            others = sorted(
                [p for hh, p in self._show_pool.items() if hh != h and p > 0],
                reverse=True,
            )
            if len(others) >= 2:
                min_denom = ph + others[0] + others[1]      # 最人気2頭 → 配当最小
                max_denom = ph + others[-2] + others[-1]    # 最低人気2頭 → 配当最大
            elif len(others) == 1:
                min_denom = max_denom = ph + others[0]
            else:
                min_denom = max_denom = ph
            result[h] = (
                max(1.0, round(net / min_denom, 1)),
                max(1.0, round(net / max_denom, 1)),
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

        # 複勝実配当: ネットプール ÷ 3着以内馬の複勝合計額（JRA方式）
        net_show  = sum(self._show_pool.values()) * SHOW_TAKEOUT
        top3_pool = sum(self._show_pool.get(h, 0) for h in top3)
        show_div  = max(1.0, round(net_show / top3_pool, 1)) if top3_pool > 0 else 1.0

        results: List[PayoutResult] = []
        for bet in self._bets:
            payout = 0
            odds   = 0.0
            if bet.bet_type == "win" and bet.horse == first:
                odds   = max(1.0, win_odds.get(first, 0.0))
                payout = (int(bet.amount * odds) // 10) * 10
            elif bet.bet_type == "show" and bet.horse in top3:
                odds   = show_div   # 3着以内馬は全員同じ配当
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

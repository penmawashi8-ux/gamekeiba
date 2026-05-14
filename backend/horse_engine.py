"""馬クラスとレースシミュレーション（Pygame不要版）"""

import random
from typing import List, Optional

HORSE_NAMES: List[str] = [
    "ディープインパクト", "オルフェーヴル",     "ウオッカ",         "ジェンティルドンナ",
    "キタサンブラック",   "アーモンドアイ",     "コントレイル",     "エフフォーリア",
    "イクイノックス",     "テイエムオペラオー", "スペシャルウィーク", "グラスワンダー",
    "サイレンススズカ",   "ナリタブライアン",   "トウカイテイオー",  "オグリキャップ",
    "シンボリルドルフ",   "ミスターシービー",   "タマモクロス",     "メジロマックイーン",
    "ライスシャワー",     "ビワハヤヒデ",       "マヤノトップガン", "バブルガムフェロー",
    "エルコンドルパサー", "アグネスデジタル",   "ジャングルポケット", "ゼンノロブロイ",
    "ハルウララ",         "ヒシアマゾン",       "タニノギムレット",  "ツルマルボーイ",
]

# JRA公式枠番カラー（CSS hex）
HORSE_COLORS: List[str] = [
    "#FFFFFF",  # 1: 白
    "#1a1a1a",  # 2: 黒
    "#CC0000",  # 3: 赤
    "#0064DC",  # 4: 青
    "#FFC800",  # 5: 黄
    "#00A000",  # 6: 緑
    "#FF7800",  # 7: 橙
    "#FF69B4",  # 8: ピンク
]

RUNNING_STYLES: List[str] = ["逃げ", "先行", "差し", "追い込み"]
STRENGTH_STARS: dict = {
    1: "★☆☆☆☆", 2: "★★☆☆☆", 3: "★★★☆☆",
    4: "★★★★☆", 5: "★★★★★",
}

TRACK_LENGTH: float = 6000.0
BASE_SPEED_MIN: float = 185.0
BASE_SPEED_MAX: float = 210.0
STRENGTH_MULT: dict = {1: 0.88, 2: 0.94, 3: 1.00, 4: 1.06, 5: 1.12}


class Horse:
    def __init__(self, number: int, name: str, strength: int, running_style: str):
        self.number = number
        self.name = name
        self.color = HORSE_COLORS[number - 1]
        self.strength = strength
        self.running_style = running_style
        self.stars = STRENGTH_STARS[strength]

        self.x: float = 0.0
        self.speed: float = 0.0
        self.base_speed: float = 0.0
        self.finished: bool = False
        self.finish_rank: Optional[int] = None
        self.anim_t: float = 0.0

    def setup_race(self):
        self.base_speed = random.uniform(BASE_SPEED_MIN, BASE_SPEED_MAX)
        self.x = 0.0
        self.finished = False
        self.finish_rank = None
        self.anim_t = 0.0

    def _style_mult(self) -> float:
        progress = min(1.0, self.x / TRACK_LENGTH)
        s = self.running_style
        if s == "逃げ":
            if progress < 0.30:
                return 1.10
            elif progress < 0.60:
                return 1.10 - (progress - 0.30) * 0.933
            else:
                return max(0.62, 0.82 - (progress - 0.60) * 1.00)
        elif s == "先行":
            if progress < 0.5:
                return 1.10
            else:
                return max(0.90, 1.10 - (progress - 0.5) * 0.40)
        elif s == "差し":
            if progress < 0.55:
                return 0.80
            elif progress < 0.70:
                return 0.80 + (progress - 0.55) * 1.60
            else:
                return 1.04 + (progress - 0.70) * 1.80
        else:  # 追い込み
            if progress < 0.62:
                return 0.80
            else:
                return 0.80 + (progress - 0.62) * 2.00

    def update(self, dt: float):
        if self.finished:
            return
        sm = STRENGTH_MULT[self.strength]
        style_m = self._style_mult()
        noise = random.gauss(0, 3.0)
        eff = self.base_speed * sm * style_m + noise
        self.speed = max(BASE_SPEED_MIN * 0.55, min(BASE_SPEED_MAX * 1.50, eff))
        self.x += self.speed * dt
        self.anim_t += dt

    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "name": self.name,
            "color": self.color,
            "strength": self.strength,
            "stars": self.stars,
            "running_style": self.running_style,
        }


def generate_race_horses(count: int = 8) -> List[Horse]:
    names = random.sample(HORSE_NAMES, min(count, len(HORSE_NAMES)))
    weights = [1, 3, 5, 3, 1]
    horses = []
    for i in range(count):
        strength = random.choices([1, 2, 3, 4, 5], weights=weights)[0]
        style = random.choice(RUNNING_STYLES)
        horses.append(Horse(i + 1, names[i], strength, style))
    return horses

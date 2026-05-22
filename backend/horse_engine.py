"""馬クラスとレースシミュレーション（Pygame不要版）"""

import random
from typing import List, Optional

HORSE_NAMES: List[str] = [
    # 英語系複合名（ディープインパクト風）
    "スターブレイズ",   "ゴールデンストーム", "シルバーアロー",   "クリスタルドーン",
    "ムーンシャドウ",   "ダークホライズン",   "ウィンドチェイサー", "スカーレットリーフ",
    "ライジングムーン", "サンダーロード",     "ゴールドラッシュ", "ブラックダイヤ",
    "ロイヤルフラッグ", "トワイライトソード", "ライトニングボルト", "マジックスプリント",
    "ドリームキャッチ", "フラッシュビート",   "ネオジャスパー",   "コメットランナー",
    # 日本語冠名＋英語（キタサンブラック風）
    "ホシノブレイズ",   "カゼノダンサー",     "ツキノソルジャー", "ハナノクイーン",
    "タカノスピリット", "ミナミノスター",     "フジノルビー",     "サクラノキング",
    "ウミノエース",     "ヤマノランナー",     "アサヒグローリー", "ヒカリノソード",
    "ソラノドリーム",   "ニシノブルーム",     "カワカミフラッシュ", "マツリダジェット",
    "ハルノフレアー",   "タツノライジン",     "オウミノフリート", "コウヤノホシ",
    # 外国語・音楽用語（ウオッカ・ジェンティルドンナ風）
    "シャンパーニュ",   "カプリチョーソ",     "フォルテッシモ",   "グランドフィナーレ",
    "バラードキング",   "エスプリライト",     "マエストロドーン", "ビバーチェハート",
    "ソナタウィンド",   "ブラボーシーン",
    # ミックス系
    "エターナルロード", "グランプリスター",   "フリーダムウェイ", "アルテミスグロウ",
    "ペガサスドリーム", "オリオンライナー",   "フェニックスラン", "スパイラルウィンド",
    "サイクロンキング", "ボルケーノダッシュ", "アクアマリン",     "ラプソディブルー",
    "ソーラーエクリプス", "パラダイスエクセル",
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
CONDITION_SIGMA: float = 0.10  # レースごとの調子ばらつき（±10%程度）


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
        self.condition: float = 1.0
        self.finished: bool = False
        self.finish_rank: Optional[int] = None
        self.anim_t: float = 0.0

    def setup_race(self):
        self.base_speed = random.uniform(BASE_SPEED_MIN, BASE_SPEED_MAX)
        self.condition = max(0.70, min(1.30, random.gauss(1.0, CONDITION_SIGMA)))
        self.x = 0.0
        self.finished = False
        self.finish_rank = None
        self.anim_t = 0.0

    def _style_mult(self) -> float:
        progress = min(1.0, self.x / TRACK_LENGTH)
        s = self.running_style
        if s == "逃げ":
            # 前半強い、後半急激に落ちる / 平均 ≈ 1.00
            if progress < 0.25:
                return 1.23
            elif progress < 0.60:
                return 1.23 - (progress - 0.25) / 0.35 * 0.35   # 1.23 → 0.88
            else:
                return 0.88 - (progress - 0.60) / 0.40 * 0.13   # 0.88 → 0.75
        elif s == "先行":
            # 前半やや速い、後半落ちる / 調和平均≈1.025
            if progress < 0.50:
                return 1.04
            else:
                return 1.04 - (progress - 0.50) / 0.50 * 0.24   # 1.04 → 0.80
        elif s == "差し":
            # 前半抑えて後半伸びる / 平均 ≈ 1.00
            if progress < 0.50:
                return 0.82
            else:
                return 0.82 + (progress - 0.50) / 0.50 * 0.72   # 0.82 → 1.54
        else:  # 追い込み
            # 前半ゆっくり後半加速 / 調和平均≈1.03で他スタイルと均衡
            if progress < 0.50:
                return 0.80
            else:
                return 0.80 + (progress - 0.50) / 0.50 * 1.00   # 0.80 → 1.80

    def update(self, dt: float):
        if self.finished:
            return
        sm = STRENGTH_MULT[self.strength]
        style_m = self._style_mult()
        noise = random.gauss(0, 3.0)
        eff = self.base_speed * sm * style_m * self.condition + noise
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

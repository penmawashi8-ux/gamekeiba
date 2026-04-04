"""
馬クラスとレースアニメーション描画モジュール

draw_horse() 関数を独立させているため、
将来的に画像スプライトへの差し替えが容易。
"""

import pygame
import math
import random
from typing import List, Optional

# ──────────────────────────────────────────────────────────────────
# 馬名・カラー定数
# ──────────────────────────────────────────────────────────────────

# 全て9文字以内（日本語1文字 = 1カウント）
HORSE_NAMES: List[str] = [
    "ディープ",       "オルフェール",   "ウオッカ",       "ジェンティル",
    "キタサンブラック", "アーモンドアイ", "コントレイル",   "エフフォーリア",
    "イクイノックス", "テイエムオペラ", "スペシャルW",    "グラスワンダー",
    "サイレンス",     "ナリタブライアン", "トウカイテイオー", "オグリキャップ",
    "シンボリルドルフ", "ミスターシービー", "タマモクロス",  "メジロマックイーン",
    "ライスシャワー", "ビワハヤヒデ",   "マヤノトップガン", "バブルガムF",
    "エルコンドル",   "アグネスデジタル", "ジャングルP",    "ゼンノロブロイ",
    "ハルウララ",     "ヒシアマゾン",   "メイショウドト", "タニノギムレット",
]

# 全馬名が9文字以内であることを起動時に保証
assert all(len(n) <= 9 for n in HORSE_NAMES), \
    "HORSE_NAMES に9文字超の馬名が含まれています"

# 馬番ごとの枠色（日本の枠番カラーに準拠）
HORSE_COLORS: List[tuple] = [
    (220,  50,  50),   # 1番: 白（視認性のため赤表示）
    (50,  100, 220),   # 2番: 黒（青表示）
    (220, 80,  80),    # 3番: 赤
    (50,  180,  50),   # 4番: 青（緑表示）
    (220, 220,  50),   # 5番: 黄
    (50,  190, 200),   # 6番: 緑（水色表示）
    (220, 120,  40),   # 7番: オレンジ
    (200,  70, 200),   # 8番: ピンク（紫表示）
]

# ──────────────────────────────────────────────────────────────────
# レース設定定数
# ──────────────────────────────────────────────────────────────────

TRACK_LENGTH: int = 6000   # トラック全長（ピクセル単位）
BASE_SPEED_MIN: float = 185.0   # 基本速度の下限（強さ・脚質で上下に変動）
BASE_SPEED_MAX: float = 210.0   # 基本速度の上限

# 脚質リスト
RUNNING_STYLES: List[str] = ["逃げ", "先行", "差し", "追い込み"]
# 画面表示用略称
STYLE_SHORT: dict = {"逃げ": "逃", "先行": "先", "差し": "差", "追い込み": "追"}

# 強さ → 速度倍率
STRENGTH_MULT: dict = {1: 0.88, 2: 0.94, 3: 1.00, 4: 1.06, 5: 1.12}
# 強さ → 星表示（★☆）
STRENGTH_STARS: dict = {
    1: "★☆☆☆☆", 2: "★★☆☆☆", 3: "★★★☆☆",
    4: "★★★★☆", 5: "★★★★★",
}


# ──────────────────────────────────────────────────────────────────
# 馬クラス
# ──────────────────────────────────────────────────────────────────

class Horse:
    """競走馬クラス"""

    def __init__(self, number: int, name: str,
                 strength: int = 3, running_style: str = "先行"):
        """
        Args:
            number:        馬番（1〜8）
            name:          馬名（9文字以内）
            strength:      強さ（1〜5）
            running_style: 脚質（"逃げ"/"先行"/"差し"/"追い込み"）
        """
        self.number: int = number
        self.name: str = name[:9]   # 安全のため上限適用
        self.color: tuple = HORSE_COLORS[number - 1]
        self.strength: int = strength
        self.running_style: str = running_style

        # レース中の状態（setup_race() で初期化）
        self.x: float = 0.0
        self.speed: float = 0.0
        self.base_speed: float = 0.0
        self.finished: bool = False
        self.finish_rank: Optional[int] = None
        self.finish_time: Optional[float] = None

        # アニメーション用タイマー
        self._anim_t: float = 0.0

    # ── 表示用プロパティ ──────────────────────────
    @property
    def stars(self) -> str:
        """強さを星表示で返す（例: ★★★☆☆）"""
        return STRENGTH_STARS[self.strength]

    @property
    def style_short(self) -> str:
        """脚質の略称を返す（例: 逃、先、差、追）"""
        return STYLE_SHORT.get(self.running_style, "?")

    # ── 速度計算 ──────────────────────────────────

    def _style_mult(self) -> float:
        """
        脚質と現在進行度に応じた速度倍率を返す。

        レース全体を progress=0.0（スタート）〜1.0（ゴール）で表し、
        脚質ごとに前半・後半の速度プロファイルを変える。
        """
        progress = min(1.0, self.x / TRACK_LENGTH)
        s = self.running_style

        if s == "逃げ":
            # 前半強く、後半急失速
            if progress < 0.3:
                return 1.30
            elif progress < 0.65:
                return 1.30 - (progress - 0.3) * 0.65   # 1.30→1.07
            else:
                return max(0.78, 1.07 - (progress - 0.65) * 0.83)  # 1.07→0.78

        elif s == "先行":
            # 前半やや速く、後半ゆるやか失速
            if progress < 0.5:
                return 1.12
            else:
                return max(0.92, 1.12 - (progress - 0.5) * 0.40)

        elif s == "差し":
            # 前半抑えて直線で加速
            if progress < 0.55:
                return 0.93
            else:
                return 0.93 + (progress - 0.55) * 0.70   # 最大1.24

        else:  # 追い込み
            # 後半3割だけ猛加速
            if progress < 0.65:
                return 0.82
            else:
                return 0.82 + (progress - 0.65) * 1.80   # 最大1.47

    def setup_race(self):
        """レース開始時に速度・位置をリセットする"""
        self.base_speed = random.uniform(BASE_SPEED_MIN, BASE_SPEED_MAX)
        self.speed = self.base_speed
        self.x = 0.0
        self.finished = False
        self.finish_rank = None
        self.finish_time = None
        self._anim_t = 0.0

    def update(self, dt: float):
        """
        馬の位置を更新する。

        強さ・脚質・ランダムノイズを組み合わせて速度を計算する。
        完全実力通りにはならないよう適度なランダム性を保持。

        Args:
            dt: デルタタイム（秒）
        """
        if self.finished:
            return

        strength_mult = STRENGTH_MULT[self.strength]
        style_mult    = self._style_mult()

        # ランダムノイズ（標準偏差=3px/s 程度の揺らぎ）
        noise = random.gauss(0, 3.0)

        effective = self.base_speed * strength_mult * style_mult + noise
        # 下限・上限クランプ（速すぎ・遅すぎ防止）
        self.speed = max(BASE_SPEED_MIN * 0.55,
                         min(BASE_SPEED_MAX * 1.50, effective))
        self.x += self.speed * dt
        self._anim_t += dt


# ──────────────────────────────────────────────────────────────────
# 描画関数（差し替え可能）
# ──────────────────────────────────────────────────────────────────

def draw_horse(
    surface: pygame.Surface,
    horse: Horse,
    screen_x: float,
    screen_y: float,
    font_num: pygame.font.Font,
):
    """
    馬をシンプルな図形で描画する。

    この関数を差し替えることで画像スプライトに変更できる。

    Args:
        surface:   描画先サーフェス
        horse:     描画対象の Horse インスタンス
        screen_x:  画面上のX座標（馬の中央）
        screen_y:  画面上のY座標（レーン中央）
        font_num:  馬番表示用フォント
    """
    sx = int(screen_x)
    sy = int(screen_y)
    col = horse.color
    dark = tuple(max(0, c - 70) for c in col)

    t = horse._anim_t
    # 脚アニメーション: 前後で位相をπずらす
    leg_fwd = int(math.sin(t * 14) * 9)
    leg_bwd = int(math.sin(t * 14 + math.pi) * 9)

    # ── 胴体（楕円）
    body_rect = pygame.Rect(sx - 32, sy - 13, 60, 26)
    pygame.draw.ellipse(surface, col, body_rect)
    pygame.draw.ellipse(surface, dark, body_rect, 1)

    # ── 首・頭部
    neck_pts = [
        (sx + 22, sy - 11),
        (sx + 31, sy - 30),
        (sx + 47, sy - 26),
        (sx + 49, sy - 10),
    ]
    pygame.draw.polygon(surface, col, neck_pts)
    # 頭部（円）
    pygame.draw.circle(surface, col, (sx + 47, sy - 20), 10)
    pygame.draw.circle(surface, dark, (sx + 47, sy - 20), 10, 1)
    # 目
    pygame.draw.circle(surface, (20, 20, 20), (sx + 52, sy - 23), 2)

    # ── 尻尾
    tail_base_y = sy - 8
    pygame.draw.lines(surface, dark, False, [
        (sx - 30, tail_base_y),
        (sx - 44, tail_base_y - 12 + leg_fwd // 2),
        (sx - 50, tail_base_y + 5),
    ], 3)

    # ── 前脚 2本
    pygame.draw.line(surface, (90, 55, 20),
                     (sx + 16, sy + 11), (sx + 20 + leg_fwd, sy + 28), 3)
    pygame.draw.line(surface, (90, 55, 20),
                     (sx + 6, sy + 11), (sx + 4 + leg_bwd, sy + 28), 3)

    # ── 後脚 2本
    pygame.draw.line(surface, (90, 55, 20),
                     (sx - 12, sy + 11), (sx - 8 + leg_bwd, sy + 28), 3)
    pygame.draw.line(surface, (90, 55, 20),
                     (sx - 22, sy + 11), (sx - 26 + leg_fwd, sy + 28), 3)

    # ── 馬番（胴体上に白文字）
    num_surf = font_num.render(str(horse.number), True, (255, 255, 255))
    surface.blit(num_surf, (sx - num_surf.get_width() // 2 - 5,
                            sy - num_surf.get_height() // 2))


# ──────────────────────────────────────────────────────────────────
# ファクトリ関数
# ──────────────────────────────────────────────────────────────────

def generate_race_horses(count: int = 8) -> List[Horse]:
    """
    レース用の馬をランダム生成する。

    強さは 3（普通）が最も出やすい分布。
    脚質は均等ランダム。

    Args:
        count: 出走馬数（最大 len(HORSE_NAMES)）

    Returns:
        Horse のリスト（馬番1〜count）
    """
    names = random.sample(HORSE_NAMES, min(count, len(HORSE_NAMES)))

    # 強さ: 1〜5（3が最頻値になる正規分布で生成）
    # weights: [1, 3, 5, 3, 1] → 3が最も出やすい
    strength_weights = [1, 3, 5, 3, 1]

    horses = []
    for i in range(count):
        strength = random.choices([1, 2, 3, 4, 5], weights=strength_weights)[0]
        style    = random.choice(RUNNING_STYLES)
        horses.append(Horse(i + 1, names[i], strength, style))

    return horses

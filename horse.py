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

HORSE_NAMES: List[str] = [
    "ディープインパクト", "オルフェーヴル", "ウオッカ", "ジェンティルドンナ",
    "キタサンブラック", "アーモンドアイ", "コントレイル", "エフフォーリア",
    "イクイノックス", "テイエムオペラオー", "スペシャルウィーク", "グラスワンダー",
    "サイレンススズカ", "ナリタブライアン", "トウカイテイオー", "オグリキャップ",
    "シンボリルドルフ", "ミスターシービー", "タマモクロス", "メジロマックイーン",
    "ライスシャワー", "ビワハヤヒデ", "マヤノトップガン", "バブルガムフェロー",
    "エルコンドルパサー", "アグネスデジタル", "ジャングルポケット", "ゼンノロブロイ",
]

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
BASE_SPEED_MIN: float = 175.0   # 最低基本速度（px/秒）
BASE_SPEED_MAX: float = 225.0   # 最高基本速度（px/秒）


# ──────────────────────────────────────────────────────────────────
# 馬クラス
# ──────────────────────────────────────────────────────────────────

class Horse:
    """競走馬クラス"""

    def __init__(self, number: int, name: str):
        """
        Args:
            number: 馬番（1〜8）
            name:   馬名
        """
        self.number: int = number
        self.name: str = name
        self.color: tuple = HORSE_COLORS[number - 1]

        # レース中の状態（setup_race() で初期化）
        self.x: float = 0.0          # 現在トラック位置（px）
        self.speed: float = 0.0      # 現在速度（px/秒）
        self.base_speed: float = 0.0 # 基本速度（レース中は固定）
        self.finished: bool = False  # ゴール済み
        self.finish_rank: Optional[int] = None
        self.finish_time: Optional[float] = None

        # アニメーション用タイマー
        self._anim_t: float = 0.0

    def setup_race(self):
        """レース開始時に速度・位置をリセットしランダム速度を設定する"""
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

        わずかなランダム変動を加えることでレース展開に動きを出す。

        Args:
            dt: デルタタイム（秒）
        """
        if self.finished:
            return

        # 速度変動（白色雑音）
        noise = random.gauss(0, 4.0)
        self.speed = max(
            BASE_SPEED_MIN * 0.85,
            min(BASE_SPEED_MAX * 1.15, self.base_speed + noise),
        )
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

    Args:
        count: 出走馬数（最大 len(HORSE_NAMES)）

    Returns:
        Horse のリスト（馬番1〜count）
    """
    names = random.sample(HORSE_NAMES, min(count, len(HORSE_NAMES)))
    horses = [Horse(i + 1, names[i]) for i in range(count)]
    return horses

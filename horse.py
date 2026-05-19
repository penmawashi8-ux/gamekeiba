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
    "ディープインパクト", "オルフェーヴル",     "ウオッカ",         "ジェンティルドンナ",
    "キタサンブラック",   "アーモンドアイ",     "コントレイル",     "エフフォーリア",
    "イクイノックス",     "テイエムオペラオー", "スペシャルウィーク", "グラスワンダー",
    "サイレンススズカ",   "ナリタブライアン",   "トウカイテイオー", "オグリキャップ",
    "シンボリルドルフ",   "ミスターシービー",   "タマモクロス",     "メジロマックイーン",
    "ライスシャワー",     "ビワハヤヒデ",       "マヤノトップガン", "バブルガムフェロー",
    "エルコンドルパサー", "アグネスデジタル",   "ジャングルポケット", "ゼンノロブロイ",
    "ハルウララ",         "ヒシアマゾン",       "タニノギムレット", "ツルマルボーイ",
    "ドウデュース",       "スターズオンアース", "リバティアイランド", "ソールオリエンス",
    "タスティエーラ",     "ジャスティンパレス", "プログノーシス",   "ロードカナロア",
    "モーリス",           "キズナ",             "ゴールドシップ",   "フェノーメノ",
    "オーシャンブルー",   "ジェネラーレウーノ", "ラブリーデイ",     "ヴィルシーナ",
    "ヴィブロス",         "ショウナンパンドラ", "クロコスミア",     "ラッキーライラック",
    "アエロリット",       "ノームコア",         "サートゥルナーリア", "ワグネリアン",
    "フィエールマン",     "カレンブーケドール", "クロノジェネシス",   "デアリングタクト",
    "シャフリヤール",     "ドゥラメンテ",       "パンサラッサ",     "テーオーケインズ",
]

# 全馬名が9文字以内であることを起動時に保証
assert all(len(n) <= 9 for n in HORSE_NAMES), \
    "HORSE_NAMES に9文字超の馬名が含まれています"

# 馬番ごとの枠色（JRA公式枠番カラー）
HORSE_COLORS: List[tuple] = [
    (255, 255, 255),  # 1番: 白
    (  0,   0,   0),  # 2番: 黒
    (220,   0,   0),  # 3番: 赤
    (  0, 100, 220),  # 4番: 青
    (255, 200,   0),  # 5番: 黄
    (  0, 160,   0),  # 6番: 緑
    (255, 120,   0),  # 7番: 橙
    (255, 105, 180),  # 8番: ピンク
]

# 馬番バッジの文字色（背景が白・黄は黒文字、それ以外は白文字）
HORSE_TEXT_COLORS: List[tuple] = [
    (  0,   0,   0),  # 1番（白背景）: 黒
    (255, 255, 255),  # 2番（黒背景）: 白
    (255, 255, 255),  # 3番（赤背景）: 白
    (255, 255, 255),  # 4番（青背景）: 白
    (  0,   0,   0),  # 5番（黄背景）: 黒
    (255, 255, 255),  # 6番（緑背景）: 白
    (255, 255, 255),  # 7番（橙背景）: 白
    (255, 255, 255),  # 8番（ピンク背景）: 白
]


def horse_num_text_color(number: int) -> tuple:
    """馬番バッジの文字色を返す（背景が白・黄の場合は黒、それ以外は白）"""
    return HORSE_TEXT_COLORS[number - 1]

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
            # 序盤だけ先行より速いが、中盤から急激に失速する高リスクスタイル
            if progress < 0.30:
                return 1.10                                           # 前30%: 先頭を走る
            elif progress < 0.60:
                return 1.10 - (progress - 0.30) * 0.933             # 1.10→0.82 急降下
            else:
                return max(0.62, 0.82 - (progress - 0.60) * 1.00)   # →最小0.62 スタミナ切れ

        elif s == "先行":
            # 安定型: 前半やや速く、後半ゆるやか失速
            if progress < 0.5:
                return 1.10
            else:
                return max(0.90, 1.10 - (progress - 0.5) * 0.40)

        elif s == "差し":
            # 後半豪快に差す: 前55%は抑えて、後45%で爆発（最大1.58倍）
            if progress < 0.55:
                return 0.80
            elif progress < 0.70:
                return 0.80 + (progress - 0.55) * 1.60              # 0.80→1.04 加速準備
            else:
                return 1.04 + (progress - 0.70) * 1.80              # 最大1.58 豪快な差し！

        else:  # 追い込み
            # 後半38%だけ猛加速（最大1.56倍）
            if progress < 0.62:
                return 0.80
            else:
                return 0.80 + (progress - 0.62) * 2.00              # 最大1.56

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

    # ── 差し馬の加速エフェクト（後半60%以降）──────────────
    if horse.running_style == "差し" and TRACK_LENGTH > 0:
        progress = min(1.0, horse.x / TRACK_LENGTH)
        if progress > 0.60:
            intensity = min(1.0, (progress - 0.60) / 0.40)
            # 後ろに伸びる緑の速度ライン（3本）
            line_len = int(40 + intensity * 100)
            alpha = int(80 + intensity * 120)
            for li, offset_y in enumerate((-10, 0, 10)):
                lc = (min(255, alpha), min(255, 180 + int(75 * intensity)), min(255, alpha))
                pygame.draw.line(
                    surface, lc,
                    (sx - 32 - line_len + li * 8, sy + offset_y),
                    (sx - 32 + li * 4, sy + offset_y),
                    max(1, int(2 + intensity * 2))
                )
            # 馬体を明るいグリーンでハイライト（オーバーレイ）
            glow_col = (
                min(255, col[0] + int(60 * intensity)),
                min(255, col[1] + int(80 * intensity)),
                min(255, col[2] + int(40 * intensity)),
            )
            col = glow_col

    # アウトライン色: 白・黄系は濃いグレー、黒系は中グレー、それ以外は暗色
    brightness = sum(horse.color) // 3
    if brightness > 200:
        dark = (80, 80, 80)       # 白・黄系
    elif brightness < 60:
        dark = (110, 110, 110)    # 黒系
    else:
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
    # 目（黒馬は白目、それ以外は黒目）
    eye_col = (200, 200, 200) if brightness < 60 else (20, 20, 20)
    pygame.draw.circle(surface, eye_col, (sx + 52, sy - 23), 2)

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

    # ── 馬番（枠色に応じたコントラスト文字色）
    num_surf = font_num.render(str(horse.number), True,
                               horse_num_text_color(horse.number))
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

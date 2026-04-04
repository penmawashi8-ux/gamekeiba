"""
ゲームループ・フェーズ管理・Pygame描画モジュール

フェーズ:
  BETTING  -- 馬券受付（300秒）
  RACING   -- レースアニメーション（全馬ゴールまで）
  RESULTS  -- 結果発表・払い戻し（15秒）

解像度: 1280×720
"""

import os
import time
import queue
import logging
import math
import random
from enum import Enum, auto
from typing import List, Optional, Tuple

import pygame

from horse import Horse, draw_horse, generate_race_horses, TRACK_LENGTH, HORSE_COLORS
from betting import BettingManager, PayoutResult
from user_manager import UserManager
from youtube_client import ParsedCommand, CMD_WIN, CMD_QUINELLA, CMD_BALANCE

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────
# 画面定数
# ──────────────────────────────────────────────────────────────────
SCREEN_W, SCREEN_H = 1280, 720
FPS = 60

HEADER_H    = 50    # ヘッダー高さ
TRACK_TOP   = HEADER_H
LANE_H      = (SCREEN_H - TRACK_TOP) // 8   # 1レーン高さ ≈ 83px
NUM_HORSES  = 8

BETTING_DURATION = 300   # 馬券受付秒数
RESULTS_DURATION = 15    # 結果表示秒数

# ──────────────────────────────────────────────────────────────────
# カラーパレット
# ──────────────────────────────────────────────────────────────────
COL_BG        = ( 18,  28,  18)
COL_PANEL     = ( 28,  42,  28)
COL_HEADER    = ( 15,  25,  50)
COL_BORDER    = ( 60,  90,  60)
COL_TEXT      = (240, 240, 240)
COL_DIM       = (150, 150, 150)
COL_YELLOW    = (255, 220,  50)
COL_GREEN_BR  = ( 80, 220, 100)
COL_RED       = (220,  60,  60)
COL_ORANGE    = (255, 150,  30)
COL_GOLD      = (255, 200,   0)
COL_SILVER    = (200, 200, 200)
COL_BRONZE    = (180, 120,  60)
COL_GRASS1    = ( 45, 120,  45)
COL_GRASS2    = ( 55, 140,  55)
COL_WHITE     = (255, 255, 255)

# 日本語フォント候補パス
JAPANESE_FONT_PATHS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJKjp-Regular.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJKjp-Regular.otf",
    "/usr/share/fonts/truetype/ipafont-gothic/ipag.ttf",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    "C:/Windows/Fonts/meiryo.ttc",
    "C:/Windows/Fonts/msgothic.ttc",
    "C:/Windows/Fonts/YuGothM.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/Library/Fonts/Osaka.ttf",
]


# ──────────────────────────────────────────────────────────────────
# フェーズ定義
# ──────────────────────────────────────────────────────────────────
class Phase(Enum):
    BETTING  = auto()
    RACING   = auto()
    RESULTS  = auto()



# ──────────────────────────────────────────────────────────────────
# ヘルパー関数
# ──────────────────────────────────────────────────────────────────

def _find_japanese_font() -> Optional[str]:
    """システムから日本語フォントのパスを探す"""
    env_path = os.environ.get("GAME_FONT_PATH", "")
    if env_path and os.path.exists(env_path):
        return env_path
    for path in JAPANESE_FONT_PATHS:
        if os.path.exists(path):
            return path
    return None


def _load_font(path: Optional[str], size: int) -> pygame.font.Font:
    """フォントを読み込む。失敗時はデフォルトフォントを返す"""
    if path:
        try:
            return pygame.font.Font(path, size)
        except Exception:
            pass
    return pygame.font.SysFont(None, size)


def _draw_text_shadow(
    surface: pygame.Surface,
    text: str,
    font: pygame.font.Font,
    color: tuple,
    x: int,
    y: int,
    shadow_offset: int = 2,
    center: bool = False,
):
    """ドロップシャドウ付きテキストを描画する"""
    shadow_surf = font.render(text, True, (0, 0, 0))
    text_surf   = font.render(text, True, color)
    if center:
        x -= text_surf.get_width() // 2
        y -= text_surf.get_height() // 2
    surface.blit(shadow_surf, (x + shadow_offset, y + shadow_offset))
    surface.blit(text_surf,   (x, y))


def _draw_panel(surface: pygame.Surface, rect: pygame.Rect,
                bg: tuple = COL_PANEL, border: tuple = COL_BORDER,
                radius: int = 6):
    """角丸パネルを描画する"""
    pygame.draw.rect(surface, bg, rect, border_radius=radius)
    pygame.draw.rect(surface, border, rect, 1, border_radius=radius)


# ──────────────────────────────────────────────────────────────────
# Game クラス
# ──────────────────────────────────────────────────────────────────

class Game:
    """ゲームメインクラス。Pygameのライフサイクルと全フェーズを管理する"""

    def __init__(
        self,
        command_queue: queue.Queue,
        user_manager: UserManager,
        betting_manager: BettingManager,
        num_races: int = 10,
        test_client=None,
    ):
        """
        Args:
            command_queue:   YouTubeコマンドを受け取るキュー
            user_manager:    ユーザーDB管理
            betting_manager: 馬券・オッズ管理
            num_races:       消化レース数（達したら終了）
            test_client:     TestClient インスタンス（テストモード時）
        """
        self.command_queue   = command_queue
        self.user_manager    = user_manager
        self.betting_manager = betting_manager
        self.num_races       = num_races
        self.test_client     = test_client

        self.race_count  = 0      # 消化レース数
        self.is_running  = True   # False にすると次フレームで終了

        # Pygame 初期化
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("YouTube LIVE 競馬ゲーム")
        self.clock = pygame.time.Clock()

        # フォント読み込み
        font_path = _find_japanese_font()
        if font_path:
            logger.info("日本語フォント: %s", font_path)
        else:
            logger.warning("日本語フォントが見つかりません（英語表示になります）")
        self.f_sm  = _load_font(font_path, 18)
        self.f_md  = _load_font(font_path, 24)
        self.f_lg  = _load_font(font_path, 32)
        self.f_xl  = _load_font(font_path, 46)
        self.f_num = _load_font(font_path, 20)  # 馬番用

        # フェーズ状態
        self.phase: Phase = Phase.BETTING
        self.phase_start: float = 0.0

        # 馬・レース状態
        self.horses: List[Horse] = []
        self.finish_order: List[Horse] = []   # ゴール順
        self.camera_x: float = 0.0

        # コメント・UI状態
        self.recent_messages: List[str] = []  # 直近5件のコメント表示
        self.payout_results: List[PayoutResult] = []

    # ──────────────────────────────────────────────
    # メインループ
    # ──────────────────────────────────────────────

    def run(self):
        """Pygameメインループ。is_running=False または num_races消化で終了"""
        self._start_betting_phase()

        while self.is_running:
            dt = self.clock.tick(FPS) / 1000.0  # 秒に変換

            # イベント処理
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.is_running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.is_running = False

            # コマンドキューを処理
            self._process_commands()

            # フェーズ更新
            if self.phase == Phase.BETTING:
                self._update_betting()
            elif self.phase == Phase.RACING:
                self._update_racing(dt)
            elif self.phase == Phase.RESULTS:
                self._update_results()

            # 描画
            self.screen.fill(COL_BG)
            if self.phase == Phase.BETTING:
                self._draw_betting()
            elif self.phase == Phase.RACING:
                self._draw_racing()
            elif self.phase == Phase.RESULTS:
                self._draw_results()

            pygame.display.flip()

        pygame.quit()


    # ──────────────────────────────────────────────
    # コマンド処理
    # ──────────────────────────────────────────────

    def _process_commands(self):
        """キューからコマンドをすべて読み出して処理する"""
        while True:
            try:
                cmd: ParsedCommand = self.command_queue.get_nowait()
            except queue.Empty:
                break

            # ユーザーを取得/登録
            user = self.user_manager.get_or_create_user(
                cmd.channel_id, cmd.display_name
            )

            if cmd.command_type == CMD_BALANCE:
                bal = user["balance"]
                self._add_message(f"{cmd.display_name}: 残高 {bal:,}円")

            elif cmd.command_type in (CMD_WIN, CMD_QUINELLA):
                # 馬券受付フェーズ以外は無視
                if self.phase != Phase.BETTING:
                    continue
                # 受付終了後は無視
                if self._betting_remaining() <= 0:
                    continue
                self._handle_bet(cmd, user)

    def _handle_bet(self, cmd: ParsedCommand, user: dict):
        """馬券購入処理。残高チェック後にベット登録する"""
        amount  = cmd.amount
        balance = user["balance"]

        if balance < amount:
            self._add_message(
                f"{cmd.display_name}: 残高不足（{balance:,}円）"
            )
            return

        # 残高を先に引く
        new_bal = self.user_manager.update_balance(cmd.channel_id, -amount)

        if cmd.command_type == CMD_WIN:
            self.betting_manager.place_win_bet(
                cmd.channel_id, cmd.display_name, cmd.horse1, amount
            )
            self._add_message(
                f"{cmd.display_name}: 単勝 {cmd.horse1}番 {amount:,}円 "
                f"（残{new_bal:,}円）"
            )
        elif cmd.command_type == CMD_QUINELLA:
            self.betting_manager.place_quinella_bet(
                cmd.channel_id, cmd.display_name,
                cmd.horse1, cmd.horse2, amount
            )
            self._add_message(
                f"{cmd.display_name}: 馬連 {cmd.horse1}-{cmd.horse2}番 "
                f"{amount:,}円 （残{new_bal:,}円）"
            )

    def _add_message(self, text: str):
        """直近メッセージリストに追加（最大5件）"""
        self.recent_messages.insert(0, text)
        self.recent_messages = self.recent_messages[:5]

    # ──────────────────────────────────────────────
    # ベットフェーズ
    # ──────────────────────────────────────────────

    def _start_betting_phase(self):
        """馬券受付フェーズを開始する"""
        # レース上限チェック
        if self.race_count >= self.num_races:
            logger.info("設定レース数（%d）を消化しました", self.num_races)
            self.is_running = False
            return

        self.race_count += 1
        logger.info("=== RACE %d 開始 ===", self.race_count)

        # 馬を生成してセットアップ
        self.horses = generate_race_horses(NUM_HORSES)
        for h in self.horses:
            h.setup_race()

        self.finish_order  = []
        self.payout_results = []
        self.recent_messages = []
        self.camera_x = 0.0

        self.betting_manager.reset()
        self.phase       = Phase.BETTING
        self.phase_start = time.time()

        # テストクライアントのベット受付フラグを立てる
        if self.test_client and hasattr(self.test_client, "betting_active"):
            self.test_client.betting_active.set()

    def _betting_remaining(self) -> float:
        """馬券受付残り秒数を返す"""
        elapsed = time.time() - self.phase_start
        return max(0.0, BETTING_DURATION - elapsed)

    def _update_betting(self):
        """馬券フェーズの更新（タイムアップでレース開始）"""
        if self._betting_remaining() <= 0:
            self._start_racing_phase()


    # ──────────────────────────────────────────────
    # レースフェーズ
    # ──────────────────────────────────────────────

    def _start_racing_phase(self):
        """レースフェーズを開始する"""
        logger.info("レース開始: %s", [h.name for h in self.horses])
        self.phase       = Phase.RACING
        self.phase_start = time.time()

        # テストクライアントのベット受付を閉じる
        if self.test_client and hasattr(self.test_client, "betting_active"):
            self.test_client.betting_active.clear()

    def _update_racing(self, dt: float):
        """馬の位置更新・ゴール判定"""
        rank = len(self.finish_order) + 1
        for horse in self.horses:
            horse.update(dt)
            if not horse.finished and horse.x >= TRACK_LENGTH:
                horse.finished   = True
                horse.finish_rank = rank
                horse.finish_time = time.time() - self.phase_start
                self.finish_order.append(horse)
                logger.info("%d着: %d番 %s (%.2fs)",
                            rank, horse.number, horse.name, horse.finish_time)
                rank += 1

        # カメラを先頭馬に追従
        active = [h for h in self.horses if not h.finished]
        if active:
            lead_x = max(h.x for h in active)
        elif self.finish_order:
            lead_x = TRACK_LENGTH
        else:
            lead_x = 0
        target_cam = max(0.0, lead_x - 300)
        # ゴール後もカメラを固定
        max_cam = float(TRACK_LENGTH - SCREEN_W + 200)
        self.camera_x = min(target_cam, max_cam)

        # 全馬ゴールしたら結果フェーズへ
        if len(self.finish_order) == NUM_HORSES:
            self._start_results_phase()

    # ──────────────────────────────────────────────
    # 結果フェーズ
    # ──────────────────────────────────────────────

    def _start_results_phase(self):
        """結果フェーズを開始する（払い戻し計算）"""
        self.phase       = Phase.RESULTS
        self.phase_start = time.time()

        first  = self.finish_order[0].number
        second = self.finish_order[1].number
        logger.info("着順: 1着=%d番, 2着=%d番", first, second)

        # 払い戻し計算・残高反映
        self.payout_results = self.betting_manager.calculate_payouts(first, second)
        for pr in self.payout_results:
            self.user_manager.update_balance(pr.channel_id, pr.payout_amount)
            logger.info("払い戻し: %s %d円（%.1f倍）",
                        pr.display_name, pr.payout_amount, pr.odds)

    def _update_results(self):
        """結果フェーズの更新（表示時間終了で次レースへ）"""
        elapsed = time.time() - self.phase_start
        if elapsed >= RESULTS_DURATION:
            self._start_betting_phase()


    # ──────────────────────────────────────────────
    # 描画: ヘッダー共通
    # ──────────────────────────────────────────────

    def _draw_header(self, title: str, sub: str = "", countdown: float = -1):
        """画面上部ヘッダーを描画する"""
        rect = pygame.Rect(0, 0, SCREEN_W, HEADER_H)
        pygame.draw.rect(self.screen, COL_HEADER, rect)
        pygame.draw.line(self.screen, COL_BORDER,
                         (0, HEADER_H - 1), (SCREEN_W, HEADER_H - 1), 1)

        # タイトル
        _draw_text_shadow(self.screen, title, self.f_md, COL_YELLOW, 16, 12)

        # サブテキスト
        if sub:
            sw = self.f_sm.render(sub, True, COL_DIM).get_width()
            _draw_text_shadow(self.screen, sub, self.f_sm, COL_DIM,
                              SCREEN_W // 2 - sw // 2, 16)

        # カウントダウン
        if countdown >= 0:
            secs = int(countdown)
            col = COL_RED if secs <= 10 else (COL_ORANGE if secs <= 30 else COL_TEXT)
            cd_text = f"残り {secs}秒"
            cw = self.f_md.render(cd_text, True, col).get_width()
            _draw_text_shadow(self.screen, cd_text, self.f_md, col,
                              SCREEN_W - cw - 16, 12)

    # ──────────────────────────────────────────────
    # 描画: 馬券受付フェーズ
    # ──────────────────────────────────────────────

    def _draw_betting(self):
        """馬券受付フェーズの描画"""
        remaining = self._betting_remaining()
        self._draw_header(
            f"RACE {self.race_count}  馬券受付中",
            "  ".join(f"{h.number}:{h.name}" for h in self.horses[:4]),
            remaining,
        )

        # カウントダウン警告（60/30/10秒）
        secs = int(remaining)
        if secs in (60, 30, 10):
            pass  # ヘッダーの色変化で表現済み

        # ── 左パネル: オッズ表 ────────────────────────────
        left_rect = pygame.Rect(0, HEADER_H, SCREEN_W // 2, SCREEN_H - HEADER_H)
        _draw_panel(self.screen, left_rect, radius=0)

        lx = 10
        ly = HEADER_H + 10

        # 単勝オッズ
        _draw_text_shadow(self.screen, "【単勝オッズ】", self.f_md, COL_YELLOW, lx, ly)
        ly += 30

        win_odds = self.betting_manager.get_win_odds()

        # テーブルヘッダー
        header_cols = [("馬番", 50), ("馬名", 180), ("オッズ", 90), ("売上", 80)]
        hx = lx + 5
        for label, w in header_cols:
            surf = self.f_sm.render(label, True, COL_DIM)
            self.screen.blit(surf, (hx, ly))
            hx += w
        ly += 22
        pygame.draw.line(self.screen, COL_BORDER, (lx, ly), (lx + 420, ly), 1)
        ly += 4

        win_pool = self.betting_manager.get_win_pool_total()
        for horse in self.horses:
            odds = win_odds.get(horse.number)
            pool = self.betting_manager._win_pool.get(horse.number, 0)

            # 馬番色バッジ
            badge = pygame.Rect(lx + 5, ly + 1, 18, 18)
            pygame.draw.rect(self.screen, horse.color, badge, border_radius=3)
            num_s = self.f_sm.render(str(horse.number), True, COL_WHITE)
            self.screen.blit(num_s, (badge.x + badge.w // 2 - num_s.get_width() // 2,
                                     badge.y + 1))

            # 馬名（最大8文字）
            name_disp = horse.name[:8]
            self.screen.blit(self.f_sm.render(name_disp, True, COL_TEXT),
                             (lx + 55, ly + 1))

            # オッズ
            if odds:
                odds_col = COL_GREEN_BR if odds >= 5.0 else COL_YELLOW
                self.screen.blit(
                    self.f_sm.render(f"{odds:.1f}倍", True, odds_col),
                    (lx + 235, ly + 1)
                )
            else:
                self.screen.blit(
                    self.f_sm.render("---", True, COL_DIM),
                    (lx + 235, ly + 1)
                )

            # 売上
            self.screen.blit(
                self.f_sm.render(f"{pool:,}円", True, COL_DIM),
                (lx + 325, ly + 1)
            )
            ly += 24

        ly += 8
        pygame.draw.line(self.screen, COL_BORDER, (lx, ly), (lx + 420, ly), 1)
        ly += 8

        # 馬連オッズ（購入済み組み合わせのみ）
        quinella_odds = self.betting_manager.get_quinella_odds()
        if quinella_odds:
            _draw_text_shadow(self.screen, "【馬連オッズ】", self.f_md, COL_YELLOW, lx, ly)
            ly += 28
            for (h1, h2), odds in sorted(quinella_odds.items()):
                pool = self.betting_manager._quinella_pool.get((h1, h2), 0)
                line = f"  {h1}-{h2}番:  {odds:.1f}倍  ({pool:,}円)"
                col = COL_GREEN_BR if odds >= 5.0 else COL_YELLOW
                self.screen.blit(self.f_sm.render(line, True, col), (lx, ly))
                ly += 22
                if ly > SCREEN_H - 20:
                    break

        # 総売上
        total = win_pool + self.betting_manager.get_quinella_pool_total()
        tot_s = self.f_sm.render(f"総売上: {total:,}円", True, COL_DIM)
        self.screen.blit(tot_s, (lx, SCREEN_H - 28))

        # ── 右パネル ─────────────────────────────────────
        right_x = SCREEN_W // 2
        right_w = SCREEN_W // 2
        mid_y   = HEADER_H + (SCREEN_H - HEADER_H) // 2

        # 最新コメント（上半分）
        comment_rect = pygame.Rect(right_x, HEADER_H, right_w, mid_y - HEADER_H)
        _draw_panel(self.screen, comment_rect, radius=0)
        _draw_text_shadow(self.screen, "最新コメント", self.f_md, COL_YELLOW,
                          right_x + 10, HEADER_H + 8)
        cy = HEADER_H + 38
        if self.recent_messages:
            for msg in self.recent_messages:
                disp = msg if len(msg) <= 38 else msg[:37] + "…"
                self.screen.blit(self.f_sm.render(disp, True, COL_TEXT),
                                 (right_x + 10, cy))
                cy += 24
        else:
            self.screen.blit(
                self.f_sm.render("コメントを待っています...", True, COL_DIM),
                (right_x + 10, cy)
            )

        # 残高ランキング（下半分）
        rank_rect = pygame.Rect(right_x, mid_y, right_w, SCREEN_H - mid_y)
        _draw_panel(self.screen, rank_rect, radius=0)
        _draw_text_shadow(self.screen, "残高ランキング TOP5", self.f_md, COL_YELLOW,
                          right_x + 10, mid_y + 8)
        ry = mid_y + 38
        ranking = self.user_manager.get_ranking(5)
        medal_colors = [COL_GOLD, COL_SILVER, COL_BRONZE, COL_TEXT, COL_TEXT]
        for i, (name, bal) in enumerate(ranking):
            col = medal_colors[i]
            rank_txt = f"{i+1}位  {name[:10]}  {bal:,}円"
            self.screen.blit(self.f_md.render(rank_txt, True, col), (right_x + 10, ry))
            ry += 30

        # 区切り線（左右の境界）
        pygame.draw.line(self.screen, COL_BORDER,
                         (SCREEN_W // 2, HEADER_H), (SCREEN_W // 2, SCREEN_H), 1)


    # ──────────────────────────────────────────────
    # 描画: レースフェーズ
    # ──────────────────────────────────────────────

    def _draw_racing(self):
        """レースフェーズの描画（横スクロールアニメーション）"""
        elapsed = time.time() - self.phase_start
        self._draw_header(f"RACE {self.race_count}  レース中！",
                          f"{int(elapsed)}秒経過")

        # ── トラック背景（8レーン）
        for i in range(NUM_HORSES):
            col = COL_GRASS1 if i % 2 == 0 else COL_GRASS2
            lane_rect = pygame.Rect(
                0,
                TRACK_TOP + i * LANE_H,
                SCREEN_W,
                LANE_H,
            )
            pygame.draw.rect(self.screen, col, lane_rect)

        # ── レーン区切り線
        for i in range(1, NUM_HORSES):
            yy = TRACK_TOP + i * LANE_H
            pygame.draw.line(self.screen, (30, 80, 30),
                             (0, yy), (SCREEN_W, yy), 1)

        # ── スタートライン
        start_sx = int(-self.camera_x)
        if 0 <= start_sx <= SCREEN_W:
            pygame.draw.line(self.screen, COL_YELLOW,
                             (start_sx, TRACK_TOP), (start_sx, SCREEN_H), 3)

        # ── ゴールライン（白・市松模様風）
        finish_sx = int(TRACK_LENGTH - self.camera_x)
        if -20 <= finish_sx <= SCREEN_W + 20:
            pygame.draw.line(self.screen, COL_WHITE,
                             (finish_sx, TRACK_TOP), (finish_sx, SCREEN_H), 5)
            # ゴールポスト
            for yi in range(TRACK_TOP, SCREEN_H, 20):
                col = COL_WHITE if (yi // 20) % 2 == 0 else COL_RED
                pygame.draw.rect(self.screen, col,
                                 pygame.Rect(finish_sx - 6, yi, 12, 10))

        # ── 馬を描画（レーン中央 Y, 画面 X に変換）
        for horse in self.horses:
            lane_center_y = TRACK_TOP + (horse.number - 1) * LANE_H + LANE_H // 2
            screen_x = horse.x - self.camera_x

            # 画面外はスキップ（軽量化）
            if screen_x < -80 or screen_x > SCREEN_W + 80:
                continue

            draw_horse(self.screen, horse, screen_x, lane_center_y, self.f_num)

            # ゴール済み馬: ゴールラインの外側に停止描画
            if horse.finished:
                stop_x = max(screen_x, finish_sx + 60)
                draw_horse(self.screen, horse, stop_x, lane_center_y, self.f_num)

        # ── 右下: ゴール順情報パネル
        panel_w, panel_h = 200, NUM_HORSES * 22 + 30
        panel_rect = pygame.Rect(SCREEN_W - panel_w - 8,
                                 SCREEN_H - panel_h - 8,
                                 panel_w, panel_h)
        _draw_panel(self.screen, panel_rect, bg=(10, 20, 10, 200))
        _draw_text_shadow(self.screen, "馬番  馬名", self.f_sm, COL_DIM,
                          panel_rect.x + 8, panel_rect.y + 6)
        for i, horse in enumerate(self.horses):
            py = panel_rect.y + 26 + i * 22
            # 馬番バッジ
            b = pygame.Rect(panel_rect.x + 6, py + 1, 16, 16)
            pygame.draw.rect(self.screen, horse.color, b, border_radius=2)
            self.screen.blit(
                self.f_sm.render(str(horse.number), True, COL_WHITE),
                (b.x + b.w // 2 - 5, b.y + 1)
            )
            # 馬名（6文字まで）
            name_col = COL_GOLD if horse.finish_rank == 1 else COL_TEXT
            self.screen.blit(
                self.f_sm.render(horse.name[:6], True, name_col),
                (panel_rect.x + 28, py + 1)
            )
            # 着順
            if horse.finish_rank:
                self.screen.blit(
                    self.f_sm.render(f"{horse.finish_rank}着", True, COL_YELLOW),
                    (panel_rect.x + 155, py + 1)
                )


    # ──────────────────────────────────────────────
    # 描画: 結果フェーズ
    # ──────────────────────────────────────────────

    def _draw_results(self):
        """結果フェーズの描画"""
        elapsed   = time.time() - self.phase_start
        remaining = max(0.0, RESULTS_DURATION - elapsed)

        self._draw_header(
            f"RACE {self.race_count}  レース結果",
            countdown=remaining,
        )

        # ── 着順パネル（中央左） ──────────────────────────
        order_rect = pygame.Rect(20, HEADER_H + 10, 480, 400)
        _draw_panel(self.screen, order_rect)
        _draw_text_shadow(self.screen, "着順", self.f_lg, COL_YELLOW,
                          order_rect.x + 12, order_rect.y + 10)

        medal_cols = [COL_GOLD, COL_SILVER, COL_BRONZE]
        for i, horse in enumerate(self.finish_order):
            fy = order_rect.y + 50 + i * 40
            col = medal_cols[i] if i < 3 else COL_TEXT
            rank_s = self.f_lg.render(f"{i+1}着", True, col)
            self.screen.blit(rank_s, (order_rect.x + 10, fy))

            # 馬番バッジ
            badge = pygame.Rect(order_rect.x + 80, fy + 3, 24, 24)
            pygame.draw.rect(self.screen, horse.color, badge, border_radius=4)
            bn = self.f_sm.render(str(horse.number), True, COL_WHITE)
            self.screen.blit(bn, (badge.x + badge.w // 2 - bn.get_width() // 2,
                                  badge.y + 4))

            # 馬名
            name_surf = self.f_lg.render(horse.name[:8], True, col)
            self.screen.blit(name_surf, (order_rect.x + 115, fy))

            # 上位3頭以下は小さく
            if i >= 8:
                break

        # ── 払い戻しパネル（中央左下） ────────────────────
        pay_rect = pygame.Rect(20, HEADER_H + 420, 480, SCREEN_H - HEADER_H - 440)
        _draw_panel(self.screen, pay_rect)
        px, py_start = pay_rect.x + 10, pay_rect.y + 8

        if self.payout_results:
            _draw_text_shadow(self.screen, "払い戻し", self.f_md, COL_YELLOW,
                              px, py_start)
            py_ = py_start + 30
            for pr in self.payout_results[:6]:
                type_label = "単勝" if pr.bet_type == "win" else "馬連"
                line = (f"{pr.display_name[:8]}  "
                        f"{type_label}{pr.horse_label}  "
                        f"{pr.odds:.1f}倍  "
                        f"→ {pr.payout_amount:,}円")
                self.screen.blit(self.f_sm.render(line, True, COL_GREEN_BR),
                                 (px, py_))
                py_ += 22
        else:
            _draw_text_shadow(self.screen, "払い戻しなし", self.f_md, COL_DIM,
                              px, py_start + 10)

        # ── 単勝・馬連配当表示（中央右上） ───────────────
        div_rect = pygame.Rect(520, HEADER_H + 10, 340, 180)
        _draw_panel(self.screen, div_rect)
        dx, dy = div_rect.x + 12, div_rect.y + 10
        _draw_text_shadow(self.screen, "配当", self.f_md, COL_YELLOW, dx, dy)
        dy += 32

        first_num  = self.finish_order[0].number
        second_num = self.finish_order[1].number
        win_odds_map  = self.betting_manager.get_win_odds()
        quin_odds_map = self.betting_manager.get_quinella_odds()

        # 単勝
        w_odds = win_odds_map.get(first_num)
        w_str  = f"{w_odds:.1f}倍" if w_odds else "---"
        self.screen.blit(
            self.f_md.render(f"単勝  {first_num}番  {w_str}", True, COL_TEXT),
            (dx, dy)
        )
        dy += 34

        # 馬連
        from betting import BettingManager
        qkey = (min(first_num, second_num), max(first_num, second_num))
        q_odds = quin_odds_map.get(qkey)
        q_str  = f"{q_odds:.1f}倍" if q_odds else "---"
        self.screen.blit(
            self.f_md.render(
                f"馬連  {qkey[0]}-{qkey[1]}番  {q_str}", True, COL_TEXT
            ),
            (dx, dy)
        )

        # ── 残高ランキング（右パネル） ────────────────────
        rk_rect = pygame.Rect(520, HEADER_H + 200, 740, 480)
        _draw_panel(self.screen, rk_rect)
        _draw_text_shadow(self.screen, "残高ランキング TOP5", self.f_lg, COL_YELLOW,
                          rk_rect.x + 12, rk_rect.y + 10)

        ranking = self.user_manager.get_ranking(5)
        medal_colors = [COL_GOLD, COL_SILVER, COL_BRONZE, COL_TEXT, COL_TEXT]
        for i, (name, bal) in enumerate(ranking):
            ry = rk_rect.y + 60 + i * 70
            col = medal_colors[i]
            # 順位バッジ
            self.screen.blit(
                self.f_xl.render(f"{i+1}位", True, col),
                (rk_rect.x + 12, ry)
            )
            self.screen.blit(
                self.f_lg.render(name[:12], True, col),
                (rk_rect.x + 100, ry)
            )
            self.screen.blit(
                self.f_xl.render(f"{bal:,}円", True, col),
                (rk_rect.x + 420, ry)
            )

        # 次レースまでのカウントダウンバー
        bar_w = int((remaining / RESULTS_DURATION) * (SCREEN_W - 40))
        pygame.draw.rect(self.screen, COL_BORDER, (20, SCREEN_H - 12, SCREEN_W - 40, 8),
                         border_radius=4)
        pygame.draw.rect(self.screen, COL_GREEN_BR, (20, SCREEN_H - 12, bar_w, 8),
                         border_radius=4)


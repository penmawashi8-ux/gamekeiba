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

from horse import (Horse, draw_horse, generate_race_horses,
                   TRACK_LENGTH, HORSE_COLORS, horse_num_text_color)
from betting import BettingManager, PayoutResult
from user_manager import UserManager
from youtube_client import ParsedCommand, CMD_WIN, CMD_SHOW, CMD_BALANCE, CMD_ERROR

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────
# 画面定数
# ──────────────────────────────────────────────────────────────────
SCREEN_W, SCREEN_H = 1280, 720
FPS = 60

# 縦型モード（--vertical）では 720×1280 に切り替わる
VERTICAL_W, VERTICAL_H = 720, 1280

HEADER_H    = 72    # ヘッダー高さ（大型フォント対応で拡大）
TRACK_TOP   = HEADER_H
LEFT_PANEL_W = 720  # 馬券受付フェーズの左パネル幅（60%弱）
LANE_H      = (SCREEN_H - TRACK_TOP) // 8   # 1レーン高さ ≈ 83px
NUM_HORSES  = 8

BETTING_DURATION = 90    # 馬券受付秒数
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


def _fit_text(text: str, color: tuple, max_width: int,
              fonts: list) -> pygame.Surface:
    """
    テキストを指定幅に収まるよう描画する。

    fonts は大→小の順で渡す。全て収まらない場合は最小フォントで強制描画。

    Args:
        text:      描画するテキスト
        color:     文字色
        max_width: 許容最大幅（px）
        fonts:     試行するフォントのリスト（大きい順）

    Returns:
        描画済み pygame.Surface
    """
    for font in fonts:
        surf = font.render(text, True, color)
        if surf.get_width() <= max_width:
            return surf
    # 最小フォントで強制描画
    return fonts[-1].render(text, True, color)


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
        youtube_client=None,
        vertical: bool = False,
    ):
        """
        Args:
            command_queue:   YouTubeコマンドを受け取るキュー
            user_manager:    ユーザーDB管理
            betting_manager: 馬券・オッズ管理
            num_races:       消化レース数（達したら終了）
            test_client:     TestClient インスタンス（テストモード時）
            youtube_client:  YouTubeClient インスタンス（ステータス表示用）
        """
        self.command_queue   = command_queue
        self.user_manager    = user_manager
        self.betting_manager = betting_manager
        self.num_races       = num_races
        self.test_client     = test_client
        self.youtube_client  = youtube_client
        self.vertical        = vertical  # 縦型モード（720×1280）

        self.race_count  = 0      # 消化レース数
        self.is_running  = True   # False にすると次フレームで終了
        self._last_restore_check: float = 0.0  # 破産復活チェックの最終実行時刻

        # Pygame 初期化
        pygame.init()
        self.sw = SCREEN_W
        self.sh = SCREEN_H
        caption = "YouTube LIVE 競馬ゲーム" + (" [縦型]" if vertical else "")
        if vertical:
            self._display = pygame.display.set_mode((VERTICAL_W, VERTICAL_H))
            self.screen   = pygame.Surface((SCREEN_W, SCREEN_H))
        else:
            self._display = pygame.display.set_mode((SCREEN_W, SCREEN_H))
            self.screen   = self._display
        pygame.display.set_caption(caption)
        self.clock = pygame.time.Clock()

        # フォント読み込み
        font_path = _find_japanese_font()
        if font_path:
            logger.info("日本語フォント: %s", font_path)
        else:
            logger.warning("日本語フォントが見つかりません（英語表示になります）")
        self.f_xs  = _load_font(font_path, 22)  # 小テーブル用（旧15）
        self.f_xs2 = _load_font(font_path, 19)  # 馬名縮小フォント1（旧13）
        self.f_xs3 = _load_font(font_path, 16)  # 馬名縮小フォント2（旧11）
        self.f_sm  = _load_font(font_path, 28)  # （旧18）
        self.f_md  = _load_font(font_path, 38)  # （旧24）
        self.f_lg  = _load_font(font_path, 52)  # （旧32）
        self.f_xl  = _load_font(font_path, 72)  # （旧46）
        self.f_num = _load_font(font_path, 30)  # 馬番用（旧20）
        self.f_num_sm = _load_font(font_path, 22)  # レースパネル内の馬名用（旧15）

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

            # 破産ユーザーの残高復活チェック（30秒ごと）
            self._check_restore_broke_users()

            # フェーズ更新
            if self.phase == Phase.BETTING:
                self._update_betting()
            elif self.phase == Phase.RACING:
                self._update_racing(dt)
            elif self.phase == Phase.RESULTS:
                self._update_results()

            # 描画（縦型・横型ともに同じメソッドで1280×720 surfaceに描く）
            self.screen.fill(COL_BG)
            if self.phase == Phase.BETTING:
                self._draw_betting()
            elif self.phase == Phase.RACING:
                self._draw_racing()
            elif self.phase == Phase.RESULTS:
                self._draw_results()

            if self.vertical:
                self._composite_vertical()
            else:
                pygame.display.flip()

        pygame.quit()


    # ──────────────────────────────────────────────
    # コマンド処理
    # ──────────────────────────────────────────────

    def _check_restore_broke_users(self):
        """破産状態から10分経過したユーザーの残高を初期値に戻す（30秒ごとにチェック）"""
        import time as _time
        now = _time.time()
        if now - self._last_restore_check < 30.0:
            return
        self._last_restore_check = now

        restored = self.user_manager.restore_broke_users()
        for _, display_name in restored:
            self._add_message(
                f"[復活] {display_name}さんの残高が{10000:,}円に回復しました！"
            )

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

            if cmd.command_type == CMD_ERROR:
                # 100円単位エラー等: ユーザー登録だけして画面にエラー表示
                self._add_message(f"[エラー] {cmd.display_name}: {cmd.error_message}")
                continue

            elif cmd.command_type == CMD_BALANCE:
                bal = user["balance"]
                self._add_message(f"{cmd.display_name}: 残高 {bal:,}円")

            elif cmd.command_type in (CMD_WIN, CMD_SHOW):
                # 馬券受付フェーズ以外はエラー表示
                if self.phase != Phase.BETTING:
                    self._add_message(f"{cmd.display_name}: 馬券受付中ではありません")
                    continue
                # 受付終了後も同様
                if self._betting_remaining() <= 0:
                    self._add_message(f"{cmd.display_name}: 馬券締め切り済みです")
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

        # 残高を先に引く（失敗時は馬券を登録しない）
        new_bal = self.user_manager.update_balance(cmd.channel_id, -amount)
        if new_bal is None:
            logger.error("update_balance が None を返しました: %s", cmd.channel_id)
            return

        self._real_bettors.add(cmd.channel_id)  # 実ユーザーとして記録

        if cmd.command_type == CMD_WIN:
            self.betting_manager.place_win_bet(
                cmd.channel_id, cmd.display_name, cmd.horse1, amount
            )
            self._add_message(
                f"{cmd.display_name}: 単勝 {cmd.horse1}番 {amount:,}円 "
                f"（残{new_bal:,}円）"
            )
        elif cmd.command_type == CMD_SHOW:
            self.betting_manager.place_show_bet(
                cmd.channel_id, cmd.display_name, cmd.horse1, amount
            )
            self._add_message(
                f"{cmd.display_name}: 複勝 {cmd.horse1}番 {amount:,}円 "
                f"（残{new_bal:,}円）"
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

        # Bot自動参加管理
        self._real_bettors: set = set()   # 実際に馬券を購入したユーザーのchannel_id
        self._bot_triggered: bool = False  # 締め切り30秒前のBot出動済みフラグ

        # テストクライアントのベット受付フラグを立てる
        if self.test_client and hasattr(self.test_client, "betting_active"):
            self.test_client.betting_active.set()

    def _betting_remaining(self) -> float:
        """馬券受付残り秒数を返す"""
        elapsed = time.time() - self.phase_start
        return max(0.0, BETTING_DURATION - elapsed)

    def _update_betting(self):
        """馬券フェーズの更新（タイムアップでレース開始）"""
        remaining = self._betting_remaining()
        if remaining <= 0:
            self._start_racing_phase()
            return

        # 締め切り30秒前・実ユーザー3人以下のときBotが自動参加（1回のみ）
        if (not self._bot_triggered
                and remaining <= 30.0
                and len(self._real_bettors) <= 3):
            self._trigger_bots()
            self._bot_triggered = True


    def _trigger_bots(self):
        """
        ダミーユーザー Bot_1〜Bot_5 が自動的に馬券を購入する。

        参加者が少ない場合にオッズを成立させるために使用。
        Botの残高は無限（DB登録・払い戻しなし）。
        """
        bot_names = ["Bot_1", "Bot_2", "Bot_3", "Bot_4", "Bot_5"]
        for bot_name in bot_names:
            bot_id = f"BOT_{bot_name[-1]}"   # "BOT_1" 〜 "BOT_5"
            num_bets = random.randint(5, 15)  # 5倍（旧1〜3）
            for _ in range(num_bets):
                amount = random.choice([100, 200, 300, 500, 1000])
                if random.random() < 0.55:
                    # 単勝
                    horse = random.randint(1, NUM_HORSES)
                    self.betting_manager.place_win_bet(bot_id, bot_name, horse, amount)
                    self._add_message(f"{bot_name}: !単勝 {horse} {amount:,}")
                else:
                    # 複勝
                    horse = random.randint(1, NUM_HORSES)
                    self.betting_manager.place_show_bet(bot_id, bot_name, horse, amount)
                    self._add_message(f"{bot_name}: !複勝 {horse} {amount:,}")

        logger.info("Bot自動参加（実ユーザー %d人）", len(self._real_bettors))

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
        third  = self.finish_order[2].number
        logger.info("着順: 1着=%d番, 2着=%d番, 3着=%d番", first, second, third)

        # 払い戻し計算・残高反映（Botは払い戻し不要）
        self.payout_results = self.betting_manager.calculate_payouts(first, second, third)
        for pr in self.payout_results:
            if pr.channel_id.startswith("BOT_"):
                continue  # ダミーユーザーへの払い戻しはスキップ
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

        # タイトル（ヘッダー縦中央に配置）
        title_surf = self.f_md.render(title, True, COL_YELLOW)
        ty = (HEADER_H - title_surf.get_height()) // 2
        _draw_text_shadow(self.screen, title, self.f_md, COL_YELLOW, 16, ty)

        # サブテキスト
        if sub:
            sw = self.f_sm.render(sub, True, COL_DIM).get_width()
            _draw_text_shadow(self.screen, sub, self.f_sm, COL_DIM,
                              SCREEN_W // 2 - sw // 2, ty + 2)

        # カウントダウン
        if countdown >= 0:
            secs = int(countdown)
            col = COL_RED if secs <= 10 else (COL_ORANGE if secs <= 30 else COL_TEXT)
            cd_text = f"残り {secs}秒"
            cw = self.f_md.render(cd_text, True, col).get_width()
            _draw_text_shadow(self.screen, cd_text, self.f_md, col,
                              SCREEN_W - cw - 16, ty)

        # YouTube接続ステータス（右下隅）
        if self.youtube_client is not None:
            yt_status = self.youtube_client.status
            col = COL_GREEN_BR if yt_status == "受信中" else (
                  COL_RED   if yt_status.startswith("エラー") else COL_ORANGE)
            self.screen.blit(
                self.f_xs.render(f"YT:{yt_status}", True, col),
                (16, HEADER_H - self.f_xs.get_height() - 2))
        elif self.test_client is not None:
            self.screen.blit(
                self.f_xs.render("テストモード", True, COL_DIM),
                (16, HEADER_H - self.f_xs.get_height() - 2))

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
        left_rect = pygame.Rect(0, HEADER_H, LEFT_PANEL_W, SCREEN_H - HEADER_H)
        _draw_panel(self.screen, left_rect, radius=0)

        lx = 12
        ly = HEADER_H + 10

        # タイトル
        _draw_text_shadow(self.screen, "【単勝・複勝オッズ】", self.f_md, COL_YELLOW, lx, ly)
        ly += 48

        win_odds  = self.betting_manager.get_win_odds()
        show_odds = self.betting_manager.get_show_odds()

        # ── 列X座標（f_sm=28px基準、LEFT_PANEL_W=720に収まるよう配置）──
        TX_NUM   = lx + 4     # 馬番バッジ（34×32px）
        TX_NAME  = lx + 44    # 馬名（最大7文字）
        TX_STARS = lx + 226   # 強さ★（5文字）
        TX_STYLE = lx + 368   # 脚質略称（1文字）
        TX_WIN   = lx + 408   # 単勝オッズ
        TX_SHOW  = lx + 536   # 複勝オッズ
        TABLE_W  = 660
        ROW_H    = 40         # 1行の高さ

        # テーブルヘッダー
        for label, tx in [
            ("馬番", TX_NUM), ("馬名", TX_NAME), ("強さ", TX_STARS),
            ("脚", TX_STYLE), ("単勝", TX_WIN), ("複勝", TX_SHOW),
        ]:
            self.screen.blit(self.f_sm.render(label, True, COL_DIM), (tx, ly))
        ly += 32
        pygame.draw.line(self.screen, COL_BORDER, (lx, ly), (lx + TABLE_W, ly), 1)
        ly += 4

        for horse in self.horses:
            w_odds = win_odds.get(horse.number)
            s_odds = show_odds.get(horse.number)
            row_y  = ly + 2

            # 馬番カラーバッジ
            badge = pygame.Rect(TX_NUM, row_y, 34, 32)
            pygame.draw.rect(self.screen, horse.color, badge, border_radius=4)
            ns = self.f_sm.render(str(horse.number), True,
                                  horse_num_text_color(horse.number))
            self.screen.blit(ns, (badge.centerx - ns.get_width() // 2,
                                  badge.y + (badge.height - ns.get_height()) // 2))

            # 馬名（幅に収まるよう動的にフォントを縮小）
            name_w = TX_STARS - TX_NAME - 4
            self.screen.blit(
                _fit_text(horse.name, COL_TEXT, name_w,
                          [self.f_sm, self.f_xs, self.f_xs2, self.f_xs3]),
                (TX_NAME, row_y + 2)
            )

            # 強さ★（色分け）
            star_col = COL_GOLD if horse.strength >= 4 \
                       else COL_DIM if horse.strength <= 2 else COL_YELLOW
            self.screen.blit(
                self.f_sm.render(horse.stars, True, star_col), (TX_STARS, row_y + 2))

            # 脚質略称（色分け）
            style_col = {
                "逃げ": COL_RED, "先行": COL_ORANGE,
                "差し": COL_GREEN_BR, "追い込み": COL_SILVER,
            }.get(horse.running_style, COL_TEXT)
            self.screen.blit(
                self.f_sm.render(horse.style_short, True, style_col),
                (TX_STYLE, row_y + 2))

            # 単勝オッズ
            if w_odds:
                dw = max(1.0, w_odds)
                wc = COL_GREEN_BR if dw >= 5.0 else COL_YELLOW
                self.screen.blit(
                    self.f_sm.render(f"{dw:.1f}倍", True, wc), (TX_WIN, row_y + 2))
            else:
                self.screen.blit(
                    self.f_sm.render("---", True, COL_DIM), (TX_WIN, row_y + 2))

            # 複勝オッズ
            if s_odds:
                ds = max(1.0, s_odds)
                sc = COL_GREEN_BR if ds >= 3.0 else COL_YELLOW
                self.screen.blit(
                    self.f_sm.render(f"{ds:.1f}倍", True, sc), (TX_SHOW, row_y + 2))
            else:
                self.screen.blit(
                    self.f_sm.render("---", True, COL_DIM), (TX_SHOW, row_y + 2))

            ly += ROW_H

        ly += 6
        pygame.draw.line(self.screen, COL_BORDER, (lx, ly), (lx + TABLE_W, ly), 1)
        ly += 8

        # 総売上
        win_pool  = self.betting_manager.get_win_pool_total()
        show_pool = self.betting_manager.get_show_pool_total()
        total     = win_pool + show_pool
        tot_s = self.f_sm.render(f"総売上: {total:,}円", True, COL_DIM)
        self.screen.blit(tot_s, (lx, SCREEN_H - tot_s.get_height() - 6))

        # ── 右パネル ─────────────────────────────────────
        right_x = LEFT_PANEL_W
        right_w = SCREEN_W - LEFT_PANEL_W
        mid_y   = HEADER_H + (SCREEN_H - HEADER_H) // 2

        # 最新コメント（上半分）
        comment_rect = pygame.Rect(right_x, HEADER_H, right_w, mid_y - HEADER_H)
        _draw_panel(self.screen, comment_rect, radius=0)
        _draw_text_shadow(self.screen, "最新コメント", self.f_md, COL_YELLOW,
                          right_x + 10, HEADER_H + 8)
        cy = HEADER_H + 52
        if self.recent_messages:
            for msg in self.recent_messages:
                max_chars = max(8, right_w // 18)
                disp = msg if len(msg) <= max_chars else msg[:max_chars - 1] + "…"
                self.screen.blit(self.f_sm.render(disp, True, COL_TEXT),
                                 (right_x + 10, cy))
                cy += 34
        else:
            self.screen.blit(
                self.f_sm.render("コメントを待っています...", True, COL_DIM),
                (right_x + 10, cy)
            )

        # 残高ランキング（下半分）
        rank_rect = pygame.Rect(right_x, mid_y, right_w, SCREEN_H - mid_y)
        _draw_panel(self.screen, rank_rect, radius=0)
        _draw_text_shadow(self.screen, "残高 TOP5", self.f_md, COL_YELLOW,
                          right_x + 10, mid_y + 8)
        ry = mid_y + 52
        ranking = self.user_manager.get_ranking(5)
        medal_colors = [COL_GOLD, COL_SILVER, COL_BRONZE, COL_TEXT, COL_TEXT]
        for i, (name, bal) in enumerate(ranking):
            col = medal_colors[i]
            rank_txt = f"{i+1}. {name[:8]}  {bal:,}円"
            self.screen.blit(self.f_md.render(rank_txt, True, col), (right_x + 10, ry))
            ry += 42

        # 区切り線（左右の境界）
        pygame.draw.line(self.screen, COL_BORDER,
                         (LEFT_PANEL_W, HEADER_H), (LEFT_PANEL_W, SCREEN_H), 1)


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

        # ── 右下: ゴール順情報パネル（大型フォント対応）
        panel_w, panel_h = 320, NUM_HORSES * 32 + 40
        panel_rect = pygame.Rect(SCREEN_W - panel_w - 8,
                                 SCREEN_H - panel_h - 8,
                                 panel_w, panel_h)
        _draw_panel(self.screen, panel_rect, bg=(10, 20, 10, 200))
        _draw_text_shadow(self.screen, "馬番  馬名         着順", self.f_xs, COL_DIM,
                          panel_rect.x + 6, panel_rect.y + 6)
        for i, horse in enumerate(self.horses):
            py = panel_rect.y + 32 + i * 32
            # 馬番バッジ（枠色に応じた文字色）
            b = pygame.Rect(panel_rect.x + 4, py + 1, 24, 24)
            pygame.draw.rect(self.screen, horse.color, b, border_radius=3)
            ns = self.f_xs.render(str(horse.number), True,
                                  horse_num_text_color(horse.number))
            self.screen.blit(ns, (b.centerx - ns.get_width() // 2,
                                  b.y + (b.height - ns.get_height()) // 2))
            # 馬名（幅に収まるよう動的にフォントを縮小）
            name_col = COL_GOLD if horse.finish_rank == 1 else COL_TEXT
            name_max_w = panel_w - 80
            self.screen.blit(
                _fit_text(horse.name, name_col, name_max_w,
                          [self.f_num_sm, self.f_xs, self.f_xs2, self.f_xs3]),
                (panel_rect.x + 32, py + 1)
            )
            # 着順
            if horse.finish_rank:
                self.screen.blit(
                    self.f_xs.render(f"{horse.finish_rank}着", True, COL_YELLOW),
                    (panel_rect.x + panel_w - 56, py + 1)
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

        # ── 着順パネル（左） ──────────────────────────────
        order_rect = pygame.Rect(10, HEADER_H + 8, 500, SCREEN_H - HEADER_H - 16)
        _draw_panel(self.screen, order_rect)
        _draw_text_shadow(self.screen, "着順", self.f_lg, COL_YELLOW,
                          order_rect.x + 12, order_rect.y + 8)

        medal_cols = [COL_GOLD, COL_SILVER, COL_BRONZE]
        for i, horse in enumerate(self.finish_order):
            fy = order_rect.y + 62 + i * 50
            col = medal_cols[i] if i < 3 else COL_TEXT
            rank_s = self.f_lg.render(f"{i+1}着", True, col)
            self.screen.blit(rank_s, (order_rect.x + 10, fy))

            # 馬番バッジ
            badge = pygame.Rect(order_rect.x + 100, fy + 4, 36, 36)
            pygame.draw.rect(self.screen, horse.color, badge, border_radius=5)
            bn = self.f_md.render(str(horse.number), True,
                                  horse_num_text_color(horse.number))
            self.screen.blit(bn, (badge.centerx - bn.get_width() // 2,
                                  badge.y + (badge.height - bn.get_height()) // 2))

            # 馬名
            name_max_w = order_rect.width - 150 - 12
            name_surf = _fit_text(horse.name, col, name_max_w,
                                  [self.f_lg, self.f_md, self.f_sm,
                                   self.f_xs, self.f_xs2, self.f_xs3])
            self.screen.blit(name_surf, (order_rect.x + 146, fy + 2))

            if i >= 7:
                break

        # ── 右側パネル（配当 + ランキング）──────────────────
        right_x2 = order_rect.right + 8
        right_w2  = SCREEN_W - right_x2 - 8

        # 配当パネル（高さを絞る: title 50 + 単勝 40 + 複勝×3×36 = 198 → 210）
        div_rect = pygame.Rect(right_x2, HEADER_H + 8, right_w2, 210)
        _draw_panel(self.screen, div_rect)
        dx, dy = div_rect.x + 12, div_rect.y + 8
        _draw_text_shadow(self.screen, "配当", self.f_lg, COL_YELLOW, dx, dy)
        dy += 50

        first_num  = self.finish_order[0].number
        second_num = self.finish_order[1].number
        third_num  = self.finish_order[2].number
        win_odds_map  = self.betting_manager.get_win_odds()
        show_odds_map = self.betting_manager.get_show_odds()

        # 単勝
        w_odds = win_odds_map.get(first_num)
        w_str  = f"{max(1.0, w_odds):.1f}倍" if w_odds else "---"
        self.screen.blit(
            self.f_md.render(f"単勝 {first_num}番 {w_str}", True, COL_TEXT), (dx, dy))
        dy += 40

        # 複勝（1〜3着）
        for place_num in (first_num, second_num, third_num):
            s_odds = show_odds_map.get(place_num)
            s_str  = f"{max(1.0, s_odds):.1f}倍" if s_odds else "---"
            self.screen.blit(
                self.f_md.render(f"複勝 {place_num}番 {s_str}", True, COL_TEXT), (dx, dy))
            dy += 36

        # 払い戻しパネル（title 36 + items×30 = 156 → 160）
        pay_rect = pygame.Rect(right_x2, div_rect.bottom + 8, right_w2, 160)
        _draw_panel(self.screen, pay_rect)
        px, py_start = pay_rect.x + 12, pay_rect.y + 8
        if self.payout_results:
            _draw_text_shadow(self.screen, "払い戻し", self.f_sm, COL_YELLOW, px, py_start)
            py_ = py_start + 36
            for pr in self.payout_results[:4]:
                type_label = "単勝" if pr.bet_type == "win" else "複勝"
                line = (f"{pr.display_name[:6]} {type_label}{pr.horse_label}"
                        f" {pr.odds:.1f}倍→{pr.payout_amount:,}円")
                self.screen.blit(self.f_sm.render(line, True, COL_GREEN_BR), (px, py_))
                py_ += 30
        else:
            _draw_text_shadow(self.screen, "払い戻しなし", self.f_md, COL_DIM,
                              px, py_start + 10)

        # 残高ランキングパネル（残りすべて: ≈ 248px）
        # title 46 + 5items×38 = 236 → 248に収まる
        rk_rect = pygame.Rect(right_x2, pay_rect.bottom + 8,
                              right_w2, SCREEN_H - pay_rect.bottom - 16)
        _draw_panel(self.screen, rk_rect)
        _draw_text_shadow(self.screen, "残高 TOP5", self.f_md, COL_YELLOW,
                          rk_rect.x + 12, rk_rect.y + 6)

        ranking = self.user_manager.get_ranking(5)
        medal_colors = [COL_GOLD, COL_SILVER, COL_BRONZE, COL_TEXT, COL_TEXT]
        for i, (name, bal) in enumerate(ranking):
            ry = rk_rect.y + 44 + i * 38
            col = medal_colors[i]
            rank_s  = self.f_sm.render(f"{i+1}位", True, col)
            name_s  = self.f_sm.render(name[:10], True, col)
            bal_s   = self.f_sm.render(f"{bal:,}円", True, col)
            self.screen.blit(rank_s, (rk_rect.x + 10, ry))
            self.screen.blit(name_s, (rk_rect.x + 90, ry))
            self.screen.blit(bal_s,  (rk_rect.right - bal_s.get_width() - 10, ry))

        # 次レースまでのカウントダウンバー
        bar_w = int((remaining / RESULTS_DURATION) * (SCREEN_W - 40))
        pygame.draw.rect(self.screen, COL_BORDER, (20, SCREEN_H - 12, SCREEN_W - 40, 8),
                         border_radius=4)
        pygame.draw.rect(self.screen, COL_GREEN_BR, (20, SCREEN_H - 12, bar_w, 8),
                         border_radius=4)



    # ──────────────────────────────────────────────
    # 縦型モード: ゲーム画面を合成してバナーを追加
    # ──────────────────────────────────────────────

    _V_TOP_H  = 100
    _V_GAME_W = VERTICAL_W                           # 720
    _V_GAME_H = VERTICAL_W * SCREEN_H // SCREEN_W   # 405
    _V_BOT_Y  = _V_TOP_H + _V_GAME_H                # 505
    _V_BOT_H  = VERTICAL_H - _V_BOT_Y               # 775

    def _composite_vertical(self):
        """縦型: ゲーム面を720×405にスケールし上下バナーと合成してdisplayへ転送"""
        dsp = self._display
        dsp.fill(COL_BG)

        # ── ゲームコンテンツ（スケール済み）を中段に配置 ──
        game_scaled = pygame.transform.scale(
            self.screen, (self._V_GAME_W, self._V_GAME_H))
        dsp.blit(game_scaled, (0, self._V_TOP_H))

        # ── 上バナー ──────────────────────────────────
        top_r = pygame.Rect(0, 0, VERTICAL_W, self._V_TOP_H)
        pygame.draw.rect(dsp, (10, 20, 60), top_r)
        pygame.draw.line(dsp, COL_BORDER,
                         (0, self._V_TOP_H - 1), (VERTICAL_W, self._V_TOP_H - 1), 2)
        bs = self.f_sm.render("毎日配信予定  チャンネル登録よろしく！", True, (255, 215, 0))
        dsp.blit(bs, ((VERTICAL_W - bs.get_width()) // 2,
                      (self._V_TOP_H - bs.get_height()) // 2))

        # ── 下バナー ──────────────────────────────────
        bot_r = pygame.Rect(0, self._V_BOT_Y, VERTICAL_W, self._V_BOT_H)
        pygame.draw.rect(dsp, (10, 20, 60), bot_r)
        pygame.draw.line(dsp, COL_BORDER,
                         (0, self._V_BOT_Y), (VERTICAL_W, self._V_BOT_Y), 2)

        lines = [
            ("コメントで馬券購入！",   self.f_lg, (255, 215, 0)),
            ("",                       self.f_sm, (0, 0, 0)),
            ("!単勝 [馬番] [金額]",     self.f_md, (200, 255, 200)),
            ("  例: !単勝 3 500",      self.f_sm, (160, 220, 160)),
            ("!複勝 [馬番] [金額]",     self.f_md, (200, 255, 200)),
            ("  例: !複勝 3 500",      self.f_sm, (160, 220, 160)),
            ("",                       self.f_sm, (0, 0, 0)),
            ("!残高 で残高確認",        self.f_md, (200, 255, 200)),
        ]
        y = self._V_BOT_Y + 20
        for text, font, col in lines:
            if text:
                surf = font.render(text, True, col)
                dsp.blit(surf, ((VERTICAL_W - surf.get_width()) // 2, y))
                y += surf.get_height() + 6
            else:
                y += 10

        pygame.display.flip()

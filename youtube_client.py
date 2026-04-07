"""
YouTube Live Chat クライアントモジュール

YouTube Data API v3 でライブチャットを5秒間隔でポーリングし、
コマンドをキューに投入する。

コマンド仕様:
  !単勝 [馬番] [金額]   例: !単勝 3 500
  !複勝 [馬番] [金額]   例: !複勝 3 500
  !残高

--test 引数でダミーコメントを投入するテストモードも提供する。
"""

import queue
import random
import threading
import time
import logging
import os
import unicodedata
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────
# コマンドデータクラス
# ──────────────────────────────────────────────────────────────────

CMD_WIN     = "win_bet"
CMD_SHOW    = "show_bet"    # 複勝
CMD_BALANCE = "balance"
CMD_ERROR   = "error"   # 購入金額が100円単位でない等のバリデーションエラー


@dataclass
class ParsedCommand:
    """パースされたコメントコマンド"""
    channel_id: str
    display_name: str
    command_type: str         # CMD_WIN | CMD_SHOW | CMD_BALANCE | CMD_ERROR
    horse1: Optional[int] = None
    horse2: Optional[int] = None
    amount: Optional[int] = None
    raw_text: str = ""
    timestamp: float = 0.0
    error_message: str = ""   # CMD_ERROR 時のエラーメッセージ


# ──────────────────────────────────────────────────────────────────
# コマンドパーサー
# ──────────────────────────────────────────────────────────────────

def parse_comment(channel_id: str, display_name: str,
                  text: str, timestamp: float) -> Optional[ParsedCommand]:
    """
    コメントテキストをパースしてコマンドを返す。

    認識できないコメントは None を返す。

    Args:
        channel_id:   YouTubeチャンネルID
        display_name: 表示名
        text:         コメント本文
        timestamp:    受信時刻（time.time()）

    Returns:
        ParsedCommand または None
    """
    # 全角→半角正規化（！→!、全角数字→半角、全角スペース→半角スペース）
    text = unicodedata.normalize("NFKC", text).strip()
    # 「円」suffix を除去（例: 500円 → 500）
    text = text.replace("円", "")

    # 単勝: !単勝 馬番 金額
    if text.startswith("!単勝"):
        parts = text.split()
        if len(parts) == 3:
            try:
                horse  = int(parts[1])
                amount = int(parts[2])
                if 1 <= horse <= 8 and amount > 0:
                    if amount % 100 != 0:
                        return ParsedCommand(
                            channel_id=channel_id,
                            display_name=display_name,
                            command_type=CMD_ERROR,
                            horse1=horse,
                            amount=amount,
                            raw_text=text,
                            timestamp=timestamp,
                            error_message=(
                                f"金額は100円単位で入力してください "
                                f"（例: !単勝 {horse} {(amount // 100 + 1) * 100}）"
                            ),
                        )
                    return ParsedCommand(
                        channel_id=channel_id,
                        display_name=display_name,
                        command_type=CMD_WIN,
                        horse1=horse,
                        amount=amount,
                        raw_text=text,
                        timestamp=timestamp,
                    )
            except ValueError:
                pass
        return None

    # 複勝: !複勝 馬番 金額
    if text.startswith("!複勝"):
        parts = text.split()
        if len(parts) == 3:
            try:
                horse  = int(parts[1])
                amount = int(parts[2])
                if 1 <= horse <= 8 and amount > 0:
                    if amount % 100 != 0:
                        return ParsedCommand(
                            channel_id=channel_id,
                            display_name=display_name,
                            command_type=CMD_ERROR,
                            horse1=horse,
                            amount=amount,
                            raw_text=text,
                            timestamp=timestamp,
                            error_message=(
                                f"金額は100円単位で入力してください "
                                f"（例: !複勝 {horse} {(amount // 100 + 1) * 100}）"
                            ),
                        )
                    return ParsedCommand(
                        channel_id=channel_id,
                        display_name=display_name,
                        command_type=CMD_SHOW,
                        horse1=horse,
                        amount=amount,
                        raw_text=text,
                        timestamp=timestamp,
                    )
            except ValueError:
                pass
        return None

    # 残高確認: !残高
    if text.strip() == "!残高":
        return ParsedCommand(
            channel_id=channel_id,
            display_name=display_name,
            command_type=CMD_BALANCE,
            raw_text=text,
            timestamp=timestamp,
        )

    return None


# ──────────────────────────────────────────────────────────────────
# YouTube Live Chat クライアント
# ──────────────────────────────────────────────────────────────────

class YouTubeClient:
    """
    YouTube Data API v3 でライブチャットをポーリングするクライアント。

    バックグラウンドスレッドで動作し、
    コマンドを command_queue に投入する。
    """

    POLL_INTERVAL = 1.5   # デフォルトポーリング間隔（秒）。遅延最小化のため短めに設定

    def __init__(self, video_id: str, api_key: str,
                 command_queue: queue.Queue):
        """
        Args:
            video_id:      ライブ配信のvideo_id
            api_key:       YouTube Data API キー
            command_queue: コマンド投入先キュー
        """
        self.video_id = video_id
        self.api_key  = api_key
        self.command_queue = command_queue

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._next_page_token: Optional[str] = None
        self._live_chat_id: Optional[str] = None
        self._poll_interval: float = self.POLL_INTERVAL  # APIの推奨待機時間で上書きされる
        self.status: str = "初期化中"  # ゲーム画面に表示するステータス文字列

        # googleapiclient の遅延インポート
        try:
            from googleapiclient.discovery import build
            # token.json があれば OAuth 認証を使う
            # (限定公開配信のライブチャットは API キーでは取得できない場合がある)
            _token_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "token.json")
            if os.path.exists(_token_file):
                from google.oauth2.credentials import Credentials
                from google.auth.transport.requests import Request
                creds = Credentials.from_authorized_user_file(_token_file)
                if creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                self._youtube = build("youtube", "v3", credentials=creds)
                logger.info("YouTube APIクライアント初期化完了 (OAuth)")
            else:
                self._youtube = build("youtube", "v3", developerKey=api_key)
                logger.info("YouTube APIクライアント初期化完了 (APIキー)")
            self.status = "接続待機中"
        except ImportError:
            logger.error("google-api-python-client がインストールされていません")
            self._youtube = None
            self.status = "ライブラリなし"
        except Exception as e:
            logger.error("YouTube APIクライアント初期化エラー: %s", e)
            self._youtube = None
            self.status = "初期化失敗"

    def start(self):
        """ポーリングスレッドを開始する"""
        if self._youtube is None:
            logger.error("YouTube API が利用できないためポーリングを開始できません")
            self.status = "起動失敗"
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True,
                                        name="YouTubePoller")
        self._thread.start()
        logger.info("YouTube ポーリング開始: video_id=%s", self.video_id)

    def stop(self):
        """ポーリングスレッドを停止する"""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("YouTube ポーリング停止")

    # ── 内部メソッド ──

    def _get_live_chat_id(self) -> Optional[str]:
        """video_id からライブチャットIDを取得する"""
        try:
            resp = self._youtube.videos().list(
                part="liveStreamingDetails",
                id=self.video_id,
            ).execute()
            items = resp.get("items", [])
            if not items:
                logger.error("video_id=%s が見つかりません", self.video_id)
                return None
            details = items[0].get("liveStreamingDetails", {})
            chat_id = details.get("activeLiveChatId")
            if not chat_id:
                logger.error("ライブチャットIDが取得できません（配信中でない可能性）")
            else:
                logger.info("ライブチャットID取得成功: live_chat_id=%s", chat_id)
            return chat_id
        except Exception as e:
            logger.error("ライブチャットID取得エラー: %s", e)
            return None

    def _fetch_messages(self):
        """メッセージを取得してキューに投入する"""
        from googleapiclient.errors import HttpError
        try:
            params = {
                "liveChatId": self._live_chat_id,
                "part": "snippet,authorDetails",
            }
            if self._next_page_token:
                params["pageToken"] = self._next_page_token

            resp = self._youtube.liveChatMessages().list(**params).execute()
            self._next_page_token = resp.get("nextPageToken")

            # APIが推奨する待機時間を取得（最大10秒にキャップ）
            interval_ms = resp.get("pollingIntervalMillis")
            if interval_ms:
                # 遅延最小化: API推奨値を採用するが最大2秒にキャップ（通常は5〜10秒を無視）
                new_interval = min(interval_ms / 1000.0, 2.0)
                new_interval = max(new_interval, 1.0)  # 最小1秒（API負荷対策）
                if new_interval != self._poll_interval:
                    logger.info("ポーリング間隔: %.1f秒 (API推奨: %dms)", new_interval, interval_ms)
                    self._poll_interval = new_interval

            items = resp.get("items", [])
            if items:
                logger.info("[コメント取得] %d件", len(items))

            for item in items:
                snippet = item.get("snippet", {})
                author  = item.get("authorDetails", {})
                text         = snippet.get("displayMessage", "")
                channel_id   = author.get("channelId", "")
                # displayName = チャンネル表示名。@ で始まるハンドル形式の場合は @ を除去
                raw_name     = author.get("displayName", "名無し")
                display_name = raw_name.lstrip("@") if raw_name.startswith("@") else raw_name

                logger.info("[コメント受信] %s: %r", display_name, text)

                cmd = parse_comment(channel_id, display_name, text, time.time())
                if cmd:
                    self.command_queue.put(cmd)
                    logger.info("[コマンド認識] user=%s type=%s text=%r",
                                display_name, cmd.command_type, text)

        except HttpError as e:
            status = e.resp.status if hasattr(e, "resp") else "?"
            logger.error("[APIエラー] HTTP %s: %s", status, e)
            if str(status) == "403":
                logger.error("→ APIキーが無効またはクォータ超過の可能性があります")
                self.status = "エラー:403"
                self._poll_interval = 60.0  # エラー時は待機を延ばす
            else:
                self.status = f"エラー:{status}"
        except Exception as e:
            logger.error("[APIエラー] %s: %s", type(e).__name__, e)
            self.status = f"エラー"

    def _poll_loop(self):
        """ポーリングループ（バックグラウンドスレッドで実行）"""
        # ライブチャットIDを取得
        self.status = "チャットID取得中"
        while not self._stop_event.is_set():
            self._live_chat_id = self._get_live_chat_id()
            if self._live_chat_id:
                break
            self.status = "チャットID待機中"
            logger.warning("ライブチャットID取得失敗、10秒後にリトライ")
            self._stop_event.wait(10)
        self.status = "受信中"

        # メッセージポーリング
        while not self._stop_event.is_set():
            self._fetch_messages()
            self._stop_event.wait(self._poll_interval)


# ──────────────────────────────────────────────────────────────────
# テストクライアント（--test モード用）
# ──────────────────────────────────────────────────────────────────

# テスト用ダミーユーザー
TEST_USERS = [
    ("test_ch_001", "テストユーザー１"),
    ("test_ch_002", "テストユーザー２"),
    ("test_ch_003", "テストユーザー３"),
    ("test_ch_004", "テストユーザー４"),
    ("test_ch_005", "テストユーザー５"),
    ("test_ch_006", "テストユーザー６"),
    ("test_ch_007", "テストユーザー７"),
    ("test_ch_008", "テストユーザー８"),
]


class TestClient:
    """
    ダミーコメントを自動投入するテストクライアント。

    --test 引数で起動したときに使用する。
    ランダムなタイミングで馬券コマンドを生成する。
    """

    def __init__(self, command_queue: queue.Queue, num_horses: int = 8):
        """
        Args:
            command_queue: コマンド投入先キュー
            num_horses:    出走馬数（馬番の上限）
        """
        self.command_queue = command_queue
        self.num_horses    = num_horses
        self._stop_event   = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.betting_active = threading.Event()  # ベット受付中フラグ

    def start(self):
        """テストスレッドを開始する"""
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._generate_loop, daemon=True,
                                        name="TestClient")
        self._thread.start()
        logger.info("テストクライアント開始")

    def stop(self):
        """テストスレッドを停止する"""
        self._stop_event.set()
        self.betting_active.set()  # ブロック解除
        if self._thread:
            self._thread.join(timeout=5)

    def _generate_loop(self):
        """ランダムコマンドを生成し続けるループ"""
        while not self._stop_event.is_set():
            # ベット受付中のみコマンドを生成
            self.betting_active.wait(timeout=1)
            if not self.betting_active.is_set():
                continue

            user = random.choice(TEST_USERS)
            channel_id, display_name = user

            cmd = self._random_command(channel_id, display_name)
            if cmd:
                self.command_queue.put(cmd)
                logger.debug("[TEST] コマンド投入: %s %s", display_name, cmd.raw_text)

            # 1〜6秒のランダム間隔
            wait = random.uniform(1.0, 6.0)
            self._stop_event.wait(wait)

    def _random_command(self, channel_id: str,
                        display_name: str) -> Optional[ParsedCommand]:
        """ランダムなコマンドを生成する"""
        r      = random.random()
        amount = random.choice([100, 200, 300, 500, 1000])

        if r < 0.05:
            # 5%: 残高確認
            return ParsedCommand(
                channel_id=channel_id,
                display_name=display_name,
                command_type=CMD_BALANCE,
                raw_text="!残高",
                timestamp=time.time(),
            )
        elif r < 0.55:
            # 50%: 単勝
            horse = random.randint(1, self.num_horses)
            return ParsedCommand(
                channel_id=channel_id,
                display_name=display_name,
                command_type=CMD_WIN,
                horse1=horse,
                amount=amount,
                raw_text=f"!単勝 {horse} {amount}",
                timestamp=time.time(),
            )
        else:
            # 45%: 複勝
            horse = random.randint(1, self.num_horses)
            return ParsedCommand(
                channel_id=channel_id,
                display_name=display_name,
                command_type=CMD_SHOW,
                horse1=horse,
                amount=amount,
                raw_text=f"!複勝 {horse} {amount}",
                timestamp=time.time(),
            )


# ──────────────────────────────────────────────────────────────────
# YouTube ライブ配信枠の自動作成
# ──────────────────────────────────────────────────────────────────

def create_live_broadcast(api_key: str, title: str,
                           scheduled_start_time: str) -> Optional[str]:
    """
    YouTube ライブ配信枠を自動作成する（OAuth2 認証が必要）。

    Args:
        api_key:               YouTube Data API キー
        title:                 配信タイトル
        scheduled_start_time:  ISO 8601形式の開始時刻（例: "2025-01-01T18:00:00Z"）

    Returns:
        作成された video_id、失敗時は None
    """
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build as yt_build

        SCOPES = ["https://www.googleapis.com/auth/youtube"]
        flow   = InstalledAppFlow.from_client_secrets_file("client_secrets.json", SCOPES)
        credentials = flow.run_local_server(port=0)
        youtube = yt_build("youtube", "v3", credentials=credentials)

        # ブロードキャスト作成
        broadcast = youtube.liveBroadcasts().insert(
            part="snippet,status,contentDetails",
            body={
                "snippet": {
                    "title": title,
                    "scheduledStartTime": scheduled_start_time,
                    "description": "YouTube競馬ゲーム 自動配信",
                },
                "status": {"privacyStatus": "public"},
                "contentDetails": {"enableAutoStart": True, "enableAutoStop": True},
            }
        ).execute()

        broadcast_id = broadcast["id"]

        # ストリーム作成
        stream = youtube.liveStreams().insert(
            part="snippet,cdn",
            body={
                "snippet": {"title": title},
                "cdn": {
                    "frameRate": "30fps",
                    "ingestionType": "rtmp",
                    "resolution": "1080p",
                },
            }
        ).execute()

        # ブロードキャストとストリームを紐付け
        youtube.liveBroadcasts().bind(
            part="id,contentDetails",
            id=broadcast_id,
            streamId=stream["id"],
        ).execute()

        logger.info("ライブ配信枠を作成しました: video_id=%s", broadcast_id)
        return broadcast_id

    except Exception as e:
        logger.error("ライブ配信枠の作成に失敗しました: %s", e)
        return None

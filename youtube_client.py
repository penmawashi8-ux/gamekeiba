"""
YouTube Live Chat クライアントモジュール

YouTube Data API v3 でライブチャットを5秒間隔でポーリングし、
コマンドをキューに投入する。

コマンド仕様:
  !単勝 [馬番] [金額]         例: !単勝 3 500
  !馬連 [馬番] [馬番] [金額]  例: !馬連 2 5 1000
  !残高

--test 引数でダミーコメントを投入するテストモードも提供する。
"""

import queue
import random
import threading
import time
import logging
import os
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────
# コマンドデータクラス
# ──────────────────────────────────────────────────────────────────

CMD_WIN = "win_bet"
CMD_QUINELLA = "quinella_bet"
CMD_BALANCE = "balance"


@dataclass
class ParsedCommand:
    """パースされたコメントコマンド"""
    channel_id: str
    display_name: str
    command_type: str         # CMD_WIN | CMD_QUINELLA | CMD_BALANCE
    horse1: Optional[int] = None
    horse2: Optional[int] = None
    amount: Optional[int] = None
    raw_text: str = ""
    timestamp: float = 0.0


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
    text = text.strip()

    # 単勝: !単勝 馬番 金額
    if text.startswith("!単勝"):
        parts = text.split()
        if len(parts) == 3:
            try:
                horse = int(parts[1])
                amount = int(parts[2])
                if 1 <= horse <= 8 and amount > 0:
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

    # 馬連: !馬連 馬番 馬番 金額
    if text.startswith("!馬連"):
        parts = text.split()
        if len(parts) == 4:
            try:
                h1 = int(parts[1])
                h2 = int(parts[2])
                amount = int(parts[3])
                if 1 <= h1 <= 8 and 1 <= h2 <= 8 and h1 != h2 and amount > 0:
                    return ParsedCommand(
                        channel_id=channel_id,
                        display_name=display_name,
                        command_type=CMD_QUINELLA,
                        horse1=h1,
                        horse2=h2,
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

    POLL_INTERVAL = 5.0   # ポーリング間隔（秒）

    def __init__(self, video_id: str, api_key: str,
                 command_queue: queue.Queue):
        """
        Args:
            video_id:      ライブ配信のvideo_id
            api_key:       YouTube Data API キー
            command_queue: コマンド投入先キュー
        """
        self.video_id = video_id
        self.api_key = api_key
        self.command_queue = command_queue

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._next_page_token: Optional[str] = None
        self._live_chat_id: Optional[str] = None

        # googleapiclient の遅延インポート
        try:
            from googleapiclient.discovery import build
            self._youtube = build("youtube", "v3", developerKey=api_key)
            logger.info("YouTube API クライアント初期化完了")
        except ImportError:
            logger.error("google-api-python-client がインストールされていません")
            self._youtube = None

    def start(self):
        """ポーリングスレッドを開始する"""
        if self._youtube is None:
            logger.error("YouTube API が利用できないためポーリングを開始できません")
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

            for item in resp.get("items", []):
                snippet = item.get("snippet", {})
                author = item.get("authorDetails", {})
                text = snippet.get("displayMessage", "")
                channel_id = author.get("channelId", "")
                display_name = author.get("displayName", "名無し")

                cmd = parse_comment(channel_id, display_name, text, time.time())
                if cmd:
                    self.command_queue.put(cmd)
                    logger.debug("コマンド受信: %s %s", display_name, text)

        except HttpError as e:
            logger.warning("YouTube API エラー: %s", e)
        except Exception as e:
            logger.warning("メッセージ取得エラー: %s", e)

    def _poll_loop(self):
        """ポーリングループ（バックグラウンドスレッドで実行）"""
        # ライブチャットIDを取得
        while not self._stop_event.is_set():
            self._live_chat_id = self._get_live_chat_id()
            if self._live_chat_id:
                break
            logger.warning("ライブチャットID取得失敗、10秒後にリトライ")
            self._stop_event.wait(10)

        # メッセージポーリング
        while not self._stop_event.is_set():
            self._fetch_messages()
            self._stop_event.wait(self.POLL_INTERVAL)


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
        self.num_horses = num_horses
        self._stop_event = threading.Event()
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
        r = random.random()
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
            # 45%: 馬連
            h1, h2 = random.sample(range(1, self.num_horses + 1), 2)
            return ParsedCommand(
                channel_id=channel_id,
                display_name=display_name,
                command_type=CMD_QUINELLA,
                horse1=h1,
                horse2=h2,
                amount=amount,
                raw_text=f"!馬連 {h1} {h2} {amount}",
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

    Note:
        この機能は OAuth2 認証が必要です。
        Google Cloud Console でOAuth2クライアントを設定し、
        google-auth-oauthlib をインストールしてください。
    """
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build as yt_build

        SCOPES = ["https://www.googleapis.com/auth/youtube"]
        flow = InstalledAppFlow.from_client_secrets_file("client_secrets.json", SCOPES)
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

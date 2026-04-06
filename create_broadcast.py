#!/usr/bin/env python3
"""
YouTube ライブ配信枠 自動作成スクリプト

OAuth2認証でYouTube LiveのブロードキャストをAPI経由で作成します。
認証トークンはtoken.jsonに保存され、2回目以降は自動使用されます。

使い方:
    python create_broadcast.py
    -> 作成した VIDEO_ID を標準出力に1行出力します。
    -> エラー時は何も出力せず終了コード1で終了します。

必要ファイル:
    client_secret.json  - Google Cloud ConsoleでダウンロードしたOAuth2クライアント情報
    token.json          - 認証トークン（初回認証後に自動生成・再利用）
"""

import json
import os
import sys
import logging
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# OAuth2スコープ
SCOPES = ["https://www.googleapis.com/auth/youtube"]

# ファイルパス（スクリプトと同じフォルダ）
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRET_FILE = os.path.join(_BASE_DIR, "client_secret.json")
TOKEN_FILE = os.path.join(_BASE_DIR, "token.json")


# ──────────────────────────────────────────────────────────────────
# 認証
# ──────────────────────────────────────────────────────────────────

def get_credentials():
    """
    OAuth2認証情報を取得する。

    token.json が存在すれば再利用し、期限切れならリフレッシュする。
    token.json が存在しない場合はブラウザで初回認証フローを実行する。

    Returns:
        google.oauth2.credentials.Credentials

    Raises:
        SystemExit: client_secret.json が見つからない場合
    """
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None

    # 既存トークンを読み込む
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
            logger.info("token.json からトークンを読み込みました")
        except Exception as e:
            logger.warning("token.json の読み込みに失敗しました（再認証します）: %s", e)
            creds = None

    # トークンが無効または期限切れの場合
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # リフレッシュトークンで更新を試みる
            try:
                creds.refresh(Request())
                logger.info("アクセストークンをリフレッシュしました")
            except Exception as e:
                logger.warning("トークンのリフレッシュに失敗しました（再認証します）: %s", e)
                creds = None

        if not creds:
            # 初回認証フロー（ブラウザが開きます）
            if not os.path.exists(CLIENT_SECRET_FILE):
                print(
                    f"[ERROR] {CLIENT_SECRET_FILE} が見つかりません。\n"
                    "Google Cloud Console で OAuth2 クライアント ID を作成し、\n"
                    "client_secret.json をプロジェクトフォルダに配置してください。\n"
                    "詳細は README.md の「OAuth2 の設定手順」を参照してください。",
                    file=sys.stderr,
                )
                sys.exit(1)

            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
            print("[INFO] 認証が完了しました", file=sys.stderr)

        # トークンを保存（次回以降は自動使用）
        try:
            with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                f.write(creds.to_json())
            logger.info("token.json を保存しました: %s", TOKEN_FILE)
        except Exception as e:
            logger.warning("token.json の保存に失敗しました: %s", e)

    return creds


# ──────────────────────────────────────────────────────────────────
# 配信枠の作成
# ──────────────────────────────────────────────────────────────────

def create_broadcast(title: str, scheduled_start_time: str) -> str:
    """
    YouTube ライブ配信枠（限定公開）を作成して video_id を返す。

    Args:
        title:                 配信タイトル
        scheduled_start_time:  ISO 8601 形式の開始時刻
                               例: "2025-01-01T19:00:00+09:00"

    Returns:
        作成された video_id（文字列）

    Raises:
        Exception: 作成に失敗した場合
    """
    from googleapiclient.discovery import build

    creds = get_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    # ブロードキャスト作成（限定公開）
    broadcast = youtube.liveBroadcasts().insert(
        part="snippet,status,contentDetails",
        body={
            "snippet": {
                "title": title,
                "scheduledStartTime": scheduled_start_time,
                "description": (
                    "バーチャル競馬LIVE 自動配信\n\n"
                    "コメントで馬券を購入しよう！\n"
                    "  !単勝 [馬番] [金額]          例: !単勝 3 500\n"
                    "  !馬連 [馬番] [馬番] [金額]   例: !馬連 2 5 1000\n"
                    "  !残高"
                ),
            },
            "status": {
                "privacyStatus": "unlisted",   # 限定公開
            },
            "contentDetails": {
                "enableAutoStart": True,
                "enableAutoStop": True,
            },
        },
    ).execute()

    broadcast_id = broadcast["id"]
    logger.info("ブロードキャスト作成完了: id=%s", broadcast_id)

    # ライブストリーム作成
    stream = youtube.liveStreams().insert(
        part="snippet,cdn",
        body={
            "snippet": {"title": title},
            "cdn": {
                "frameRate": "30fps",
                "ingestionType": "rtmp",
                "resolution": "1080p",
            },
        },
    ).execute()

    logger.info("ライブストリーム作成完了: id=%s", stream["id"])

    # ブロードキャストとストリームを紐付け
    youtube.liveBroadcasts().bind(
        part="id,contentDetails",
        id=broadcast_id,
        streamId=stream["id"],
    ).execute()

    logger.info("ブロードキャストとストリームを紐付けました")
    return broadcast_id


# ──────────────────────────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────────────────────────

def main():
    """メイン処理"""
    # 日本時間（JST = UTC+9）で当日19時の開始時刻を生成
    JST = timezone(timedelta(hours=9))
    now = datetime.now(JST)
    today_19 = now.replace(hour=19, minute=0, second=0, microsecond=0)

    # 配信タイトル（例: 「【毎日19時】バーチャル競馬LIVE 4月6日」）
    title = f"【毎日19時】バーチャル競馬LIVE {today_19.month}月{today_19.day}日"

    # ISO 8601 形式（例: "2025-04-06T19:00:00+09:00"）
    scheduled_start_time = today_19.isoformat()

    print(f"[INFO] 配信タイトル: {title}", file=sys.stderr)
    print(f"[INFO] 開始時刻: {scheduled_start_time}", file=sys.stderr)

    try:
        video_id = create_broadcast(title, scheduled_start_time)
        print(f"[INFO] 配信枠を作成しました: https://youtu.be/{video_id}", file=sys.stderr)
        # video_id のみ標準出力に出力（auto_start.bat で取得するため）
        print(video_id)
        sys.exit(0)
    except Exception as e:
        print(f"[ERROR] 配信枠の作成に失敗しました: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

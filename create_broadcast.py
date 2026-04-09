#!/usr/bin/env python3
"""
YouTube ライブ配信枠 自動作成スクリプト

OAuth2認証でYouTube LiveのブロードキャストをAPI経由で作成します。
認証トークンはtoken.jsonに保存され、2回目以降は自動使用されます。

複数のGoogle Cloudプロジェクトを登録しておくと、1つ目がクォータ超過の場合に
自動で2つ目にフォールバックします。

使い方:
    python create_broadcast.py
    -> 作成した VIDEO_ID を標準出力に1行出力します。
    -> エラー時は何も出力せず終了コード1で終了します。

必要ファイル（1つ目のプロジェクト）:
    client_secret.json  - Google Cloud ConsoleでダウンロードしたOAuth2クライアント情報
    token.json          - 認証トークン（初回認証後に自動生成・再利用）

2つ目のプロジェクト（任意）:
    client_secret2.json
    token2.json
"""

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

# 認証情報セット（順番に試みる）
# client_secret2.json / token2.json を置くと2つ目のプロジェクトとして使われる
CREDENTIAL_SETS = [
    (
        os.path.join(_BASE_DIR, "client_secret.json"),
        os.path.join(_BASE_DIR, "token.json"),
    ),
    (
        os.path.join(_BASE_DIR, "client_secret2.json"),
        os.path.join(_BASE_DIR, "token2.json"),
    ),
]


# ──────────────────────────────────────────────────────────────────
# 認証
# ──────────────────────────────────────────────────────────────────

def get_credentials(client_secret_file: str, token_file: str):
    """
    OAuth2認証情報を取得する。

    token_file が存在すれば再利用し、期限切れならリフレッシュする。
    token_file が存在しない場合はブラウザで初回認証フローを実行する。

    Args:
        client_secret_file: OAuthクライアント情報JSONのパス
        token_file:         トークン保存先JSONのパス

    Returns:
        google.oauth2.credentials.Credentials

    Raises:
        FileNotFoundError: client_secret_file が見つからない場合
    """
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None

    # 既存トークンを読み込む
    if os.path.exists(token_file):
        try:
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)
            logger.info("%s からトークンを読み込みました", token_file)
        except Exception as e:
            logger.warning("%s の読み込みに失敗しました（再認証します）: %s", token_file, e)
            creds = None

    # トークンが無効または期限切れの場合
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                logger.info("アクセストークンをリフレッシュしました")
            except Exception as e:
                logger.warning("トークンのリフレッシュに失敗しました（再認証します）: %s", e)
                creds = None

        if not creds:
            if not os.path.exists(client_secret_file):
                raise FileNotFoundError(client_secret_file)

            flow = InstalledAppFlow.from_client_secrets_file(client_secret_file, SCOPES)
            creds = flow.run_local_server(port=0)
            print("[INFO] 認証が完了しました", file=sys.stderr)

        # トークンを保存（次回以降は自動使用）
        try:
            with open(token_file, "w", encoding="utf-8") as f:
                f.write(creds.to_json())
            logger.info("%s を保存しました", token_file)
        except Exception as e:
            logger.warning("%s の保存に失敗しました: %s", token_file, e)

    return creds


# ──────────────────────────────────────────────────────────────────
# 配信枠の作成
# ──────────────────────────────────────────────────────────────────

STREAM_ID_FILE       = os.path.join(_BASE_DIR, "stream_id.txt")
STREAM_SETTINGS_FILE = os.path.join(_BASE_DIR, "stream_settings.txt")


def _is_rate_limit_error(e) -> bool:
    """HttpError が userRequestsExceedRateLimit かどうかを判定する"""
    try:
        status = int(e.resp.status)
    except Exception:
        return False
    return status == 403 and "userRequestsExceedRateLimit" in str(e)


def _get_or_create_stream(youtube) -> dict:
    """
    ライブストリームを取得または新規作成する。

    stream_id.txt が存在すればそのストリームを再利用し、
    存在しなければ新規作成して stream_id.txt に保存する。
    ストリームを再利用することでOBSのストリームキーを固定できる。

    Returns:
        liveStreams リソース dict（cdn.ingestionInfo を含む）
    """
    if os.path.exists(STREAM_ID_FILE):
        with open(STREAM_ID_FILE, "r") as f:
            stream_id = f.read().strip()
        if stream_id:
            resp = youtube.liveStreams().list(
                part="snippet,cdn", id=stream_id
            ).execute()
            if resp.get("items"):
                logger.info("既存ストリームを再利用: id=%s", stream_id)
                return resp["items"][0]
            logger.warning("保存済みストリームID(%s)が見つかりません。新規作成します。", stream_id)

    stream = youtube.liveStreams().insert(
        part="snippet,cdn",
        body={
            "snippet": {"title": "バーチャル競馬LIVE ストリーム"},
            "cdn": {
                "frameRate": "30fps",
                "ingestionType": "rtmp",
                "resolution": "1080p",
            },
        },
    ).execute()

    with open(STREAM_ID_FILE, "w") as f:
        f.write(stream["id"])
    logger.info("新規ストリーム作成・保存: id=%s", stream["id"])
    return stream


def _do_create_broadcast(youtube, title: str, scheduled_start_time: str) -> tuple:
    """
    youtube クライアントを使って配信枠を作成する（内部用）。

    rate limit エラーは呼び出し元に伝播させる（フォールバック処理のため）。

    Args:
        scheduled_start_time: ISO 8601 形式の開始時刻。None の場合は即時配信（縦型対応）。

    Returns:
        (broadcast_id, rtmp_server, stream_key)
    """
    snippet = {
        "title": title,
        "description": (
            "バーチャル競馬LIVE 自動配信\n\n"
            "コメントで馬券を購入しよう！\n"
            "  !単勝 [馬番] [金額]   例: !単勝 3 500\n"
            "  !複勝 [馬番] [金額]   例: !複勝 3 500\n"
            "  !残高"
        ),
    }
    if scheduled_start_time:
        snippet["scheduledStartTime"] = scheduled_start_time

    broadcast = youtube.liveBroadcasts().insert(
        part="snippet,status,contentDetails",
        body={
            "snippet": snippet,
            "status": {"privacyStatus": "unlisted"},
            "contentDetails": {
                "enableAutoStart": True,
                "enableAutoStop": True,
                "enableDvr": False,
                "latencyPreference": "ultraLow",
            },
        },
    ).execute()

    broadcast_id = broadcast["id"]
    logger.info("ブロードキャスト作成完了: id=%s", broadcast_id)

    stream = _get_or_create_stream(youtube)
    ingestion = stream["cdn"]["ingestionInfo"]
    rtmp_server = ingestion["ingestionAddress"]
    stream_key  = ingestion["streamName"]

    youtube.liveBroadcasts().bind(
        part="id,contentDetails",
        id=broadcast_id,
        streamId=stream["id"],
    ).execute()
    logger.info("ブロードキャストとストリームを紐付けました")

    with open(STREAM_SETTINGS_FILE, "w", encoding="utf-8") as f:
        f.write(f"{rtmp_server}\n{stream_key}\n")
    logger.info("ストリーム設定を保存: %s", STREAM_SETTINGS_FILE)

    return broadcast_id, rtmp_server, stream_key


def create_broadcast(title: str, scheduled_start_time: str) -> tuple:
    """
    YouTube ライブ配信枠（限定公開）を作成する。

    CREDENTIAL_SETS に登録された認証情報を順番に試み、
    クォータ超過（userRequestsExceedRateLimit）の場合は次のプロジェクトへ
    即座にフォールバックする。

    Args:
        title:                 配信タイトル
        scheduled_start_time:  ISO 8601 形式の開始時刻

    Returns:
        (video_id, rtmp_server, stream_key) のタプル

    Raises:
        Exception: 全プロジェクトで失敗した場合
    """
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError

    # 設定済み（client_secret*.json が存在する）セットのみ対象
    active_sets = [
        (idx, cs, tk)
        for idx, (cs, tk) in enumerate(CREDENTIAL_SETS, 1)
        if os.path.exists(cs)
    ]

    if not active_sets:
        cs_path = CREDENTIAL_SETS[0][0]
        print(
            f"[ERROR] {cs_path} が見つかりません。\n"
            "Google Cloud Console で OAuth2 クライアント ID を作成し、\n"
            "client_secret.json をプロジェクトフォルダに配置してください。\n"
            "詳細は README.md の「OAuth2 の設定手順」を参照してください。",
            file=sys.stderr,
        )
        raise FileNotFoundError(cs_path)

    last_error = None
    for idx, cs_file, tk_file in active_sets:
        print(
            f"[INFO] プロジェクト{idx}で配信枠を作成します"
            f" ({os.path.basename(cs_file)})",
            file=sys.stderr,
        )
        try:
            creds = get_credentials(cs_file, tk_file)
            youtube = build("youtube", "v3", credentials=creds)
            return _do_create_broadcast(youtube, title, scheduled_start_time)

        except HttpError as e:
            if _is_rate_limit_error(e):
                print(
                    f"[WARN] プロジェクト{idx}のクォータが超過しています。",
                    file=sys.stderr,
                )
                last_error = e
                if idx < len(active_sets):
                    print("[INFO] 次のプロジェクトに切り替えます...", file=sys.stderr)
                continue
            raise

    print(
        "[ERROR] 全プロジェクトでクォータ超過です。明日再試行してください。",
        file=sys.stderr,
    )
    raise last_error


# ──────────────────────────────────────────────────────────────────
# メイン
# ──────────────────────────────────────────────────────────────────

def main():
    """メイン処理"""
    import argparse

    parser = argparse.ArgumentParser(
        description="YouTube ライブ配信枠を自動作成します。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "例:\n"
            "  py -3.12 create_broadcast.py                              # 当日19時で作成\n"
            "  py -3.12 create_broadcast.py --start 2026-04-06T21:00:00+09:00\n"
        ),
    )
    parser.add_argument(
        "--start",
        metavar="DATETIME",
        help="配信開始時刻（ISO 8601形式）。例: 2026-04-06T21:00:00+09:00。省略時は当日19時(JST)。",
    )
    parser.add_argument(
        "--instant",
        action="store_true",
        help="即時配信モード（縦型ライブフィード対応）。スケジュール設定なしで作成する。",
    )
    args = parser.parse_args()

    JST = timezone(timedelta(hours=9))
    now = datetime.now(JST)

    if args.instant:
        # 即時配信: scheduledStartTime を設定しない（縦型ライブフィードに表示される）
        title = f"【コメント参加型】バーチャル競馬LIVE {now.month}月{now.day}日"
        scheduled_start_time = None
        print(f"[INFO] 即時配信モード（縦型ライブフィード対応）", file=sys.stderr)
        print(f"[INFO] 配信タイトル: {title}", file=sys.stderr)
    else:
        if args.start:
            try:
                start_dt = datetime.fromisoformat(args.start)
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=JST)
            except ValueError:
                print(
                    f"[ERROR] --start の形式が不正です: {args.start!r}\n"
                    "ISO 8601 形式で指定してください。例: 2026-04-06T21:00:00+09:00",
                    file=sys.stderr,
                )
                sys.exit(1)
        else:
            start_dt = now.replace(hour=19, minute=0, second=0, microsecond=0)

        if start_dt <= now + timedelta(minutes=1):
            adjusted = now + timedelta(minutes=1)
            print(
                f"[INFO] 指定時刻({start_dt.strftime('%H:%M')})が過去または直近のため、"
                f"{adjusted.strftime('%H:%M')} に自動調整します。",
                file=sys.stderr,
            )
            start_dt = adjusted

        title = f"【コメント参加型】バーチャル競馬LIVE {start_dt.month}月{start_dt.day}日"
        scheduled_start_time = start_dt.isoformat()
        print(f"[INFO] 配信タイトル: {title}", file=sys.stderr)
        print(f"[INFO] 開始時刻: {scheduled_start_time}", file=sys.stderr)

    try:
        video_id, rtmp_server, stream_key = create_broadcast(title, scheduled_start_time)
        print(f"[INFO] 配信枠を作成しました: https://youtu.be/{video_id}", file=sys.stderr)
        print(f"[INFO] RTMP Server : {rtmp_server}", file=sys.stderr)
        print(f"[INFO] Stream Key  : {stream_key}", file=sys.stderr)
        print(video_id)
        sys.exit(0)
    except Exception as e:
        print(f"[ERROR] 配信枠の作成に失敗しました: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

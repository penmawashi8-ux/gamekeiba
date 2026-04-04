"""
エントリーポイント

使用方法:
  # 本番モード（YouTube Live）
  python main.py VIDEO_ID

  # テストモード（ダミーコメント自動投入）
  python main.py --test

  # レース回数指定 & OBS制御
  python main.py VIDEO_ID --races 5

  # YouTube配信枠を自動作成して起動
  python main.py --create-broadcast --title "競馬ゲーム" --start-time "2025-01-01T18:00:00Z"

環境変数:
  YOUTUBE_API_KEY   YouTube Data API v3 のAPIキー
  OBS_PASSWORD      OBS WebSocket パスワード（省略可）
  GAME_FONT_PATH    日本語フォントファイルのパス（省略可）
"""

import sys
import os
import argparse
import logging
import queue
import signal
import time

# ──────────────────────────────────────────────────────────────────
# ロガー設定（ゲーム起動前に設定）
# ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ローカルモジュール
from user_manager import UserManager
from betting import BettingManager
from obs_controller import OBSController
from youtube_client import YouTubeClient, TestClient, create_live_broadcast
from game import Game


# ──────────────────────────────────────────────────────────────────
# 引数パーサー
# ──────────────────────────────────────────────────────────────────

def build_arg_parser() -> argparse.ArgumentParser:
    """コマンドライン引数パーサーを構築する"""
    parser = argparse.ArgumentParser(
        description="YouTube LIVEコメント連動 競馬ゲーム",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  python main.py abc123XYZ                    # 本番起動
  python main.py --test                       # テストモード
  python main.py abc123XYZ --races 5          # 5レースで自動終了
  python main.py --test --races 3             # テスト3レース
  python main.py --create-broadcast \\
      --title "競馬LIVE" \\
      --start-time "2025-06-01T19:00:00Z"    # 配信枠作成のみ
        """,
    )

    # メインモード（video_id または --test のどちらか）
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "video_id",
        nargs="?",
        help="YouTube ライブ配信の video_id",
    )
    mode_group.add_argument(
        "--test",
        action="store_true",
        help="テストモード: ダミーコメントを自動投入する",
    )

    # レース設定
    parser.add_argument(
        "--races",
        type=int,
        default=10,
        metavar="N",
        help="レースをN回消化したら自動終了（デフォルト: 10）",
    )

    # OBS 設定
    parser.add_argument(
        "--obs-host",
        default="localhost",
        help="OBS WebSocket ホスト（デフォルト: localhost）",
    )
    parser.add_argument(
        "--obs-port",
        type=int,
        default=4455,
        help="OBS WebSocket ポート（デフォルト: 4455）",
    )
    parser.add_argument(
        "--no-obs",
        action="store_true",
        help="OBS制御を無効化する",
    )

    # YouTube配信枠の自動作成
    parser.add_argument(
        "--create-broadcast",
        action="store_true",
        help="YouTube ライブ配信枠を作成して終了する（OAuth2が必要）",
    )
    parser.add_argument(
        "--title",
        default="YouTube競馬ゲーム LIVE",
        help="配信タイトル（--create-broadcast と組み合わせて使用）",
    )
    parser.add_argument(
        "--start-time",
        default=None,
        metavar="ISO8601",
        help="配信開始時刻（例: 2025-01-01T18:00:00Z）",
    )

    # デバッグ
    parser.add_argument(
        "--debug",
        action="store_true",
        help="デバッグログを有効にする",
    )

    return parser


# ──────────────────────────────────────────────────────────────────
# メイン処理
# ──────────────────────────────────────────────────────────────────

def main() -> int:
    """
    エントリーポイント。

    Returns:
        終了コード（0: 正常, 1: エラー）
    """
    parser = build_arg_parser()
    args = parser.parse_args()

    # デバッグモード
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # ── YouTube配信枠の自動作成モード ──────────────────────────────
    if args.create_broadcast:
        api_key = os.environ.get("YOUTUBE_API_KEY", "")
        if not api_key:
            logger.error("環境変数 YOUTUBE_API_KEY が設定されていません")
            return 1
        if not args.start_time:
            logger.error("--start-time を指定してください（例: 2025-01-01T18:00:00Z）")
            return 1

        video_id = create_live_broadcast(api_key, args.title, args.start_time)
        if video_id:
            print(f"\n配信枠を作成しました。\nvideo_id: {video_id}")
            print(f"\n起動コマンド:\n  python main.py {video_id} --races {args.races}")
            return 0
        else:
            logger.error("配信枠の作成に失敗しました")
            return 1

    # ── 起動モードチェック ─────────────────────────────────────────
    if not args.test and not args.video_id:
        parser.print_help()
        print("\nエラー: video_id または --test を指定してください")
        return 1

    # ── YouTube APIキー確認（テストモード以外）────────────────────
    api_key = os.environ.get("YOUTUBE_API_KEY", "")
    if not args.test and not api_key:
        logger.error(
            "環境変数 YOUTUBE_API_KEY が設定されていません\n"
            "  export YOUTUBE_API_KEY='your_api_key'"
        )
        return 1

    logger.info("=" * 60)
    logger.info("YouTube LIVE 競馬ゲーム 起動中...")
    logger.info("モード: %s", "テスト" if args.test else "本番")
    logger.info("最大レース数: %d", args.races)
    logger.info("=" * 60)

    # ── コンポーネント初期化 ───────────────────────────────────────
    command_queue: queue.Queue = queue.Queue()
    user_manager = UserManager()
    betting_manager = BettingManager()

    # OBSコントローラー
    obs_password = os.environ.get("OBS_PASSWORD", "")
    obs_ctrl = OBSController(
        host=args.obs_host,
        port=args.obs_port,
        password=obs_password,
    )
    if not args.no_obs:
        connected = obs_ctrl.connect()
        if connected:
            obs_ctrl.start_stream()
        else:
            logger.warning("OBS に接続できませんでした。OBS制御をスキップします。")

    # YouTubeクライアント / テストクライアント
    if args.test:
        yt_client = TestClient(command_queue)
        yt_client.start()
        logger.info("テストクライアント起動")
    else:
        yt_client = YouTubeClient(args.video_id, api_key, command_queue)
        yt_client.start()
        logger.info("YouTube ポーリング開始: %s", args.video_id)

    # ゲームインスタンス
    game = Game(
        command_queue=command_queue,
        user_manager=user_manager,
        betting_manager=betting_manager,
        num_races=args.races,
        test_client=yt_client if args.test else None,
    )

    # ── SIGINT ハンドラー（Ctrl+C）────────────────────────────────
    def _signal_handler(sig, frame):
        logger.info("中断シグナルを受信しました。終了します...")
        game.is_running = False

    signal.signal(signal.SIGINT, _signal_handler)

    # ── ゲームループ実行 ──────────────────────────────────────────
    exit_code = 0
    try:
        game.run()
        logger.info("ゲーム正常終了（%d レース消化）", game.race_count)
    except Exception as e:
        logger.exception("ゲームエラー: %s", e)
        exit_code = 1
    finally:
        # クリーンアップ
        logger.info("後処理中...")

        if args.test:
            yt_client.stop()
        else:
            yt_client.stop()

        if not args.no_obs:
            try:
                obs_ctrl.stop_stream()
                obs_ctrl.disconnect()
                logger.info("OBS 配信を停止しました")
            except Exception as e:
                logger.warning("OBS クリーンアップエラー: %s", e)

    logger.info("終了しました")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

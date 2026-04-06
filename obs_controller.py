"""
OBS WebSocket コントローラーモジュール

obs-websocket 5.x プロトコル（obsws-python ライブラリ）を使用して
OBS Studio の配信開始・停止を制御する。

obsws-python が未インストールの場合はダミーモードで動作し、
ゲームの他の機能に影響を与えない。
"""

import logging
import time

logger = logging.getLogger(__name__)

# obsws-python のインポートを試みる（未インストール時はダミーモード）
try:
    import obsws_python as obs
    OBS_AVAILABLE = True
except ImportError:
    OBS_AVAILABLE = False
    logger.warning(
        "obsws-python が未インストールです。OBS制御はスキップされます。\n"
        "  pip install obsws-python"
    )


class OBSController:
    """
    OBS Studio WebSocket コントローラー。

    obsws-python が利用できない場合はダミーモードで動作し、
    全メソッドは何もせず正常終了する。
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 4455,
        password: str = "",
    ):
        """
        Args:
            host:     OBS WebSocket のホスト（デフォルト: localhost）
            port:     ポート番号（デフォルト: 4455）
            password: OBS WebSocket パスワード
        """
        self.host = host
        self.port = port
        self.password = password
        self._client = None
        self._connected = False
        self._dummy_mode = not OBS_AVAILABLE

    # ──────────────────────────────────────────────
    # 接続管理
    # ──────────────────────────────────────────────

    def connect(self) -> bool:
        """
        OBS WebSocket に接続する。

        Returns:
            True: 接続成功（またはダミーモード）
            False: 接続失敗
        """
        if self._dummy_mode:
            logger.info("[OBS ダミーモード] connect() 呼び出し")
            return True

        try:
            self._client = obs.ReqClient(
                host=self.host,
                port=self.port,
                password=self.password,
                timeout=5,
            )
            self._connected = True
            logger.info("OBS WebSocket に接続しました (%s:%d)", self.host, self.port)
            return True
        except Exception as e:
            logger.error("OBS WebSocket 接続失敗: %s", e)
            self._connected = False
            self._dummy_mode = True  # 接続失敗後はダミーモードに切り替え
            return False

    def disconnect(self):
        """OBS WebSocket との接続を切断する"""
        if self._dummy_mode:
            return
        try:
            if self._client:
                self._client.disconnect()
                self._connected = False
                logger.info("OBS WebSocket 接続を切断しました")
        except Exception as e:
            logger.warning("OBS 切断時エラー: %s", e)

    def is_connected(self) -> bool:
        """接続状態を返す"""
        if self._dummy_mode:
            return True
        return self._connected

    # ──────────────────────────────────────────────
    # 配信制御
    # ──────────────────────────────────────────────

    def configure_stream(self, rtmp_server: str, stream_key: str) -> bool:
        """
        OBS のストリーム配信先（YouTubeのRTMPサーバーとストリームキー）を設定する。

        Args:
            rtmp_server: RTMP サーバーURL（例: rtmp://a.rtmp.youtube.com/live2）
            stream_key:  YouTube ストリームキー

        Returns:
            True: 設定成功（またはダミーモード）
        """
        if self._dummy_mode:
            logger.info("[OBS ダミーモード] configure_stream() 呼び出し")
            return True

        try:
            self._client.set_stream_service_settings(
                ss_type="rtmp_custom",
                ss_settings={
                    "server": rtmp_server,
                    "key": stream_key,
                },
            )
            logger.info("OBS ストリーム設定完了: server=%s", rtmp_server)
            return True
        except Exception as e:
            logger.error("OBS ストリーム設定エラー: %s", e)
            return False

    def start_stream(self) -> bool:
        """
        OBS の配信を開始する。

        Returns:
            True: 開始成功（またはダミーモード）
        """
        if self._dummy_mode:
            logger.info("[OBS ダミーモード] 配信開始")
            return True

        try:
            # 既に配信中でないか確認
            status = self._client.get_stream_status()
            if status.output_active:
                logger.info("OBS: 既に配信中です")
                return True

            self._client.start_stream()
            logger.info("OBS: 配信を開始しました")
            return True
        except Exception as e:
            logger.error("OBS 配信開始エラー: %s", e)
            return False

    def stop_stream(self) -> bool:
        """
        OBS の配信を停止する。

        Returns:
            True: 停止成功（またはダミーモード）
        """
        if self._dummy_mode:
            logger.info("[OBS ダミーモード] 配信停止")
            return True

        try:
            status = self._client.get_stream_status()
            if not status.output_active:
                logger.info("OBS: 配信は既に停止しています")
                return True

            self._client.stop_stream()
            logger.info("OBS: 配信を停止しました")
            return True
        except Exception as e:
            logger.error("OBS 配信停止エラー: %s", e)
            return False

    def get_stream_status(self) -> dict:
        """
        配信ステータスを返す。

        Returns:
            {
                "streaming": bool,   配信中かどうか
                "recording": bool,   録画中かどうか
                "timecode":  str,    配信時間
            }
        """
        if self._dummy_mode:
            return {"streaming": False, "recording": False, "timecode": "00:00:00"}

        try:
            status = self._client.get_stream_status()
            return {
                "streaming": status.output_active,
                "recording": False,
                "timecode": getattr(status, "output_timecode", "00:00:00"),
            }
        except Exception as e:
            logger.warning("OBS ステータス取得エラー: %s", e)
            return {"streaming": False, "recording": False, "timecode": "00:00:00"}

    def is_obs_running(self) -> bool:
        """
        OBS が起動しているか確認する。

        接続を試み、成功すれば True を返す。
        """
        if self._dummy_mode and not OBS_AVAILABLE:
            return False

        try:
            test_client = obs.ReqClient(
                host=self.host,
                port=self.port,
                password=self.password,
                timeout=3,
            )
            test_client.disconnect()
            return True
        except Exception:
            return False

#!/usr/bin/env bash
# ============================================================
# auto_start.sh - YouTube LIVE 競馬ゲーム 全自動起動 (Mac/Linux)
#
# このスクリプトは以下を自動で行います:
#   1. YouTube 配信枠を作成 (create_broadcast.py)
#   2. 作成した配信枠の video_id で即座にゲーム起動
#   3. OBS に RTMP 設定を自動反映して配信開始
#
# 設定箇所:
#   YOUTUBE_API_KEY : YouTube Data API v3 キー
#   OBS_PASSWORD    : OBS WebSocket パスワード（なければ空欄）
#   RACES           : レース数（デフォルト 10）
#   START_TIME      : 配信開始時刻 ISO8601（省略時＝今から1分後）
#
# cron 登録例（毎日 19:00 に自動実行）:
#   0 19 * * * /path/to/gamekeiba/auto_start.sh >> /path/to/gamekeiba/auto_start.log 2>&1
# ============================================================

# ── ユーザー設定 ─────────────────────────────────────────────
export YOUTUBE_API_KEY="YOUR_YOUTUBE_API_KEY_HERE"
export OBS_PASSWORD=""
export GAME_FONT_PATH=""
RACES=10
START_TIME=""   # 例: "2026-04-07T21:00:00+09:00"（空欄なら今から1分後）

# ── スクリプトフォルダへ移動 ─────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "${SCRIPT_DIR}"

# ── 仮想環境のセットアップ ───────────────────────────────────
VENV_DIR="${SCRIPT_DIR}/.venv"
if [ -d "${VENV_DIR}" ]; then
    PYTHON="${VENV_DIR}/bin/python"
else
    echo "[INFO] 仮想環境を作成します..."
    python3 -m venv "${VENV_DIR}"
    PYTHON="${VENV_DIR}/bin/python"
    "${PYTHON}" -m pip install --upgrade pip -q
    "${PYTHON}" -m pip install -r requirements.txt -q
fi

# ── 日本語フォント自動検索 ───────────────────────────────────
if [ -z "${GAME_FONT_PATH}" ]; then
    for fp in \
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc" \
        "/usr/share/fonts/truetype/noto/NotoSansCJKjp-Regular.otf" \
        "/usr/share/fonts/truetype/ipafont-gothic/ipag.ttf" \
        "/Library/Fonts/Osaka.ttf"
    do
        if [ -f "${fp}" ]; then
            export GAME_FONT_PATH="${fp}"
            echo "[INFO] フォント: ${fp}"
            break
        fi
    done
fi

# ── API キーチェック ─────────────────────────────────────────
if [ "${YOUTUBE_API_KEY}" = "YOUR_YOUTUBE_API_KEY_HERE" ]; then
    echo "[ERROR] YOUTUBE_API_KEY を設定してください。"
    echo "        このファイルをエディタで開いて YOUTUBE_API_KEY= の行を編集してください。"
    exit 1
fi

echo "========================================"
echo " YouTube LIVE 競馬ゲーム 全自動起動"
echo " 配信枠を作成中..."
echo "========================================"

# ── 配信枠作成 ───────────────────────────────────────────────
if [ -z "${START_TIME}" ]; then
    VIDEO_ID=$("${PYTHON}" create_broadcast.py 2>/dev/null)
else
    VIDEO_ID=$("${PYTHON}" create_broadcast.py --start "${START_TIME}" 2>/dev/null)
fi

if [ -z "${VIDEO_ID}" ]; then
    echo "[ERROR] 配信枠の作成に失敗しました。"
    echo "        client_secret.json / token.json を確認してください。"
    exit 1
fi

echo "[INFO] 配信枠作成完了: video_id = ${VIDEO_ID}"
echo "[INFO] https://youtu.be/${VIDEO_ID}"

# ── ゲーム起動（OBS は main.py が stream_settings.txt を読んで自動設定）──
echo "========================================"
echo " ゲームを起動します..."
echo " video_id : ${VIDEO_ID}"
echo " races    : ${RACES}"
echo " 開始時刻 : $(date)"
echo "========================================"

"${PYTHON}" main.py "${VIDEO_ID}" --races "${RACES}"

echo "========================================"
echo " 終了時刻: $(date)"
echo "========================================"

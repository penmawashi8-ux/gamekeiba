#!/usr/bin/env bash
# ============================================================
# auto_start_vertical.sh - YouTube LIVE 競馬ゲーム 縦型全自動起動
#
# 縦型配信（720×1280 = スマホ縦向き・YouTube Shorts LIVE）用
# OBS は 1080×1920 キャンバスで設定してください（下記参照）
# ============================================================

export YOUTUBE_API_KEY="YOUR_YOUTUBE_API_KEY_HERE"
export OBS_PASSWORD=""
export GAME_FONT_PATH=""
RACES=10
START_TIME=""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "${SCRIPT_DIR}"

VENV_DIR="${SCRIPT_DIR}/.venv"
if [ -d "${VENV_DIR}" ]; then
    PYTHON="${VENV_DIR}/bin/python"
else
    python3 -m venv "${VENV_DIR}"
    PYTHON="${VENV_DIR}/bin/python"
    "${PYTHON}" -m pip install --upgrade pip -q
    "${PYTHON}" -m pip install -r requirements.txt -q
fi

if [ -z "${GAME_FONT_PATH}" ]; then
    for fp in \
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc" \
        "/usr/share/fonts/truetype/noto/NotoSansCJKjp-Regular.otf" \
        "/usr/share/fonts/truetype/ipafont-gothic/ipag.ttf" \
        "/Library/Fonts/Osaka.ttf"
    do
        [ -f "${fp}" ] && export GAME_FONT_PATH="${fp}" && break
    done
fi

if [ "${YOUTUBE_API_KEY}" = "YOUR_YOUTUBE_API_KEY_HERE" ]; then
    echo "[ERROR] YOUTUBE_API_KEY を設定してください。"
    exit 1
fi

echo "========================================"
echo " YouTube LIVE 競馬ゲーム 縦型全自動起動"
echo " 配信枠を作成中..."
echo "========================================"

if [ -z "${START_TIME}" ]; then
    VIDEO_ID=$("${PYTHON}" create_broadcast.py 2>/dev/null)
else
    VIDEO_ID=$("${PYTHON}" create_broadcast.py --start "${START_TIME}" 2>/dev/null)
fi

[ -z "${VIDEO_ID}" ] && echo "[ERROR] 配信枠の作成に失敗しました。" && exit 1

echo "[INFO] https://youtu.be/${VIDEO_ID}"
echo "========================================"
echo " 縦型モードでゲームを起動します..."
echo "========================================"

"${PYTHON}" main.py "${VIDEO_ID}" --races "${RACES}" --vertical

#!/usr/bin/env bash
# ============================================================
# YouTube LIVE 競馬ゲーム 起動スクリプト（Mac/Linux用）
# ============================================================
# 使用前に以下を設定してください:
#   1. YOUTUBE_API_KEY を設定
#   2. VIDEO_ID を設定（またはコマンドライン引数で渡す）
#   3. OBS_PASSWORD を設定（OBSのWebSocketパスワード）
#
# cron 登録例（毎日19時に5レース実行）:
#   0 19 * * * /path/to/gamekeiba/start.sh >> /path/to/gamekeiba/gamekeiba.log 2>&1
# ============================================================

# ── 設定項目 ──────────────────────────────────────────────────────
export YOUTUBE_API_KEY="YOUR_YOUTUBE_API_KEY_HERE"
export OBS_PASSWORD=""                      # OBS WebSocket パスワード（未設定なら空）
export GAME_FONT_PATH=""                    # 日本語フォントパス（空なら自動検索）

VIDEO_ID="${1:-YOUR_VIDEO_ID_HERE}"        # 引数1でvideo_idを渡せる
RACES="${2:-10}"                           # 引数2でレース数を指定
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"
PYTHON="python3"

# ── 仮想環境の確認・作成 ──────────────────────────────────────────
if [ -d "${VENV_DIR}" ]; then
    source "${VENV_DIR}/bin/activate"
    PYTHON="${VENV_DIR}/bin/python"
else
    echo "[INFO] 仮想環境が見つかりません。セットアップを実行します..."
    python3 -m venv "${VENV_DIR}"
    source "${VENV_DIR}/bin/activate"
    PYTHON="${VENV_DIR}/bin/python"
    pip install --upgrade pip
    pip install -r "${SCRIPT_DIR}/requirements.txt"
fi

# ── 日本語フォント自動検索 ────────────────────────────────────────
if [ -z "${GAME_FONT_PATH}" ]; then
    for font_path in \
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc" \
        "/usr/share/fonts/truetype/noto/NotoSansCJKjp-Regular.otf" \
        "/usr/share/fonts/truetype/ipafont-gothic/ipag.ttf" \
        "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf" \
        "/Library/Fonts/Osaka.ttf" \
        "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"
    do
        if [ -f "${font_path}" ]; then
            export GAME_FONT_PATH="${font_path}"
            echo "[INFO] 日本語フォント: ${font_path}"
            break
        fi
    done
fi

# ── OBS 起動確認 ──────────────────────────────────────────────────
# OBS が起動していなければ警告（自動起動は環境依存なのでコメントアウト）
# if ! pgrep -x "obs" > /dev/null 2>&1; then
#     echo "[WARN] OBS が起動していません。起動してください。"
# fi

# ── ゲーム起動 ────────────────────────────────────────────────────
cd "${SCRIPT_DIR}"
echo "========================================"
echo " YouTube LIVE 競馬ゲーム"
echo " video_id : ${VIDEO_ID}"
echo " races    : ${RACES}"
echo " 開始時刻 : $(date)"
echo "========================================"

if [ "${VIDEO_ID}" = "YOUR_VIDEO_ID_HERE" ]; then
    echo "[INFO] VIDEO_ID が未設定です。テストモードで起動します。"
    "${PYTHON}" main.py --test --races "${RACES}"
else
    "${PYTHON}" main.py "${VIDEO_ID}" --races "${RACES}"
fi

echo "========================================"
echo " 終了時刻: $(date)"
echo "========================================"

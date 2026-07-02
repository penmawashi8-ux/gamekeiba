#!/usr/bin/env bash
# ショート動画ワンコマンド生成パイプライン
#
#   ./video_tools/run_pipeline.sh
#
# やること:
#   1. VOICEVOXエンジン・フロントエンドが起動していなければ起動して待機
#   2. バックエンドを再起動(第1レースの受付開始から録画するため毎回まっさらにする)
#   3. 自動プレイ録画 → ショート動画 + タイトル・説明文を生成
#
# 環境変数:
#   VIDEO_OUT     出力ディレクトリ(既定: ~/video_work)
#   VOICEVOX_RUN  VOICEVOXエンジンの run 実行ファイルパス(未起動時の自動起動に使用)
#   CHROME_PATH   Chromium実行ファイル(未指定ならPlaywright標準)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export VIDEO_OUT="${VIDEO_OUT:-$HOME/video_work}"
mkdir -p "$VIDEO_OUT"

wait_http() { # url, 試行回数
  for _ in $(seq 1 "$2"); do
    curl -sf -o /dev/null "$1" && return 0
    sleep 2
  done
  echo "ERROR: $1 が起動しませんでした" >&2
  return 1
}

# 1. VOICEVOX
if ! curl -sf -o /dev/null http://127.0.0.1:50021/version; then
  if [ -z "${VOICEVOX_RUN:-}" ]; then
    echo "ERROR: VOICEVOXが起動していません。VOICEVOX_RUN にエンジンのパスを指定してください" >&2
    exit 1
  fi
  echo "VOICEVOXを起動します..."
  nohup "$VOICEVOX_RUN" --host 127.0.0.1 --port 50021 > "$VIDEO_OUT/voicevox.log" 2>&1 &
fi
wait_http http://127.0.0.1:50021/version 60

# 2. フロントエンド
if ! curl -sf -o /dev/null http://localhost:3000; then
  echo "フロントエンドを起動します..."
  (cd "$ROOT/frontend" && [ -d node_modules ] || npm ci)
  (cd "$ROOT/frontend" && nohup npm run dev > "$VIDEO_OUT/frontend.log" 2>&1 &)
fi
wait_http http://localhost:3000 30

# 3. バックエンドを再起動(レース1の受付開始から録るため)
fuser -k 8000/tcp 2>/dev/null || true
sleep 1
rm -f "$ROOT/backend/users.db"
(cd "$ROOT/backend" && nohup python3 -m uvicorn main:app --host 127.0.0.1 --port 8000 \
  > "$VIDEO_OUT/backend.log" 2>&1 &)
if ! wait_http http://127.0.0.1:8000/health 30; then
  echo "--- backend.log ---" >&2
  tail -n 30 "$VIDEO_OUT/backend.log" >&2 || true
  exit 1
fi

# 4. 録画 → 動画 + メタデータ生成
python3 "$ROOT/video_tools/record_play_vertical.py"
python3 "$ROOT/video_tools/make_shorts.py"

echo
echo "=== 完成 ==="
echo "動画:               $VIDEO_OUT/keiba_shorts.mp4"
echo "タイトル・説明文:   $VIDEO_OUT/metadata.md"

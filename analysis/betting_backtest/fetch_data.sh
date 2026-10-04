#!/usr/bin/env bash
# 検証用データ（keibamar/keiba_ai_ver3.0 の 2025年分）だけを取ってくる。
# リポジトリ全体は大きいので、年次結果CSVと2025年の払戻CSVだけを sparse checkout する。
set -euo pipefail
DEST="${1:-./keiba_ai_ver3.0}"
git clone --depth 1 --filter=blob:none --no-checkout https://github.com/keibamar/keiba_ai_ver3.0 "$DEST"
cd "$DEST"
git sparse-checkout init --no-cone
git sparse-checkout set '/data/race_result/*/2025_race_results.csv' '/data/race_info/race_returns/*/2025/*' '/data/race_schedule/race_time_id_list/2025*'
git checkout
echo "取得完了: python3 backtest.py $DEST"

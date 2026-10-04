#!/usr/bin/env bash
# 検証用データを取ってくる。どちらのリポジトリも大きいので、必要なファイルだけ sparse checkout する。
#   ./fetch_data.sh [keiba_ai_ver3.0 の置き場所] [keiba_core の置き場所]
set -euo pipefail
DEST="${1:-./keiba_ai_ver3.0}"
CORE="${2:-./keiba_core}"

# keibamar/keiba_ai_ver3.0: 2019年〜の結果・払戻・レース名（backtest.py の2025年検証と、年別データの補完・照合）
git clone --depth 1 --filter=blob:none --no-checkout https://github.com/keibamar/keiba_ai_ver3.0 "$DEST"
git -C "$DEST" sparse-checkout init --no-cone
git -C "$DEST" sparse-checkout set '/data/race_result/*/*_race_results.csv' '/data/race_info/race_returns/**' '/data/race_schedule/race_time_id_list/*'
git -C "$DEST" checkout

# iinumac/keiba_core: 2010年〜の解析済みデータ（年別ランキングの主データ。約40MB）
git clone --depth 1 --filter=blob:none --no-checkout https://github.com/iinumac/keiba_core "$CORE"
git -C "$CORE" sparse-checkout init --no-cone
git -C "$CORE" sparse-checkout set '/data/warehouse/**'
git -C "$CORE" checkout

echo "取得完了:"
echo "  python3 backtest.py $DEST                                   # 2025年のいろいろな買い方の検証"
echo "  python3 build_dataset.py $CORE $DEST <出力先>                 # 2010年〜の年別データ（coverage.md も更新）"
echo "  python3 ranking_data.py <出力先> && python3 make_video.py ranking2019"

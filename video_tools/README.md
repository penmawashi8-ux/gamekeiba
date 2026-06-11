# 実況プレイ動画 自動生成ツール

Webアプリ版(frontend + backend)を自動プレイし、VOICEVOXによる自動音声実況付きの
プレイ動画(MP4)を生成するパイプラインです。

`sample_keiba_jikkyo.mp4` が生成サンプル(約2分)です。

## 仕組み

1. **record_play.py** — Playwright(Chromium)でフロントエンドを操作して1レースをプレイ
   - 観戦用WebSocket接続でゲームイベント(出走馬・オッズ・レース展開・結果)をタイムスタンプ付きで記録
   - プレイヤーとして参加 → オッズを見て単勝・複勝を購入 → レース観戦 → 結果確認
   - Playwrightの録画機能で `raw.webm` とイベントログ `events.json` を出力
2. **build_audio.py** — イベントログを元にした実況台本をVOICEVOX(青山龍星)で音声合成し、
   ffmpegで各セリフをタイムライン配置して動画にミックス → `keiba_jikkyo.mp4`

## 必要なもの

- Python: `playwright websockets fastapi uvicorn[standard]`
- Chromium(`record_play.py` の `CHROME` パスを環境に合わせて変更)
- [VOICEVOXエンジン](https://github.com/VOICEVOX/voicevox_engine)(`http://127.0.0.1:50021` で起動)
- ffmpeg / 日本語フォント(fonts-noto-cjk)

## 実行手順

```bash
# 1. アプリを起動(レース1の受付開始から撮るため、バックエンドは直前に再起動する)
cd backend && uvicorn main:app --port 8000 &
cd frontend && npm run dev &

# 2. VOICEVOXエンジンを起動
/path/to/voicevox_engine/run --host 127.0.0.1 --port 50021 &

# 3. 自動プレイ+録画(約2分)
python3 video_tools/record_play.py

# 4. 録画をMP4化
ffmpeg -i raw.webm -r 30 -c:v libx264 -crf 20 -pix_fmt yuv420p video_nosound.mp4

# 5. 実況音声を合成してミックス
python3 video_tools/build_audio.py
```

注意: `build_audio.py` の台本(`LINES`)はサンプル収録時のレース展開
(出走馬名・着順・タイムスタンプ)に合わせて書かれています。
別のテイクを録る場合は `events.json` の内容に合わせて台本を更新してください。

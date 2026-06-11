# 実況プレイ動画 自動生成ツール

Webアプリ版(frontend + backend)を自動プレイし、VOICEVOXによる自動音声実況付きの
プレイ動画(MP4)を生成するパイプラインです。

- `sample_keiba_jikkyo.mp4` — 横長版サンプル(1280x720・約2分)
- `sample_keiba_shorts.mp4` — YouTubeショート向け縦版サンプル(1080x1920・約56秒)

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

## YouTubeショート向け縦動画

```bash
# 縦向き(540x960)で自動プレイ+録画 → raw_v.webm / events_v.json
python3 video_tools/record_play_vertical.py

# カット編集 + 実況自動生成 + BGM + 字幕 → keiba_shorts.mp4(1080x1920・約56秒)
python3 video_tools/make_shorts.py
```

冒頭には [ボドゲ広場](https://boardgamecat.com) の紹介カード
(`assets/intro_shorts.png`)が約3秒入ります。

`make_shorts.py` は横長版と違い**完全自動**です:

- イベントログから「オッズ発表〜ベット」「レース」「払い戻し」だけを残して
  ログインや待ち時間をカット(約56秒に圧縮)
- 実況台本はレース展開(先頭の入れ替わり・自分の馬の位置・的中/外れ)から自動生成。
  どんな結果のテイクでもそのまま動画化できます
- BGMはnumpyで合成したチップチューン風ループ(著作権フリー)を低音量でミックス
- 字幕は縦画面向けに大きめで焼き込み

## GitHub Actionsで実行する

`.github/workflows/make-shorts-video.yml` を用意してあります。

1. GitHubの **Actions** タブ → 「ショート動画生成」→ **Run workflow**
2. 10〜15分ほどで完了(VOICEVOXはキャッシュされるので2回目以降は速い)
3. 実行結果ページ下部の **Artifacts** から `keiba-shorts` をダウンロード

スクリプトは環境変数で調整できます:

| 環境変数 | 既定値 | 説明 |
|---|---|---|
| `VIDEO_OUT` | `/home/user/video_work` | 中間ファイル・出力先ディレクトリ |
| `CHROME_PATH` | (未指定) | Chromium実行ファイル。未指定ならPlaywright標準のChromium |
| `INTRO_IMG` | `video_tools/assets/intro_shorts.png` | 冒頭の紹介カード画像 |

注意: 録画は「第1レースの受付開始から」始める前提なので、
バックエンドは録画の直前に起動してください(ワークフローはそうなっています)。

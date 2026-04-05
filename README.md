# YouTube LIVE 競馬ゲーム

YouTube LIVEのコメントと連動するリアルタイム競馬ゲームです。  
視聴者がコメントで馬券を購入し、パリミュチュエル方式でオッズが変動します。

---

## 機能概要

- 出走馬8頭をランダム生成
- 馬券受付フェーズ（300秒）
  - `!単勝 [馬番] [金額]` で単勝購入
  - `!馬連 [馬番] [馬番] [金額]` で馬連購入
  - `!残高` で残高を画面表示
- リアルタイムオッズ表示（パリミュチュエル方式）
- Pygameによる横スクロールレースアニメーション（約30秒）
- 着順・払い戻し・残高ランキングTOP5を表示
- OBS WebSocket連携による配信自動開始・停止
- N回レース後に自動終了

---

## 必要環境

- Python 3.10 以上
- Pygame 2.5+
- OBS Studio（配信制御を使う場合）
  - obs-websocket プラグイン 5.x が必要

---

## インストール

```bash
# リポジトリをクローン
git clone <repo_url>
cd gamekeiba

# 仮想環境を作成してパッケージインストール
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 日本語フォントのインストール（Linux）

```bash
# Noto CJK フォントをインストール（Ubuntu/Debian）
sudo apt install fonts-noto-cjk

# IPA ゴシックをインストール
sudo apt install fonts-ipafont-gothic
```

---

## 環境変数の設定

| 変数名 | 説明 | 必須 |
|--------|------|------|
| `YOUTUBE_API_KEY` | YouTube Data API v3 のAPIキー | 本番モード必須 |
| `OBS_PASSWORD` | OBS WebSocket パスワード | OBS利用時 |
| `GAME_FONT_PATH` | 日本語フォントファイルのパス | 省略可（自動検索） |

```bash
# Linux/Mac
export YOUTUBE_API_KEY="AIza..."
export OBS_PASSWORD="your_password"

# Windows（コマンドプロンプト）
set YOUTUBE_API_KEY=AIza...
set OBS_PASSWORD=your_password
```

---

## YouTube Data API の取得方法

1. [Google Cloud Console](https://console.cloud.google.com/) にアクセス
2. 新規プロジェクトを作成
3. 「APIとサービス」→「ライブラリ」→「YouTube Data API v3」を有効化
4. 「認証情報」→「APIキーを作成」
5. 取得したAPIキーを `YOUTUBE_API_KEY` に設定

---

## 起動方法

### 本番モード

```bash
# 基本起動
python main.py YOUR_VIDEO_ID

# レース数指定（10レース後に自動終了）
python main.py YOUR_VIDEO_ID --races 10
```

### テストモード（ダミーコメント自動投入）

```bash
python main.py --test
python main.py --test --races 3
```

### OBSを使わずに起動

```bash
python main.py YOUR_VIDEO_ID --no-obs
```

### YouTube配信枠を自動作成

OAuth2認証が必要です。`client_secrets.json` をプロジェクトフォルダに配置してください。

```bash
python main.py --create-broadcast \
    --title "競馬ゲーム LIVE" \
    --start-time "2025-06-01T19:00:00Z"
```

---

## 起動スクリプト

### Linux/Mac（`start.sh`）

```bash
# 設定を編集
vim start.sh
# YOUTUBE_API_KEY を設定
# VIDEO_ID を設定（または引数で渡す）

# 起動
./start.sh                      # デフォルト設定
./start.sh abc123XYZ 5          # video_id と5レース指定
```

### Windows（`start.bat`）

**事前準備：** Windowsのシステム環境変数に `YOUTUBE_API_KEY` を設定してください（後述）。

```bat
REM 基本起動（VIDEO_IDを引数で渡す）
start.bat abc123XYZ

REM レース数を指定して起動（10レース後に自動終了）
start.bat abc123XYZ 10

REM VIDEO_ID 未指定の場合はテストモードで起動
start.bat
```

#### Windows 環境変数の設定方法

1. `Win + R` → `sysdm.cpl` → Enter
2. 「詳細設定」タブ → 「環境変数」をクリック
3. 「システム環境変数」の「新規」をクリック
4. 変数名: `YOUTUBE_API_KEY`、変数値: 取得したAPIキーを入力
5. OK で保存 → コマンドプロンプトを再起動

またはコマンドプロンプト（管理者）で一括設定：

```bat
REM システム環境変数に恒久設定（管理者権限が必要）
setx YOUTUBE_API_KEY "AIza..." /M
```

---

## タスクスケジューラ / cron への登録

### Linux/Mac（cron）

```bash
# crontab を開く
crontab -e

# 毎日19時に10レース実行する例
0 19 * * * /path/to/gamekeiba/start.sh YOUR_VIDEO_ID 10 >> /path/to/gamekeiba/gamekeiba.log 2>&1

# 毎週土曜20時に実行する例
0 20 * * 6 /path/to/gamekeiba/start.sh YOUR_VIDEO_ID 20 >> /path/to/gamekeiba/gamekeiba.log 2>&1
```

### Windows（タスクスケジューラ）

#### コマンドラインで登録する場合（推奨）

管理者権限のコマンドプロンプトで実行してください。

```bat
REM 毎日19時に abc123XYZ を 10レース実行（ログ出力あり）
schtasks /create /tn "競馬ゲーム" ^
  /tr "\"C:\path\to\gamekeiba\start.bat\" abc123XYZ 10" ^
  /sc daily /st 19:00 /ru SYSTEM

REM タスクの確認
schtasks /query /tn "競馬ゲーム" /fo LIST /v

REM タスクの削除
schtasks /delete /tn "競馬ゲーム" /f
```

#### GUIで設定する場合

1. `Win + R` → `taskschd.msc` → Enter でタスクスケジューラを開く
2. 右ペインの「タスクの作成」をクリック（※「基本タスク」ではなく「タスクの作成」を使う）
3. **「全般」タブ**
   - 名前: `競馬ゲーム`
   - セキュリティオプション: 「ユーザーがログオンしているかどうかにかかわらず実行する」を選択
   - 「最上位の特権で実行する」にチェック
4. **「トリガー」タブ** → 「新規」
   - タスクの開始: 「スケジュールに従う」
   - 毎日・時刻を指定（例: 19:00:00）
5. **「操作」タブ** → 「新規」
   - 操作: 「プログラムの開始」
   - プログラム/スクリプト: `C:\path\to\gamekeiba\start.bat`
   - 引数の追加: `abc123XYZ 10`（VIDEO_ID とレース数）
   - 開始（オプション）: `C:\path\to\gamekeiba`
6. **「条件」タブ**（スリープ起動の設定）
   - 「コンピューターをスリープ解除してこのタスクを実行する」にチェック ✅
   - 「AC電源に接続している場合にのみタスクを開始する」のチェックを **外す**（ノートPC等でバッテリー動作する場合）
7. **「設定」タブ**
   - 「タスクを要求時に実行する」にチェック
   - 「スケジュールされた開始時刻に実行中でも、タスクが終了しない場合は強制終了する」にチェック
8. OK → Windows ログインパスワードを入力して保存

#### スリープ中でも自動起動させる追加設定

Windowsの電源設定でスリープ解除タイマーを有効にする必要があります。

```bat
REM 管理者権限のコマンドプロンプトで実行
REM スリープ解除タイマーを有効にする
powercfg /setacvalueindex SCHEME_CURRENT SUB_SLEEP RTCWAKE 1
powercfg /setdcvalueindex SCHEME_CURRENT SUB_SLEEP RTCWAKE 1
powercfg /setactive SCHEME_CURRENT

REM 設定確認
powercfg /query SCHEME_CURRENT SUB_SLEEP RTCWAKE
```

または GUI で設定する場合：
1. `Win + R` → `powercfg.cpl` → Enter
2. 現在の電源プランの「プラン設定の変更」→「詳細な電源設定の変更」
3. 「スリープ」→「スリープ解除タイマーの許可」→「有効」に設定

---

## OBS WebSocket の設定

1. OBS Studio を起動
2. 「ツール」→「obs-websocket 設定」を開く
3. 「WebSocketサーバーを有効にする」をチェック
4. ポート: `4455`（デフォルト）
5. パスワードを設定し、`OBS_PASSWORD` 環境変数に設定

---

## ファイル構成

```
gamekeiba/
├── main.py           # エントリーポイント、引数処理
├── game.py           # ゲームループ、フェーズ管理、Pygame描画
├── horse.py          # 馬クラス、アニメーション描画
├── betting.py        # 馬券管理、パリミュチュエルオッズ計算
├── user_manager.py   # ユーザー管理（SQLite）
├── youtube_client.py # YouTube APIポーリング、コマンドパース
├── obs_controller.py # OBS WebSocket制御
├── requirements.txt  # 依存パッケージ
├── start.sh          # 起動スクリプト（Linux/Mac）
├── start.bat         # 起動スクリプト（Windows）
├── README.md         # このファイル
└── users.db          # ユーザーデータ（自動生成）
```

---

## コマンド仕様

| コマンド | 書式 | 例 |
|----------|------|----|
| 単勝 | `!単勝 [馬番] [金額]` | `!単勝 3 500` |
| 馬連 | `!馬連 [馬番] [馬番] [金額]` | `!馬連 2 5 1000` |
| 残高確認 | `!残高` | `!残高` |

- 初回コメント時に自動登録、残高10,000円を付与
- 残高不足の場合は馬券購入不可
- 締め切り後のコマンドは無視

---

## オッズ計算方式（パリミュチュエル）

```
単勝オッズ[馬番] = 全単勝売上 × 0.80 ÷ その馬への単勝売上
馬連オッズ[組] = 全馬連売上 × 0.75 ÷ その組への馬連売上
```

- 馬券が売れるたびにリアルタイムで再計算
- 誰も購入していない馬・組み合わせはオッズ非表示

---

## トラブルシューティング

**日本語が文字化けする / 表示されない**
- 日本語フォントをインストールして `GAME_FONT_PATH` に設定してください
- Linux: `sudo apt install fonts-noto-cjk`

**YouTube APIエラーが出る**
- `YOUTUBE_API_KEY` が正しく設定されているか確認
- Google Cloud Consoleで YouTube Data API v3 が有効化されているか確認
- ライブ配信が実際に開始されているか確認

**OBSに接続できない**
- OBS が起動しているか確認
- obs-websocket プラグインが有効か確認
- `OBS_PASSWORD` が正しいか確認
- `--no-obs` フラグで OBS 制御を無効化して起動

**画面が表示されない（Linux）**
- ディスプレイサーバーが動作しているか確認
- `DISPLAY` 環境変数が設定されているか確認: `export DISPLAY=:0`

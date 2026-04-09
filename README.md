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

```bat
start.bat                       # デフォルト設定
start.bat abc123XYZ 5           # video_id と5レース指定
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

**GUIで設定する場合:**
1. 「タスクスケジューラ」を開く
2. 「基本タスクの作成」をクリック
3. 名前: `競馬ゲーム`
4. トリガー: 「毎日」→ 時刻を設定
5. 操作: 「プログラムの開始」→ `C:\path\to\gamekeiba\start.bat`

**コマンドラインで登録する場合:**

```bat
REM 毎日19時に実行
schtasks /create /tn "競馬ゲーム" /tr "C:\path\to\gamekeiba\start.bat" /sc daily /st 19:00

REM タスクの確認
schtasks /query /tn "競馬ゲーム"

REM タスクの削除
schtasks /delete /tn "競馬ゲーム" /f
```

---

## OBS WebSocket の設定

1. OBS Studio を起動
2. 「ツール」→「obs-websocket 設定」を開く
3. 「WebSocketサーバーを有効にする」をチェック
4. ポート: `4455`（デフォルト）
5. パスワードを設定し、`OBS_PASSWORD` 環境変数に設定

---

## 毎日19時 自動配信の完全自動化

`auto_start.bat` を使うと、YouTube配信枠の作成からゲーム起動まで全自動で実行できます。

### 自動化の流れ

```
タスクスケジューラ（18:55）
    ↓
auto_start.bat
    ↓
create_broadcast.py  ← OAuth2認証でYouTube配信枠を自動作成（限定公開）
    ↓  VIDEO_ID取得
main.py VIDEO_ID --races 20  ← ゲーム起動（20レース固定）
    ↓
20レース終了後に自動終了・配信停止
```

---

## OAuth2 の設定手順

`create_broadcast.py` を使用するには、Google Cloud Console で OAuth2 クライアント ID を作成する必要があります。

### 1. Google Cloud Console で OAuth2 クライアント ID を作成

1. [Google Cloud Console](https://console.cloud.google.com/) にアクセス
2. 既存のプロジェクトを選択（または新規プロジェクトを作成）
3. 左メニュー「**APIとサービス**」→「**ライブラリ**」を開く
4. 「**YouTube Data API v3**」を検索して**有効化**
5. 左メニュー「**APIとサービス**」→「**認証情報**」を開く
6. 上部の「**＋認証情報を作成**」→「**OAuth クライアント ID**」をクリック
7. 「アプリケーションの種類」→「**デスクトップアプリ**」を選択
8. 名前を入力（例: `競馬ゲーム`）して「**作成**」をクリック

> **注意:** 初回は「OAuth 同意画面」の設定が必要です。  
> 「外部」を選択し、アプリ名・メールアドレスを入力して保存してください。  
> テスト用途であれば「テストユーザー」に自分のGoogleアカウントを追加するだけでOKです。

### 2. client_secret.json のダウンロード

1. 「認証情報」ページで作成したOAuthクライアントIDの右側にある **↓（ダウンロード）** アイコンをクリック
2. JSONファイルがダウンロードされます
3. ファイル名を `client_secret.json` に変更
4. `gamekeiba` フォルダ（`auto_start.bat` と同じ場所）に配置

```
gamekeiba/
├── client_secret.json  ← ここに配置
├── auto_start.bat
├── create_broadcast.py
└── ...
```

### 3. 初回認証の実行

仮想環境を有効化してから `create_broadcast.py` を実行します。

```bat
REM Windowsの場合
cd C:\path\to\gamekeiba
.venv\Scripts\activate
pip install google-auth-oauthlib
python create_broadcast.py
```

初回実行時にブラウザが自動で開き、Googleアカウントでの認証を求められます。  
許可すると認証が完了し、`token.json` が自動生成されます。

成功すると標準出力に `VIDEO_ID`（例: `abc123XYZ`）が出力されます。

### 4. token.json の場所と役割

| 項目 | 内容 |
|------|------|
| **場所** | `gamekeiba/token.json`（自動生成） |
| **役割** | OAuth2 アクセストークンとリフレッシュトークンを保存 |
| **2回目以降** | token.json を自動読み込みし、ブラウザ認証なしで実行 |
| **期限切れ時** | リフレッシュトークンで自動更新（手動操作不要） |
| **注意** | token.json はアカウントへのアクセス権を含むため、`.gitignore` に追加して管理してください |

```bash
# .gitignore に追加推奨
echo "token.json" >> .gitignore
echo "client_secret.json" >> .gitignore
```

---

## Windowsタスクスケジューラの設定手順

`auto_start.bat` を毎日18:55に自動実行する設定です。

### GUI での設定手順

1. Windowsキー → 「**タスクスケジューラ**」を検索して開く
2. 右側パネルの「**タスクの作成**」をクリック（※「基本タスクの作成」ではなく「タスクの作成」を選ぶこと）
3. **全般タブ**
   - 名前: `競馬LIVE自動配信`
   - 「**最上位の特権で実行する**」にチェック ← 管理者権限
   - 構成: `Windows 10`
4. **トリガータブ** →「新規」をクリック
   - 開始: `毎日`
   - 時刻: `18:55:00`
   - 「有効」にチェック
5. **操作タブ** →「新規」をクリック
   - 操作: `プログラムの開始`
   - プログラム/スクリプト: `C:\path\to\gamekeiba\auto_start.bat`
   - 作業フォルダー: `C:\path\to\gamekeiba`
6. **条件タブ**
   - 「**タスクを実行するためにスリープを解除する**」にチェック ← スリープ解除
   - 「AC電源で実行している場合のみタスクを開始する」のチェックを**外す**（ノートPC使用時）
7. **設定タブ**
   - 「タスクが既に実行中の場合に適用されるルール」→「新しいインスタンスを実行しない」
8. 「OK」をクリックして保存

### コマンドラインでの設定（管理者権限のコマンドプロンプト）

```bat
REM タスクを作成（毎日18:55実行、最上位権限、スリープ解除）
schtasks /create ^
  /tn "競馬LIVE自動配信" ^
  /tr "C:\path\to\gamekeiba\auto_start.bat" ^
  /sc daily ^
  /st 18:55 ^
  /rl highest ^
  /f

REM ※スリープ解除はGUIで追加設定が必要です（コマンドラインでは設定不可）

REM タスクの確認
schtasks /query /tn "競馬LIVE自動配信" /fo list /v

REM タスクの削除
schtasks /delete /tn "競馬LIVE自動配信" /f
```

### スリープ解除をコマンドラインで設定する方法

```bat
REM PowerShellでスリープ解除フラグを有効化（管理者で実行）
powershell -Command ^
  "$task = Get-ScheduledTask -TaskName '競馬LIVE自動配信'; ^
   $task.Settings.WakeToRun = $true; ^
   Set-ScheduledTask -InputObject $task"
```

### 設定確認

```bat
REM 手動でタスクをテスト実行
schtasks /run /tn "競馬LIVE自動配信"

REM 実行履歴を確認（タスクスケジューラのGUIで「履歴」タブ）
```

> **BIOS設定について**  
> スリープからの自動起動には、BIOS/UEFIで「Wake on RTC」または「RTC Alarm」が有効になっている必要があります。  
> BIOS設定はメーカーによって異なるため、PCのマニュアルを参照してください。

---

## ファイル構成

```
gamekeiba/
├── main.py              # エントリーポイント、引数処理
├── game.py              # ゲームループ、フェーズ管理、Pygame描画
├── horse.py             # 馬クラス、アニメーション描画
├── betting.py           # 馬券管理、パリミュチュエルオッズ計算
├── user_manager.py      # ユーザー管理（SQLite）
├── youtube_client.py    # YouTube APIポーリング、コマンドパース
├── obs_controller.py    # OBS WebSocket制御
├── create_broadcast.py  # YouTube配信枠の自動作成（OAuth2）
├── auto_start.bat       # 全自動配信スクリプト（Windows）
├── start.bat            # 手動起動スクリプト（Windows）
├── start.sh             # 起動スクリプト（Linux/Mac）
├── requirements.txt     # 依存パッケージ
├── client_secret.json   # OAuth2クライアント情報（要配置・gitignore推奨）
├── token.json           # 認証トークン（自動生成・gitignore推奨）
├── README.md            # このファイル
└── users.db             # ユーザーデータ（自動生成）
```

---

## コマンド仕様

| コマンド | 書式 | 例 |
|----------|------|----|
| 単勝 | `!単勝 [馬番] [金額]` | `!単勝 3 500` |
| 複勝 | `!複勝 [馬番] [金額]` | `!複勝 3 500` |
| 残高確認 | `!残高` | `!残高` |

- 初回コメント時に自動登録、残高10,000円を付与
- 残高不足の場合は馬券購入不可
- 締め切り後のコマンドは無視
- **複勝**は指定した馬が1〜3着に入れば的中

---

## オッズ計算方式（パリミュチュエル）

```
単勝オッズ[馬番] = 全単勝売上 × 0.80 ÷ その馬への単勝売上
複勝オッズ[馬番] = 全複勝売上 × 0.75 ÷ その馬への複勝売上
```

- 馬券が売れるたびにリアルタイムで再計算
- 誰も購入していない馬はオッズ非表示

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

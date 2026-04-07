@echo off
REM ============================================================
REM auto_start.bat - YouTube LIVE 競馬ゲーム 全自動起動
REM
REM このスクリプトは以下を自動で行います:
REM   1. YouTube 配信枠を作成 (create_broadcast.py)
REM   2. 作成した配信枠の video_id で即座にゲーム起動
REM   3. OBS に RTMP 設定を自動反映して配信開始
REM
REM 設定箇所:
REM   YOUTUBE_API_KEY : YouTube Data API v3 キー
REM   OBS_PASSWORD    : OBS WebSocket パスワード（なければ空欄）
REM   RACES           : レース数（デフォルト 10）
REM   START_TIME      : 配信開始時刻 ISO8601（省略時＝今から1分後）
REM ============================================================

REM ── ユーザー設定 ─────────────────────────────────────────────
set YOUTUBE_API_KEY=YOUR_YOUTUBE_API_KEY_HERE
set OBS_PASSWORD=
set GAME_FONT_PATH=
set RACES=10
set START_TIME=

REM ── スクリプトフォルダへ移動 ─────────────────────────────────
cd /d "%~dp0"

REM ── 日本語フォント自動検索 ───────────────────────────────────
if exist "C:\Windows\Fonts\meiryo.ttc"  set GAME_FONT_PATH=C:\Windows\Fonts\meiryo.ttc   & goto :font_ok
if exist "C:\Windows\Fonts\msgothic.ttc" set GAME_FONT_PATH=C:\Windows\Fonts\msgothic.ttc & goto :font_ok
if exist "C:\Windows\Fonts\YuGothM.ttc" set GAME_FONT_PATH=C:\Windows\Fonts\YuGothM.ttc  & goto :font_ok
:font_ok
if not "%GAME_FONT_PATH%"=="" echo [INFO] フォント: %GAME_FONT_PATH%

REM ── 仮想環境のセットアップ ───────────────────────────────────
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else (
    echo [INFO] 仮想環境を作成します...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install --upgrade pip -q
    pip install -r requirements.txt -q
)

REM ── API キーチェック ─────────────────────────────────────────
if "%YOUTUBE_API_KEY%"=="YOUR_YOUTUBE_API_KEY_HERE" (
    echo [ERROR] YOUTUBE_API_KEY を設定してください。
    echo         このファイルをメモ帳で開いて set YOUTUBE_API_KEY= の行を編集してください。
    pause & exit /b 1
)

echo ========================================
echo  YouTube LIVE 競馬ゲーム 全自動起動
echo  配信枠を作成中...
echo ========================================

REM ── 配信枠作成 ───────────────────────────────────────────────
REM START_TIME が空なら create_broadcast.py が自動設定（今から1分後）
if "%START_TIME%"=="" (
    for /f "delims=" %%i in ('python create_broadcast.py 2^>nul') do set VIDEO_ID=%%i
) else (
    for /f "delims=" %%i in ('python create_broadcast.py --start "%START_TIME%" 2^>nul') do set VIDEO_ID=%%i
)

if "%VIDEO_ID%"=="" (
    echo [ERROR] 配信枠の作成に失敗しました。
    echo         client_secret.json / token.json を確認してください。
    pause & exit /b 1
)

echo [INFO] 配信枠作成完了: video_id = %VIDEO_ID%
echo [INFO] https://youtu.be/%VIDEO_ID%

REM ── ゲーム起動（OBS は main.py が stream_settings.txt を読んで自動設定）─
echo ========================================
echo  ゲームを起動します...
echo  video_id : %VIDEO_ID%
echo  races    : %RACES%
echo ========================================

python main.py %VIDEO_ID% --races %RACES%

echo ========================================
echo  終了しました
echo ========================================
pause

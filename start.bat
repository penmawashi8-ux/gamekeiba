@echo off
REM ============================================================
REM YouTube LIVE 競馬ゲーム 起動スクリプト（Windows用）
REM ============================================================
REM 使用前に以下を設定してください:
REM   1. YOUTUBE_API_KEY を設定
REM   2. VIDEO_ID を設定（またはコマンドライン引数で渡す）
REM   3. OBS_PASSWORD を設定（OBSのWebSocketパスワード）
REM
REM タスクスケジューラ登録コマンド（毎日19時に実行）:
REM   schtasks /create /tn "競馬ゲーム" /tr "C:\path\to\start.bat" /sc daily /st 19:00
REM ============================================================

REM ── 設定項目 ──────────────────────────────────────────────
set YOUTUBE_API_KEY=YOUR_YOUTUBE_API_KEY_HERE
set OBS_PASSWORD=
set GAME_FONT_PATH=

REM 引数からvideo_idとレース数を受け取る
set VIDEO_ID=%1
set RACES=%2
if "%VIDEO_ID%"=="" set VIDEO_ID=YOUR_VIDEO_ID_HERE
if "%RACES%"=="" set RACES=10

REM スクリプトのディレクトリに移動
cd /d "%~dp0"

REM ── 日本語フォント自動検索 ────────────────────────────────
if exist "C:\Windows\Fonts\meiryo.ttc" (
    set GAME_FONT_PATH=C:\Windows\Fonts\meiryo.ttc
    goto :font_found
)
if exist "C:\Windows\Fonts\msgothic.ttc" (
    set GAME_FONT_PATH=C:\Windows\Fonts\msgothic.ttc
    goto :font_found
)
if exist "C:\Windows\Fonts\YuGothM.ttc" (
    set GAME_FONT_PATH=C:\Windows\Fonts\YuGothM.ttc
    goto :font_found
)
:font_found
if not "%GAME_FONT_PATH%"=="" (
    echo [INFO] 日本語フォント: %GAME_FONT_PATH%
)

REM ── 仮想環境の確認・作成 ──────────────────────────────────
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else (
    echo [INFO] 仮想環境を作成します...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install --upgrade pip
    pip install -r requirements.txt
)

REM ── ゲーム起動 ────────────────────────────────────────────
echo ========================================
echo  YouTube LIVE 競馬ゲーム
echo  video_id : %VIDEO_ID%
echo  races    : %RACES%
echo ========================================

if "%VIDEO_ID%"=="YOUR_VIDEO_ID_HERE" (
    echo [INFO] VIDEO_ID が未設定です。テストモードで起動します。
    python main.py --test --races %RACES%
) else (
    python main.py %VIDEO_ID% --races %RACES%
)

echo ========================================
echo  終了しました
echo ========================================
pause

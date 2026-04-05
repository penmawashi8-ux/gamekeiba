@echo off
REM ============================================================
REM YouTube LIVE 競馬ゲーム 起動スクリプト（Windows用）
REM ============================================================
REM 使い方:
REM   start.bat <VIDEO_ID> [レース数]
REM   例) start.bat abc123XYZ 10
REM
REM 事前に以下の環境変数を Windows のシステム環境変数に設定してください:
REM   YOUTUBE_API_KEY  ... YouTube Data API v3 のAPIキー（必須）
REM   OBS_PASSWORD     ... OBS WebSocket パスワード（任意）
REM
REM タスクスケジューラ登録例（毎日19時に VIDEO_ID abc123XYZ で10レース実行）:
REM   schtasks /create /tn "競馬ゲーム" ^
REM     /tr "\"C:\path\to\gamekeiba\start.bat\" abc123XYZ 10" ^
REM     /sc daily /st 19:00 /ru SYSTEM
REM ============================================================

REM ── 引数からvideo_idとレース数を受け取る ──────────────────
set VIDEO_ID=%1
set RACES=%2
if "%RACES%"=="" set RACES=10

REM ── YOUTUBE_API_KEY の確認（環境変数から読み込む） ────────
if "%YOUTUBE_API_KEY%"=="" (
    echo [ERROR] 環境変数 YOUTUBE_API_KEY が設定されていません。
    echo         Windowsのシステム環境変数に設定してから再実行してください。
    pause
    exit /b 1
)

REM ── スクリプトのディレクトリに移動 ───────────────────────
cd /d "%~dp0"

REM ── 日本語フォント自動検索 ────────────────────────────────
set GAME_FONT_PATH=
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
    py -3.12 -m venv .venv
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

if "%VIDEO_ID%"=="" (
    echo [INFO] VIDEO_ID が未指定です。テストモードで起動します。
    py -3.12 main.py --test --races %RACES% --no-obs
) else (
    py -3.12 main.py %VIDEO_ID% --races %RACES% --no-obs
)

echo ========================================
echo  終了しました
echo ========================================
pause

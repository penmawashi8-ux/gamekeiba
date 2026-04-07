@echo off
REM ============================================================
REM auto_start_vertical.bat - YouTube LIVE 競馬ゲーム 縦型全自動起動
REM
REM 縦型配信（720×1280 = スマホ縦向き・YouTube Shorts LIVE）用
REM OBS は 1080×1920 キャンバスで設定してください（下記参照）
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
if exist "C:\Windows\Fonts\meiryo.ttc"   set GAME_FONT_PATH=C:\Windows\Fonts\meiryo.ttc   & goto :font_ok
if exist "C:\Windows\Fonts\msgothic.ttc" set GAME_FONT_PATH=C:\Windows\Fonts\msgothic.ttc & goto :font_ok
if exist "C:\Windows\Fonts\YuGothM.ttc"  set GAME_FONT_PATH=C:\Windows\Fonts\YuGothM.ttc  & goto :font_ok
:font_ok

REM ── 仮想環境のセットアップ ───────────────────────────────────
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else (
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install --upgrade pip -q
    pip install -r requirements.txt -q
)

if "%YOUTUBE_API_KEY%"=="YOUR_YOUTUBE_API_KEY_HERE" (
    echo [ERROR] YOUTUBE_API_KEY を設定してください。
    pause & exit /b 1
)

echo ========================================
echo  YouTube LIVE 競馬ゲーム 縦型全自動起動
echo  配信枠を作成中...
echo ========================================

if "%START_TIME%"=="" (
    for /f "delims=" %%i in ('python create_broadcast.py 2^>nul') do set VIDEO_ID=%%i
) else (
    for /f "delims=" %%i in ('python create_broadcast.py --start "%START_TIME%" 2^>nul') do set VIDEO_ID=%%i
)

if "%VIDEO_ID%"=="" (
    echo [ERROR] 配信枠の作成に失敗しました。
    pause & exit /b 1
)

echo [INFO] 配信枠作成完了: https://youtu.be/%VIDEO_ID%

echo ========================================
echo  縦型モードでゲームを起動します...
echo ========================================

python main.py %VIDEO_ID% --races %RACES% --vertical

pause

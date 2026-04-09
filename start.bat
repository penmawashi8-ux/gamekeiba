@echo off
REM ============================================================
REM start.bat - YouTube LIVE Keiba Game (Windows)
REM ============================================================
REM Setup before use:
REM   1. Set YOUTUBE_API_KEY
REM   2. Set VIDEO_ID (or pass as argument)
REM   3. Set OBS_PASSWORD (if using OBS WebSocket)
REM
REM Task Scheduler example (run at 19:00 daily):
REM   schtasks /create /tn "Keiba" /tr "C:\path\to\start.bat" /sc daily /st 19:00
REM ============================================================

REM --- Settings ---
set YOUTUBE_API_KEY=YOUR_YOUTUBE_API_KEY_HERE
set OBS_PASSWORD=
set GAME_FONT_PATH=

REM Accept video_id and race count from arguments
set VIDEO_ID=%1
set RACES=%2
if "%VIDEO_ID%"=="" set VIDEO_ID=YOUR_VIDEO_ID_HERE
if "%RACES%"=="" set RACES=10

REM Move to script directory
cd /d "%~dp0"

REM --- Auto-detect Japanese font ---
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
    echo [INFO] Font: %GAME_FONT_PATH%
)

REM --- Setup venv ---
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else (
    echo [INFO] Creating venv...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install --upgrade pip
    pip install -r requirements.txt
)

REM --- Launch game ---
echo ========================================
echo  YouTube LIVE Keiba Game
echo  video_id : %VIDEO_ID%
echo  races    : %RACES%
echo ========================================

if "%VIDEO_ID%"=="YOUR_VIDEO_ID_HERE" (
    echo [INFO] VIDEO_ID not set. Starting in test mode.
    python main.py --test --races %RACES%
) else (
    python main.py %VIDEO_ID% --races %RACES%
)

echo ========================================
echo  Done.
echo ========================================
pause

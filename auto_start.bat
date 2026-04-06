@echo off
REM ============================================================
REM auto_start.bat - Virtual Keiba LIVE auto broadcast
REM ============================================================
REM Usage:
REM   Run manually by double-clicking, or via Task Scheduler at 18:55.
REM
REM Steps:
REM   1. create_broadcast.py creates a YouTube broadcast (unlisted)
REM   2. Launch game with the VIDEO_ID for 20 races
REM   3. Auto-stop after 20 races
REM
REM Requirements:
REM   - Set YOUTUBE_API_KEY below
REM   - Place client_secret.json in this folder
REM   See README.md for details.
REM ============================================================

REM --- Settings (edit here) ---
set YOUTUBE_API_KEY=YOUR_YOUTUBE_API_KEY_HERE
set OBS_PASSWORD=
set GAME_FONT_PATH=

REM Move to script directory
cd /d "%~dp0"

echo ========================================
echo  Virtual Keiba LIVE - Auto Broadcast
echo  %date% %time%
echo ========================================

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

REM --- Setup venv (Python 3.12) ---
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else (
    echo [INFO] Creating venv with Python 3.12...
    py -3.12 -m venv .venv
    call .venv\Scripts\activate.bat
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    python -m pip install google-auth-oauthlib
)

REM Install google-auth-oauthlib if missing
python -m pip show google-auth-oauthlib >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing google-auth-oauthlib...
    python -m pip install google-auth-oauthlib
)

REM --- Create YouTube broadcast ---
echo [INFO] Creating YouTube broadcast...
for /f "usebackq delims=" %%i in (`python create_broadcast.py 2^>con`) do set VIDEO_ID=%%i

if "%VIDEO_ID%"=="" (
    echo.
    echo [WARN] Broadcast creation failed. Starting in test mode.
    echo        To run live, check:
    echo          1. client_secret.json exists in this folder
    echo          2. Internet connection is available
    echo          3. Run "python create_broadcast.py" manually for details
    echo.
    python main.py --test --races 20
    goto :end
)

echo [INFO] VIDEO_ID: %VIDEO_ID%

REM --- Launch game (20 races) ---
echo.
echo ========================================
echo  Starting broadcast
echo  VIDEO_ID : %VIDEO_ID%
echo  Races    : 20
echo ========================================
echo.

python main.py %VIDEO_ID% --races 20

:end
echo.
echo ========================================
echo  Broadcast ended. (%date% %time%)
echo ========================================
pause

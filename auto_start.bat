@echo off
REM ============================================================
REM auto_start.bat - YouTube LIVE Keiba Game Auto Launcher
REM
REM Edit this file with Notepad before use:
REM   YOUTUBE_API_KEY : Your YouTube Data API v3 key (required)
REM   OBS_PASSWORD    : OBS WebSocket password (leave blank if none)
REM   RACES           : Number of races (default: 10)
REM   START_TIME      : Leave blank = start in 1 minute (for testing)
REM                     Set value  = e.g. 2026-04-10T21:00:00+09:00
REM ============================================================

REM --- User Settings ---
set YOUTUBE_API_KEY=YOUR_YOUTUBE_API_KEY_HERE
set OBS_PASSWORD=
set GAME_FONT_PATH=
set RACES=10
set START_TIME=

REM --- Move to script folder ---
cd /d "%~dp0"
echo [INFO] Working folder: %CD%

REM --- Check Python ---
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python and add to PATH.
    echo         https://www.python.org/downloads/
    goto :error
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo [INFO] %%v

REM --- Auto-detect Japanese font ---
if exist "C:\Windows\Fonts\meiryo.ttc"   set GAME_FONT_PATH=C:\Windows\Fonts\meiryo.ttc
if exist "C:\Windows\Fonts\msgothic.ttc" set GAME_FONT_PATH=C:\Windows\Fonts\msgothic.ttc
if exist "C:\Windows\Fonts\YuGothM.ttc"  set GAME_FONT_PATH=C:\Windows\Fonts\YuGothM.ttc
if not "%GAME_FONT_PATH%"=="" echo [INFO] Font: %GAME_FONT_PATH%

REM --- Setup venv ---
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    echo [INFO] venv loaded
) else (
    echo [INFO] Creating venv (first time only, may take a while)...
    python -m venv .venv
    if errorlevel 1 ( echo [ERROR] Failed to create venv. & goto :error )
    call .venv\Scripts\activate.bat
    pip install --upgrade pip -q
    pip install -r requirements.txt
    if errorlevel 1 ( echo [ERROR] Failed to install packages. & goto :error )
)

REM --- Check API key ---
if "%YOUTUBE_API_KEY%"=="YOUR_YOUTUBE_API_KEY_HERE" (
    echo.
    echo [ERROR] YOUTUBE_API_KEY is not set.
    echo         Open this file with Notepad and replace YOUR_YOUTUBE_API_KEY_HERE
    echo         with your actual YouTube Data API v3 key.
    goto :error
)

REM --- Determine start time (blank = now+1min) ---
if "%START_TIME%"=="" (
    python -c "from datetime import datetime,timedelta,timezone; t=datetime.now(timezone(timedelta(hours=9)))+timedelta(minutes=1); open('_tmp_st.txt','w').write(t.strftime('%%Y-%%m-%%dT%%H:%%M:%%S+09:00'))"
    if errorlevel 1 ( echo [ERROR] Failed to calculate start time. & goto :error )
    set /p START_TIME=<_tmp_st.txt
    del _tmp_st.txt 2>nul
)
echo [INFO] Start time: %START_TIME%

echo.
echo ========================================
echo  Creating YouTube broadcast...
echo ========================================

REM --- Create broadcast (errors shown as-is) ---
for /f "delims=" %%i in ('python create_broadcast.py --start "%START_TIME%"') do set VIDEO_ID=%%i

if "%VIDEO_ID%"=="" (
    echo.
    echo [ERROR] Failed to create broadcast.
    echo         Check the error above.
    echo         - Make sure client_secret.json exists
    echo         - Delete token.json and re-authenticate if expired
    goto :error
)

echo [INFO] Broadcast created!
echo [INFO] video_id : %VIDEO_ID%
echo [INFO] URL      : https://youtu.be/%VIDEO_ID%
echo.

REM --- Launch game ---
echo ========================================
echo  Launching game...
echo  video_id : %VIDEO_ID%
echo  races    : %RACES%
echo ========================================
echo.

python main.py %VIDEO_ID% --races %RACES%

echo.
echo ========================================
echo  Done.
echo ========================================
pause
exit /b 0

:error
echo.
echo ----------------------------------------
echo  Exited with error. See message above.
echo ----------------------------------------
pause
exit /b 1

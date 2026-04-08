@echo off
REM ============================================================
REM auto_start.bat - YouTube LIVE Keiba Game Auto Launcher
REM
REM [Required] Set YOUTUBE_API_KEY below before running.
REM
REM [OBS auto-start setup]
REM   To have OBS start streaming automatically:
REM   1. In OBS: Tools -> WebSocket Server Settings
REM      -> Enable WebSocket server (check the box)
REM      -> Set a password (optional but recommended)
REM   2. Set OBS_PASSWORD below to match (leave blank if no password)
REM   Without this, you must start the OBS stream manually.
REM
REM [Python version]
REM   pygame requires Python 3.9-3.12.
REM   If you have Python 3.14, install 3.12 from:
REM     https://www.python.org/downloads/release/python-3128/
REM   Then change the PYTHON line below to:
REM     set PYTHON=py -3.12
REM ============================================================

REM --- User Settings ---
set YOUTUBE_API_KEY=YOUR_YOUTUBE_API_KEY_HERE
set OBS_PASSWORD=
set GAME_FONT_PATH=
set RACES=10
set START_TIME=

REM --- Python executable (change to "py -3.12" if needed) ---
set PYTHON=python

REM --- Move to script folder ---
cd /d "%~dp0"
echo [INFO] Working folder: %CD%

REM --- Check Python ---
%PYTHON% --version
if errorlevel 1 (
    echo [ERROR] Python not found.
    echo   Install Python 3.12 from https://www.python.org/downloads/release/python-3128/
    goto :error
)

REM --- Warn if Python 3.13+ (pygame may not have wheels) ---
%PYTHON% -c "import sys; exit(0 if sys.version_info < (3,13) else 1)" >nul 2>&1
if errorlevel 1 (
    echo.
    echo [WARN] Python 3.13 or newer detected.
    echo   pygame may not install correctly on this version.
    echo   If install fails, install Python 3.12 and set:
    echo     set PYTHON=py -3.12
    echo   in this file, then re-run.
    echo.
)

REM --- Auto-detect Japanese font ---
if exist "C:\Windows\Fonts\meiryo.ttc"   set GAME_FONT_PATH=C:\Windows\Fonts\meiryo.ttc
if exist "C:\Windows\Fonts\msgothic.ttc" set GAME_FONT_PATH=C:\Windows\Fonts\msgothic.ttc
if exist "C:\Windows\Fonts\YuGothM.ttc"  set GAME_FONT_PATH=C:\Windows\Fonts\YuGothM.ttc
echo [INFO] Font: %GAME_FONT_PATH%

REM --- Install requirements ---
echo [INFO] Checking packages...
%PYTHON% -m pip install -r requirements.txt -q
if errorlevel 1 (
    echo.
    echo [ERROR] pip install failed.
    echo   If the error mentions pygame, install Python 3.12 and set:
    echo     set PYTHON=py -3.12
    echo   in this file, then re-run.
    goto :error
)
echo [INFO] Packages OK

REM --- Check API key ---
if "%YOUTUBE_API_KEY%"=="YOUR_YOUTUBE_API_KEY_HERE" (
    echo [ERROR] Set YOUTUBE_API_KEY in this file before running.
    goto :error
)

REM --- Determine start time ---
if "%START_TIME%"=="" (
    %PYTHON% calc_start_time.py
    if errorlevel 1 ( echo [ERROR] Time calc failed. & goto :error )
    set /p START_TIME=<_tmp_st.txt
    del _tmp_st.txt 2>nul
)
echo [INFO] Start time: %START_TIME%

echo.
echo ========================================
echo  Creating YouTube broadcast...
echo ========================================

for /f "delims=" %%i in ('%PYTHON% create_broadcast.py --start "%START_TIME%"') do set VIDEO_ID=%%i

if "%VIDEO_ID%"=="" (
    echo [ERROR] Broadcast creation failed.
    echo   - Check client_secret.json exists
    echo   - Delete token.json and re-run to re-authenticate
    goto :error
)

echo [INFO] video_id: %VIDEO_ID%
echo [INFO] URL: https://youtu.be/%VIDEO_ID%
echo.

%PYTHON% main.py %VIDEO_ID% --races %RACES%

echo.
echo Done.
pause
exit /b 0

:error
echo.
echo ----------------------------------------
echo  ERROR - see message above
echo ----------------------------------------
pause
exit /b 1

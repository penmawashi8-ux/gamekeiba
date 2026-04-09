@echo off
REM ============================================================
REM auto_start_vertical.bat - YouTube LIVE Keiba (Vertical Mode)
REM
REM Credentials are loaded from config.local.bat (not in git).
REM Copy config.local.example.bat to config.local.bat and fill in.
REM ============================================================

REM --- Defaults (overridden by config.local.bat) ---
set YOUTUBE_API_KEY=YOUR_YOUTUBE_API_KEY_HERE
set OBS_PASSWORD=
set GAME_FONT_PATH=
set RACES=10
set PYTHON=python

REM --- Move to script folder first so config.local.bat path is correct ---
cd /d "%~dp0"

REM --- Load local config ---
if exist "config.local.bat" (
    call "config.local.bat"
    echo [INFO] Loaded config.local.bat
) else (
    echo [WARN] config.local.bat not found.
    echo   Copy config.local.example.bat to config.local.bat and fill in your settings.
    echo.
)

echo [INFO] Working folder: %CD%

REM --- Check Python ---
%PYTHON% --version
if errorlevel 1 (
    echo [ERROR] Python not found.
    echo   Install Python 3.12 from https://www.python.org/downloads/release/python-3128/
    goto :error
)

REM --- Warn if Python 3.13+ ---
%PYTHON% -c "import sys; exit(0 if sys.version_info < (3,13) else 1)" >nul 2>&1
if errorlevel 1 (
    echo.
    echo [WARN] Python 3.13+ detected. pygame may not install correctly.
    echo   If install fails, set PYTHON=py -3.12 in config.local.bat
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
    echo [ERROR] pip install failed. Set PYTHON=py -3.12 in config.local.bat if needed.
    goto :error
)
echo [INFO] Packages OK

REM --- Check API key ---
if "%YOUTUBE_API_KEY%"=="YOUR_YOUTUBE_API_KEY_HERE" (
    echo [ERROR] Set YOUTUBE_API_KEY in config.local.bat
    goto :error
)

echo.
echo ========================================
echo  Creating YouTube broadcast (vertical/instant)...
echo ========================================

for /f "delims=" %%i in ('%PYTHON% create_broadcast.py --instant') do set VIDEO_ID=%%i

if "%VIDEO_ID%"=="" (
    echo [ERROR] Broadcast creation failed.
    echo   - Check client_secret.json exists
    echo   - Delete token.json and re-run to re-authenticate
    goto :error
)

echo [INFO] video_id: %VIDEO_ID%
echo [INFO] URL: https://youtu.be/%VIDEO_ID%
echo.

%PYTHON% main.py %VIDEO_ID% --races %RACES% --vertical

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

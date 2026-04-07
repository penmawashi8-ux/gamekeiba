@echo off
REM ============================================================
REM auto_start.bat - YouTube LIVE Keiba Game Auto Launcher
REM Edit YOUTUBE_API_KEY before running.
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
python --version
if errorlevel 1 (
    echo [ERROR] Python not found. Install from https://www.python.org/
    goto :error
)

REM --- Auto-detect Japanese font ---
if exist "C:\Windows\Fonts\meiryo.ttc"   set GAME_FONT_PATH=C:\Windows\Fonts\meiryo.ttc
if exist "C:\Windows\Fonts\msgothic.ttc" set GAME_FONT_PATH=C:\Windows\Fonts\msgothic.ttc
if exist "C:\Windows\Fonts\YuGothM.ttc"  set GAME_FONT_PATH=C:\Windows\Fonts\YuGothM.ttc
echo [INFO] Font: %GAME_FONT_PATH%

REM --- Install requirements ---
echo [INFO] Checking packages...
python -m pip install -r requirements.txt -q
if errorlevel 1 (
    echo [ERROR] pip install failed.
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
    python calc_start_time.py
    if errorlevel 1 ( echo [ERROR] Time calc failed. & goto :error )
    set /p START_TIME=<_tmp_st.txt
    del _tmp_st.txt 2>nul
)
echo [INFO] Start time: %START_TIME%

echo.
echo ========================================
echo  Creating YouTube broadcast...
echo ========================================

for /f "delims=" %%i in ('python create_broadcast.py --start "%START_TIME%"') do set VIDEO_ID=%%i

if "%VIDEO_ID%"=="" (
    echo [ERROR] Broadcast creation failed.
    echo   - Check client_secret.json exists
    echo   - Delete token.json and re-run to re-authenticate
    goto :error
)

echo [INFO] video_id: %VIDEO_ID%
echo [INFO] URL: https://youtu.be/%VIDEO_ID%
echo.

python main.py %VIDEO_ID% --races %RACES%

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

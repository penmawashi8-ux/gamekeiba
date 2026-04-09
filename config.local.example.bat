REM ============================================================
REM config.local.example.bat
REM
REM Copy this file to config.local.bat and fill in your values.
REM config.local.bat is NOT committed to git (your credentials stay local).
REM ============================================================

REM YouTube Data API v3 key (required)
set YOUTUBE_API_KEY=YOUR_YOUTUBE_API_KEY_HERE

REM OBS WebSocket password (leave blank if none)
REM Enable in OBS: Tools -> WebSocket Server Settings -> Enable
set OBS_PASSWORD=

REM Python executable (change to "py -3.12" if you have Python 3.14+)
set PYTHON=python

REM Number of races per session (default: 10)
set RACES=10

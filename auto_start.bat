@echo off
chcp 65001 >nul 2>&1
REM ============================================================
REM auto_start.bat - YouTube LIVE 競馬ゲーム 全自動起動
REM
REM 設定箇所（このファイルをメモ帳で開いて編集）:
REM   YOUTUBE_API_KEY : YouTube Data API v3 キー（必須）
REM   OBS_PASSWORD    : OBS WebSocket パスワード（なければ空欄）
REM   RACES           : レース数（デフォルト 10）
REM   START_TIME      : 空欄のまま = 今から1分後で即起動
REM                     指定する場合: 2026-04-10T21:00:00+09:00
REM ============================================================

REM ── ユーザー設定 ─────────────────────────────────────────────
set YOUTUBE_API_KEY=YOUR_YOUTUBE_API_KEY_HERE
set OBS_PASSWORD=
set GAME_FONT_PATH=
set RACES=10
set START_TIME=

REM ── スクリプトフォルダへ移動 ─────────────────────────────────
cd /d "%~dp0"
echo [INFO] 作業フォルダ: %CD%

REM ── Python の存在確認 ────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] Python が見つかりません。
    echo         Python をインストールして PATH に追加してください。
    echo         https://www.python.org/downloads/
    goto :error
)

REM ── 日本語フォント自動検索 ───────────────────────────────────
if exist "C:\Windows\Fonts\meiryo.ttc"   set GAME_FONT_PATH=C:\Windows\Fonts\meiryo.ttc
if exist "C:\Windows\Fonts\msgothic.ttc" set GAME_FONT_PATH=C:\Windows\Fonts\msgothic.ttc
if exist "C:\Windows\Fonts\YuGothM.ttc"  set GAME_FONT_PATH=C:\Windows\Fonts\YuGothM.ttc
if not "%GAME_FONT_PATH%"=="" echo [INFO] フォント: %GAME_FONT_PATH%

REM ── 仮想環境のセットアップ ───────────────────────────────────
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    echo [INFO] 仮想環境を読み込みました
) else (
    echo [INFO] 仮想環境を作成します（初回のみ時間がかかります）...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] 仮想環境の作成に失敗しました。
        goto :error
    )
    call .venv\Scripts\activate.bat
    pip install --upgrade pip -q
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] パッケージのインストールに失敗しました。
        goto :error
    )
)

REM ── API キーチェック ─────────────────────────────────────────
if "%YOUTUBE_API_KEY%"=="YOUR_YOUTUBE_API_KEY_HERE" (
    echo.
    echo [ERROR] YOUTUBE_API_KEY が未設定です。
    echo         このファイルをメモ帳で開いて
    echo         set YOUTUBE_API_KEY=YOUR_YOUTUBE_API_KEY_HERE
    echo         の行を実際のキーに書き換えてください。
    goto :error
)

REM ── 配信開始時刻の決定 ──────────────────────────────────────
REM START_TIME が空 → Pythonで「今から1分後」を一時ファイル経由で取得
if "%START_TIME%"=="" (
    python -c "from datetime import datetime,timedelta,timezone; t=datetime.now(timezone(timedelta(hours=9)))+timedelta(minutes=1); open('_tmp_st.txt','w').write(t.strftime('%%Y-%%m-%%dT%%H:%%M:%%S+09:00'))"
    if errorlevel 1 (
        echo [ERROR] 開始時刻の計算に失敗しました。
        goto :error
    )
    set /p START_TIME=<_tmp_st.txt
    del _tmp_st.txt 2>nul
    echo [INFO] 開始時刻を自動設定: %START_TIME%
) else (
    echo [INFO] 開始時刻: %START_TIME%
)

echo.
echo ========================================
echo  YouTube LIVE 競馬ゲーム 全自動起動
echo  配信枠を作成中...
echo ========================================

REM ── 配信枠作成（エラーはそのまま表示）───────────────────────
for /f "delims=" %%i in ('python create_broadcast.py --start "%START_TIME%"') do set VIDEO_ID=%%i

if "%VIDEO_ID%"=="" (
    echo.
    echo [ERROR] 配信枠の作成に失敗しました。
    echo         上のエラーメッセージを確認してください。
    echo         - client_secret.json が存在するか確認
    echo         - token.json が有効か確認（削除して再認証）
    goto :error
)

echo [INFO] 配信枠作成完了！
echo [INFO] video_id : %VIDEO_ID%
echo [INFO] URL      : https://youtu.be/%VIDEO_ID%
echo.

REM ── ゲーム起動 ───────────────────────────────────────────────
echo ========================================
echo  ゲームを起動します
echo  video_id : %VIDEO_ID%
echo  races    : %RACES%
echo ========================================
echo.

python main.py %VIDEO_ID% --races %RACES%

echo.
echo ========================================
echo  終了しました
echo ========================================
pause
exit /b 0

REM ── エラー終了 ───────────────────────────────────────────────
:error
echo.
echo ----------------------------------------
echo  エラーで終了しました。上のメッセージを確認してください。
echo ----------------------------------------
pause
exit /b 1

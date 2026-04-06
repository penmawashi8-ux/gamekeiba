@echo off
chcp 65001 >nul
REM ============================================================
REM バーチャル競馬LIVE 毎日19時 全自動配信スクリプト
REM ============================================================
REM 【使い方】
REM   タスクスケジューラから毎日18:55に自動実行されます。
REM   手動で実行する場合はダブルクリックするだけでOKです。
REM
REM 【処理の流れ】
REM   1. create_broadcast.py でYouTube配信枠を自動作成（限定公開）
REM   2. 取得したVIDEO_IDでゲームを起動
REM   3. 20レース終了後に自動終了・配信停止
REM
REM 【事前準備】
REM   1. YOUTUBE_API_KEY を下記に設定してください
REM   2. client_secret.json をこのフォルダに配置してください
REM      （初回のみブラウザでOAuth認証が開きます）
REM   詳細は README.md の「OAuth2の設定手順」を参照してください
REM ============================================================

REM ── 設定項目（ここを編集してください）────────────────────
set YOUTUBE_API_KEY=YOUR_YOUTUBE_API_KEY_HERE
set OBS_PASSWORD=
set GAME_FONT_PATH=

REM スクリプトのディレクトリに移動
cd /d "%~dp0"

echo ========================================
echo  バーチャル競馬LIVE 自動配信スクリプト
echo  %date% %time%
echo ========================================

REM ── 日本語フォント自動検索 ────────────────────────────────
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
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install --upgrade pip
    pip install -r requirements.txt
    pip install google-auth-oauthlib
)

REM google-auth-oauthlib が未インストールの場合に追加インストール
pip show google-auth-oauthlib >nul 2>&1
if errorlevel 1 (
    echo [INFO] google-auth-oauthlib をインストールします...
    pip install google-auth-oauthlib
)

REM ── YouTube配信枠を自動作成 ────────────────────────────────
echo [INFO] YouTube配信枠を作成しています...
for /f "usebackq delims=" %%i in (`python create_broadcast.py 2^>con`) do set VIDEO_ID=%%i

if "%VIDEO_ID%"=="" (
    echo.
    echo [ERROR] 配信枠の作成に失敗しました。
    echo.
    echo 確認事項:
    echo   1. client_secret.json がこのフォルダにあるか確認
    echo   2. YOUTUBE_API_KEY が正しく設定されているか確認
    echo   3. インターネット接続を確認
    echo   4. python create_broadcast.py を手動実行してエラーを確認
    echo.
    pause
    exit /b 1
)

echo [INFO] VIDEO_ID の取得に成功: %VIDEO_ID%

REM ── ゲーム起動（20レース固定）────────────────────────────
echo.
echo ========================================
echo  配信開始
echo  タイトル : バーチャル競馬LIVE
echo  VIDEO_ID : %VIDEO_ID%
echo  レース数 : 20
echo ========================================
echo.

python main.py %VIDEO_ID% --races 20

echo.
echo ========================================
echo  配信終了しました (%date% %time%)
echo ========================================
pause

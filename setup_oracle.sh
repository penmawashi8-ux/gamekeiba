#!/bin/bash
# Oracle Cloud Free Tier — gamekeiba バックエンド セットアップスクリプト
# 使い方: bash setup_oracle.sh <フロントエンドのVercel URL>
# 例:    bash setup_oracle.sh https://gamekeiba.vercel.app

set -e

FRONTEND_URL="${1:-https://your-frontend.vercel.app}"
REPO_URL="https://github.com/penmawashi8-ux/gamekeiba"
APP_DIR="/opt/gamekeiba/backend"
SERVICE_NAME="gamekeiba-backend"

echo "================================================"
echo " gamekeiba Oracle Cloud セットアップ"
echo " フロントエンドURL: $FRONTEND_URL"
echo "================================================"

# ── 1. システム更新・パッケージインストール ────────────────
sudo apt-get update -y
sudo apt-get install -y python3 python3-pip python3-venv git nginx certbot python3-certbot-nginx netfilter-persistent

# ── 2. リポジトリ取得 ─────────────────────────────────────
sudo mkdir -p /opt/gamekeiba
sudo chown "$USER:$USER" /opt/gamekeiba

if [ -d "$APP_DIR" ]; then
    echo "リポジトリを更新中..."
    git -C /opt/gamekeiba pull
else
    echo "リポジトリをクローン中..."
    git clone "$REPO_URL" /opt/gamekeiba
fi

# ── 3. Python 仮想環境・依存パッケージ ───────────────────
cd "$APP_DIR"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# ── 4. 環境変数ファイル ───────────────────────────────────
cat > "$APP_DIR/.env" <<EOF
ALLOWED_ORIGINS=$FRONTEND_URL,http://localhost:3000
MAX_RUNTIME_HOURS=0
IDLE_SHUTDOWN_MINUTES=0
EOF
echo ".env を作成しました: $APP_DIR/.env"

# ── 5. systemd サービス ───────────────────────────────────
sudo tee /etc/systemd/system/"$SERVICE_NAME".service > /dev/null <<EOF
[Unit]
Description=Gamekeiba Backend (FastAPI)
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl start "$SERVICE_NAME"
echo "サービス起動: $SERVICE_NAME"

# ── 6. nginx 設定（WebSocket プロキシ） ──────────────────
# ドメイン名を取得（後でcertbotが使う）
PUBLIC_IP=$(curl -s ifconfig.me)

sudo tee /etc/nginx/sites-available/gamekeiba > /dev/null <<'NGINX'
server {
    listen 80;
    server_name _;

    # WebSocket
    location /ws {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade    $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host       $host;
        proxy_read_timeout 86400s;
    }

    # REST / health
    location / {
        proxy_pass       http://127.0.0.1:8000;
        proxy_set_header Host            $host;
        proxy_set_header X-Real-IP       $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
NGINX

sudo ln -sf /etc/nginx/sites-available/gamekeiba /etc/nginx/sites-enabled/gamekeiba
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
echo "nginx 設定完了"

# ── 7. OS ファイアウォール開放 ────────────────────────────
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80  -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
echo "ポート 80/443 開放完了"

# ── 完了メッセージ ────────────────────────────────────────
echo ""
echo "================================================"
echo " セットアップ完了！"
echo "================================================"
echo ""
echo "【次にやること】"
echo ""
echo "1. Oracle Cloud Console で Security List を開く"
echo "   ポート 80 と 443 を Ingress Rule に追加"
echo "   （これをしないと外から繋がりません）"
echo ""
echo "2. ドメインを持っている場合は HTTPS 化:"
echo "   sudo certbot --nginx -d あなたのドメイン.com"
echo "   → 証明書取得後、WSS URL は wss://あなたのドメイン.com/ws"
echo ""
echo "3. Vercel の環境変数を更新:"
echo "   NEXT_PUBLIC_WS_URL=wss://あなたのドメイン.com/ws"
echo ""
echo "現在のパブリックIP: $PUBLIC_IP"
echo "（ドメインなしの場合は http://$PUBLIC_IP/health で疎通確認）"
echo ""
echo "サービス状態確認: sudo systemctl status $SERVICE_NAME"
echo "ログ確認:         sudo journalctl -u $SERVICE_NAME -f"

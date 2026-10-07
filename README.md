# バーチャル競馬

ブラウザで遊べるリアルタイム競馬ゲーム。予想して馬券を買い、レースを観戦する。
実際の賭けや金銭のやりとりは一切なく、所持金はゲーム内の数値のみ。

公開URL: https://gamekeiba.boardgamecat.com
（[ボドゲ広場](https://boardgamecat.com/games/keiba) に埋め込まれている）

## 構成

| ディレクトリ | 内容 | デプロイ先 |
|---|---|---|
| `backend/` | FastAPI + WebSocket。レース進行・オッズ・払い戻しを一手に持つ | Render（`render.yaml`） |
| `frontend/` | Next.js。Canvas でレースを描画する | Vercel |

すべてのゲーム状態はサーバー側にあり、クライアントは WebSocket で受け取って描画するだけ。

## レースが動く条件

**誰かが接続している間だけレースを回す。** 誰も見ていないときは待機し、
最初の1人が接続した時点で投票受付から始まる。

判定はレースの切れ目でのみ行うので、レース中に全員が抜けてもそのレースは
最後まで進む。途中でリロードしても中断されない。

## ローカルで動かす

バックエンド:

```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8000
```

フロントエンド:

```bash
cd frontend
npm install
WS_URL=ws://127.0.0.1:8000/ws npm run dev
```

## 環境変数

### frontend

| 変数 | 説明 |
|---|---|
| `WS_URL` | バックエンドの WebSocket URL。**実行時**に `/api/config` 経由で読まれるので、変更に再ビルドは不要 |
| `NEXT_PUBLIC_WS_URL` | 同上のフォールバック。ビルド時にバンドルへ焼き込まれるため、変更には再デプロイが必要 |

両方ある場合は `WS_URL` が優先される。詳細は `frontend/.env.example`。

### backend

| 変数 | 既定 | 説明 |
|---|---|---|
| `ALLOWED_ORIGINS` | `*` | CORS 許可オリジン（カンマ区切り） |
| `DATABASE_URL` | なし | 所持金の保存先 Postgres。未設定だと `users.db` (SQLite) になり、Render では再デプロイや自動スリープ復帰のたびに消える |
| `NIGHT_START_JST` | `0` | 夜間休止の開始時刻。`0` で無効 |
| `NIGHT_END_JST` | `8` | 夜間休止の終了時刻 |
| `IDLE_SHUTDOWN_MINUTES` | `0` | 無人が続いたら休止。`0` で無効 |
| `MAX_RUNTIME_HOURS` | `0` | 連続稼働の上限。`0` で無効 |
| `EXIT_ON_SHUTDOWN` | `0` | `1` でプロセスごと終了。Render では `0`（終了すると再起動ループになる） |
| `ADMIN_TOKEN` | なし | メンテナンス用の管理APIの合言葉。未設定なら管理APIは使えない |

## メンテナンス（デプロイの前に）

バックエンドを再デプロイするとプロセスが入れ替わり、進行中のレースは消える。
そのまま出すとレース途中で止まるので、先にメンテナンスを予約する。

```bash
# 5分後以降、そのとき進行中のレースが終わったら止める（全員の画面に予告が出る）
curl -X POST -H "X-Admin-Token: $ADMIN_TOKEN" "https://<バックエンド>/admin/maintenance?minutes=5"
# 取り消し（デプロイせずに再開したいとき）
curl -X DELETE -H "X-Admin-Token: $ADMIN_TOKEN" "https://<バックエンド>/admin/maintenance"
```

- 止まるのは「開始時刻を過ぎて最初のレースの切れ目」。賭けたまま中断される人は出ない
- 止まったのは `/health` の `maintenance.active` が `true` になったことで分かる。そこでデプロイすれば、新しいプロセスは通常どおり始まる
- 予約せずに再起動した場合も、停止時（SIGTERM）に払い戻し前の馬券は全額返金する

## 転送量について

Render の無料枠は月5GBで、以前これを使い切ってワークスペースごと停止したことがある。
レース中の位置更新は全接続へのブロードキャストなので、ここのサイズがそのまま転送量になる。

現在は1人あたり約2.4 MB/時。内訳と削減の経緯は `game_engine.py` の
`_race_update_msg` / `_countdown_msg` / `_human_payouts` のコメントを参照。

送信形式を変えるときは、フロントとバックエンドが別々にデプロイされる点に注意。
切り替わりの前後でどちらの形式が届いてもレースが止まらないようにすること
（`parsePositions` が旧形式のフォールバックを持っている）。

## オッズ計算方式（パリミュチュエル）

```
単勝オッズ[馬番] = 全単勝売上 × 0.80 ÷ その馬への単勝売上
複勝オッズ[馬番] = 全複勝売上 × 0.75 ÷ その馬への複勝売上
```

- 馬券が売れるたびにリアルタイムで再計算する
- 誰も購入していない馬はオッズを表示しない
- 複勝の実配当は JRA 方式: `((W + D/3) × 0.80) / W`
  （`D` は3着外れ馬の複勝売上合計）

オッズを成立させるため、投票受付の中間地点で CPU が馬券を買う
（`BOT_COUNT` 体 + 全馬への最低1件）。

## 注意

`users.db` は SQLite で、コンテナ内に置かれる。Render はディスクが永続しないため、
再デプロイや再起動で所持金はリセットされる。

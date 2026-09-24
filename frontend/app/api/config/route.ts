import { NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

// 接続先を実行時に返す。
// NEXT_PUBLIC_* はビルド時にバンドルへ焼き込まれるため、Vercel の環境変数を
// 直しても再デプロイするまで反映されない。バックエンドの引っ越し（Railway →
// Render）のように接続先が変わったときに「環境変数は直したのに繋がらない」が
// 起きるので、実行時に読める経路を用意しておく。
// WS_URL が未設定なら従来どおりビルド時の値にフォールバックする。
export function GET() {
  return NextResponse.json({
    wsUrl: process.env.WS_URL ?? process.env.NEXT_PUBLIC_WS_URL ?? '',
  })
}

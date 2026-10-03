import type { Metadata, Viewport } from 'next'
import './globals.css'

export const metadata: Metadata = {
  metadataBase: new URL('https://gamekeiba.boardgamecat.com'),
  title: '競馬ゲーム',
  description: 'ブラウザで遊べるリアルタイム競馬ゲーム',
  // このサブドメインはゲーム本体で、クローラーが読める本文がほとんどない
  // （最初に出るのは名前の入力欄だけ）。審査対象ドメイン boardgamecat.com に
  // 本文のないページを並べることになり、AdSense の
  // 「screens without publisher-content」に当たるため検索インデックスから外す。
  // 説明文を持つ正規のページは https://boardgamecat.com/games/keiba 側。
  robots: {
    index: false,
    follow: true,
  },
}

// themeColor は metadata では非推奨（Next.js 14 以降）。viewport に移す。
export const viewport: Viewport = {
  themeColor: '#d1d5db',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body className="min-h-screen bg-gray-300">{children}</body>
    </html>
  )
}

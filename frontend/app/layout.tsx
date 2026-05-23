import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: '競馬ゲーム',
  description: 'ブラウザで遊べるリアルタイム競馬ゲーム',
  themeColor: '#d1d5db',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body className="min-h-screen bg-gray-300">{children}</body>
    </html>
  )
}

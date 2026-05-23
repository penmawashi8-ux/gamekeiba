import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: '競馬ゲーム',
  description: 'ブラウザで遊べるリアルタイム競馬ゲーム',
  themeColor: '#e5e7eb',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body className="min-h-screen bg-gray-200">{children}</body>
    </html>
  )
}

'use client'

import { useState } from 'react'

import type { RankingRow } from '@/types/game'

interface Props {
  leaderboard: RankingRow[]
  onlineLeaderboard: RankingRow[]
  myName: string
  myPublicId: string
}

type Tab = 'online' | 'total'

const TABS: { key: Tab; label: string }[] = [
  { key: 'online', label: 'オンライン' },
  { key: 'total',  label: 'トータル' },
]

const MEDALS = ['🥇', '🥈', '🥉']

export default function Leaderboard({ leaderboard, onlineLeaderboard, myName, myPublicId }: Props) {
  const [tab, setTab] = useState<Tab>('online')
  const rows = tab === 'online' ? onlineLeaderboard : leaderboard
  // 名前は重複しうるので識別子で見分ける。識別子が無い（古いサーバー）ときだけ名前で比べる
  const isMe = ([name, , pid]: RankingRow) => pid ? pid === myPublicId : name === myName

  return (
    <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
      <div className="px-4 py-2 bg-gray-100 flex items-center justify-between gap-2">
        <h3 className="text-gray-900 font-bold text-sm">残高ランキング TOP5</h3>
        <div className="flex rounded-md border border-gray-300 overflow-hidden text-xs">
          {TABS.map(t => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-2 py-1 ${tab === t.key
                ? 'bg-gray-800 text-white font-bold'
                : 'bg-white text-gray-600'}`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>
      {rows.length === 0 ? (
        <p className="px-4 py-3 text-xs text-gray-500 text-center">まだランキングはありません</p>
      ) : (
        <div className="divide-y divide-gray-100">
          {rows.map((row, i) => {
            const [name, balance] = row
            const me = isMe(row)
            return (
            <div
              key={i}
              className={`flex items-center justify-between px-4 py-2
                ${me ? 'bg-yellow-50' : ''}`}
            >
              <div className="flex items-center gap-2">
                <span className="text-base w-6 text-center">{MEDALS[i] ?? `${i + 1}`}</span>
                <span className={`text-sm font-medium ${me ? 'text-yellow-600' : 'text-gray-700'}`}>
                  {name}{me ? ' (あなた)' : ''}
                </span>
              </div>
              <span className="font-mono text-sm text-green-600">
                ¥{balance.toLocaleString()}
              </span>
            </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

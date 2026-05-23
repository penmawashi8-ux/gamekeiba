'use client'

interface Props {
  leaderboard: [string, number][]
  myName: string
}

const MEDALS = ['🥇', '🥈', '🥉']

export default function Leaderboard({ leaderboard, myName }: Props) {
  if (leaderboard.length === 0) return null

  return (
    <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
      <div className="px-4 py-2 bg-gray-100">
        <h3 className="text-gray-900 font-bold text-sm">残高ランキング TOP{leaderboard.length}</h3>
      </div>
      <div className="divide-y divide-gray-100">
        {leaderboard.map(([name, balance], i) => (
          <div
            key={i}
            className={`flex items-center justify-between px-4 py-2
              ${name === myName ? 'bg-yellow-50' : ''}`}
          >
            <div className="flex items-center gap-2">
              <span className="text-base w-6 text-center">{MEDALS[i] ?? `${i + 1}`}</span>
              <span className={`text-sm font-medium ${name === myName ? 'text-yellow-600' : 'text-gray-700'}`}>
                {name}{name === myName ? ' (あなた)' : ''}
              </span>
            </div>
            <span className="font-mono text-sm text-green-600">
              ¥{balance.toLocaleString()}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

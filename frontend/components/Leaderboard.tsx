'use client'

interface Props {
  leaderboard: [string, number][]
  myName: string
}

const MEDALS = ['🥇', '🥈', '🥉']

export default function Leaderboard({ leaderboard, myName }: Props) {
  if (leaderboard.length === 0) return null

  return (
    <div className="bg-gray-900 rounded-lg overflow-hidden">
      <div className="px-4 py-2 bg-gray-800">
        <h3 className="text-white font-bold text-sm">残高ランキング TOP{leaderboard.length}</h3>
      </div>
      <div className="divide-y divide-gray-800">
        {leaderboard.map(([name, balance], i) => (
          <div
            key={i}
            className={`flex items-center justify-between px-4 py-2
              ${name === myName ? 'bg-yellow-900/30' : ''}`}
          >
            <div className="flex items-center gap-2">
              <span className="text-base w-6 text-center">{MEDALS[i] ?? `${i + 1}`}</span>
              <span className={`text-sm font-medium ${name === myName ? 'text-yellow-300' : 'text-gray-200'}`}>
                {name}{name === myName ? ' (あなた)' : ''}
              </span>
            </div>
            <span className="font-mono text-sm text-green-400">
              ¥{balance.toLocaleString()}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

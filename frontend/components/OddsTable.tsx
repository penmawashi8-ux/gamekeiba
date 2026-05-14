'use client'

import type { HorseInfo, Pools } from '@/types/game'

interface Props {
  horses: HorseInfo[]
  winOdds: Record<string, number>
  showOdds: Record<string, number>
  pools: Pools
}

export default function OddsTable({ horses, winOdds, showOdds, pools }: Props) {
  if (horses.length === 0) return null

  return (
    <div className="bg-gray-900 rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2 bg-gray-800">
        <h3 className="text-white font-bold text-sm">出馬表・オッズ</h3>
        <div className="flex gap-4 text-xs text-gray-400">
          <span>単勝総額 <span className="text-yellow-300 font-mono">¥{pools.win_total.toLocaleString()}</span></span>
          <span>複勝総額 <span className="text-blue-300 font-mono">¥{pools.show_total.toLocaleString()}</span></span>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-400 text-xs border-b border-gray-700">
              <th className="px-3 py-1.5 text-left w-8">枠</th>
              <th className="px-3 py-1.5 text-left">馬名</th>
              <th className="px-3 py-1.5 text-center">脚質</th>
              <th className="px-3 py-1.5 text-center">強さ</th>
              <th className="px-3 py-1.5 text-right">単勝</th>
              <th className="px-3 py-1.5 text-right">複勝</th>
            </tr>
          </thead>
          <tbody>
            {horses.map(h => {
              const wo = winOdds[String(h.number)]
              const so = showOdds[String(h.number)]
              return (
                <tr key={h.number} className="border-b border-gray-800 hover:bg-gray-800/50">
                  <td className="px-3 py-2">
                    <span
                      className="inline-flex w-7 h-7 items-center justify-center rounded-full text-xs font-bold"
                      style={{
                        background: h.color,
                        color: needsDark(h.color) ? '#000' : '#fff',
                      }}
                    >
                      {h.number}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-white font-medium">{h.name}</td>
                  <td className="px-3 py-2 text-center">
                    <span className={`text-xs px-1.5 py-0.5 rounded font-bold ${styleColor(h.running_style)}`}>
                      {h.running_style}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-center text-yellow-400 text-xs tracking-tight">
                    {h.stars}
                  </td>
                  <td className="px-3 py-2 text-right font-mono">
                    {wo ? (
                      <span className={`font-bold ${oddsColor(wo)}`}>{wo.toFixed(1)}倍</span>
                    ) : (
                      <span className="text-gray-600">-</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right font-mono">
                    {so ? (
                      <span className={`font-bold ${oddsColor(so)}`}>{so.toFixed(1)}倍</span>
                    ) : (
                      <span className="text-gray-600">-</span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function needsDark(hex: string): boolean {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return (r * 299 + g * 587 + b * 114) / 1000 > 150
}

function styleColor(style: string): string {
  return {
    '逃げ':   'bg-red-800 text-red-200',
    '先行':   'bg-orange-800 text-orange-200',
    '差し':   'bg-blue-800 text-blue-200',
    '追い込み': 'bg-purple-800 text-purple-200',
  }[style] ?? 'bg-gray-700 text-gray-300'
}

function oddsColor(odds: number): string {
  if (odds < 2)   return 'text-red-400'
  if (odds < 5)   return 'text-orange-400'
  if (odds < 10)  return 'text-yellow-400'
  if (odds < 30)  return 'text-green-400'
  return 'text-blue-400'
}

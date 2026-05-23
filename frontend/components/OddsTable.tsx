'use client'

import type { HorseInfo, Pools } from '@/types/game'

interface Props {
  horses: HorseInfo[]
  winOdds: Record<string, number>
  showOdds: Record<string, [number, number]>
  pools: Pools
}

export default function OddsTable({ horses, winOdds, showOdds, pools }: Props) {
  if (horses.length === 0) return null

  return (
    <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2 bg-gray-100">
        <h3 className="text-gray-900 font-bold text-sm">出馬表・オッズ</h3>
        <div className="flex gap-4 text-xs text-gray-500">
          <span>単勝総額 <span className="text-yellow-600 font-mono">¥{pools.win_total.toLocaleString()}</span></span>
          <span>複勝総額 <span className="text-blue-600 font-mono">¥{pools.show_total.toLocaleString()}</span></span>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-500 text-xs border-b border-gray-200">
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
                <tr key={h.number} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="px-3 py-2">
                    <span
                      className="inline-flex w-7 h-7 items-center justify-center rounded-full text-xs font-bold ring-1 ring-black/20"
                      style={{
                        background: h.color,
                        color: needsDark(h.color) ? '#000' : '#fff',
                      }}
                    >
                      {h.number}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-gray-900 font-medium whitespace-nowrap">{h.name}</td>
                  <td className="px-3 py-2 text-center">
                    <span className={`text-xs px-1.5 py-0.5 rounded font-bold whitespace-nowrap ${styleColor(h.running_style)}`}>
                      {styleShort(h.running_style)}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-center text-yellow-500 text-xs tracking-tight">
                    {h.stars}
                  </td>
                  <td className="px-3 py-2 text-right font-mono">
                    {wo ? (
                      <span className={`font-bold ${oddsColor(wo)}`}>{wo.toFixed(1)}倍</span>
                    ) : (
                      <span className="text-gray-400">-</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right font-mono">
                    {so ? (
                      <span className={`font-bold text-xs ${oddsColor(so[0])}`}>
                        {so[0].toFixed(1)}{so[0] !== so[1] ? `〜${so[1].toFixed(1)}` : ''}倍
                      </span>
                    ) : (
                      <span className="text-gray-400">-</span>
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

function styleShort(style: string): string {
  return { '逃げ': '逃', '先行': '先', '差し': '差', '追い込み': '追' }[style] ?? style[0]
}

function styleColor(style: string): string {
  return {
    '逃げ':   'bg-red-100 text-red-700',
    '先行':   'bg-orange-100 text-orange-700',
    '差し':   'bg-blue-100 text-blue-700',
    '追い込み': 'bg-purple-100 text-purple-700',
  }[style] ?? 'bg-gray-100 text-gray-600'
}

function oddsColor(odds: number): string {
  if (odds < 2)   return 'text-red-600'
  if (odds < 5)   return 'text-orange-600'
  if (odds < 10)  return 'text-yellow-600'
  if (odds < 30)  return 'text-green-600'
  return 'text-blue-600'
}

'use client'

import type { HorseInfo, PayoutInfo } from '@/types/game'

interface Props {
  ranking: number[]
  horses: HorseInfo[]
  winOdds: Record<string, number>
  showOdds: Record<string, [number, number]>
  payouts: PayoutInfo[]
  myUserId: string
  countdown: number
}

const PLACE_LABELS = ['1着', '2着', '3着']
const PLACE_STYLES = [
  'bg-yellow-400 text-black',
  'bg-gray-300 text-black',
  'bg-amber-600 text-white',
]

export default function ResultsPanel({
  ranking, horses, winOdds, showOdds, payouts, myUserId, countdown
}: Props) {
  const horseMap = Object.fromEntries(horses.map(h => [h.number, h]))
  const myPayouts = payouts.filter(p => p.user_id === myUserId)
  const myTotal   = myPayouts.reduce((s, p) => s + p.payout_amount, 0)
  const showActualOdds = Object.fromEntries(
    payouts.filter(p => p.bet_type === 'show').map(p => [String(p.horse), p.odds])
  )
  const popularityMap: Record<string, number> = Object.fromEntries(
    Object.entries(winOdds)
      .sort(([, a], [, b]) => a - b)
      .map(([horseNum], idx) => [horseNum, idx + 1])
  )

  return (
    <div className="bg-gray-900 rounded-lg p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-white font-bold text-lg">レース結果</h2>
        <span className="text-gray-400 text-sm">
          次のレースまで <span className="text-yellow-300 font-mono">{countdown}秒</span>
        </span>
      </div>

      {/* top 3 */}
      <div className="flex gap-2">
        {ranking.slice(0, 3).map((num, i) => {
          const h = horseMap[num]
          if (!h) return null
          const wo  = winOdds[String(num)]
          const actualShowOdds = showActualOdds[String(num)]
          const soRange = showOdds[String(num)]
          return (
            <div key={i} className="flex-1 rounded-lg overflow-hidden border border-gray-700">
              <div className={`text-center text-xs font-bold py-1 ${PLACE_STYLES[i]}`}>
                {PLACE_LABELS[i]}
              </div>
              <div className="p-2 text-center">
                <span
                  className="inline-flex w-8 h-8 items-center justify-center rounded-full text-sm font-bold mb-1"
                  style={{ background: h.color, color: needsDark(h.color) ? '#000' : '#fff' }}
                >
                  {h.number}
                </span>
                <p className="text-white text-xs font-medium leading-tight">{h.name}</p>
                <p className="text-gray-400 text-xs">
                  {popularityMap[String(h.number)] != null
                    ? `${popularityMap[String(h.number)]}番人気`
                    : h.running_style}
                </p>
                {i === 0 && wo && (
                  <p className="text-yellow-400 text-xs mt-1">単勝 {wo.toFixed(1)}倍</p>
                )}
                {i <= 2 && (actualShowOdds != null ? (
                  <p className="text-blue-400 text-xs">複勝 {actualShowOdds.toFixed(1)}倍</p>
                ) : soRange ? (
                  <p className="text-blue-400 text-xs">複勝 {soRange[0].toFixed(1)}〜{soRange[1].toFixed(1)}倍</p>
                ) : null)}
              </div>
            </div>
          )
        })}
      </div>

      {/* personal payout */}
      {myTotal > 0 ? (
        <div className="bg-green-900/50 border border-green-600 rounded-lg p-3">
          <p className="text-green-300 font-bold text-center text-lg">
            払い戻し ¥{myTotal.toLocaleString()}
          </p>
          <div className="mt-2 space-y-1">
            {myPayouts.map((p, i) => (
              <div key={i} className="flex justify-between text-xs text-green-200">
                <span>
                  {p.bet_type === 'win' ? '単勝' : '複勝'} {p.horse}番
                  × {p.odds.toFixed(1)}倍
                </span>
                <span className="font-mono">¥{p.payout_amount.toLocaleString()}</span>
              </div>
            ))}
          </div>
        </div>
      ) : myPayouts.length === 0 && payouts.length > 0 ? (
        <div className="bg-red-900/40 border border-red-700 rounded-lg p-3 text-center text-red-300 text-sm">
          ハズレ...
        </div>
      ) : null}

      {/* all payouts */}
      {payouts.length > 0 && (
        <div className="border-t border-gray-700 pt-3">
          <p className="text-gray-400 text-xs mb-2">全払い戻し情報</p>
          <div className="space-y-1 max-h-40 overflow-y-auto">
            {payouts.map((p, i) => (
              <div key={i} className="flex justify-between text-xs bg-gray-800 rounded px-2 py-1">
                <span className="text-gray-300">
                  {p.display_name} — {p.bet_type === 'win' ? '単勝' : '複勝'} {p.horse}番
                </span>
                <span className="text-green-400 font-mono">¥{p.payout_amount.toLocaleString()}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function needsDark(hex: string): boolean {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return (r * 299 + g * 587 + b * 114) / 1000 > 150
}

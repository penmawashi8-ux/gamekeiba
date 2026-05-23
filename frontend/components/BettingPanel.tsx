'use client'

import { useState } from 'react'
import type { HorseInfo, Bet } from '@/types/game'
import type { UserState } from '@/types/game'

interface Props {
  horses: HorseInfo[]
  winOdds: Record<string, number>
  showOdds: Record<string, [number, number]>
  user: UserState
  onBet: (betType: 'win' | 'show', horse: number, amount: number) => void
  disabled: boolean
}

const PRESETS = [100, 500, 1000, 5000, 10000]

export default function BettingPanel({ horses, winOdds, showOdds, user, onBet, disabled }: Props) {
  const [selectedHorse, setSelectedHorse] = useState<number | null>(null)
  const [betType, setBetType] = useState<'win' | 'show'>('win')
  const [amount, setAmount] = useState(500)
  const [flash, setFlash] = useState<string | null>(null)

  const handleBet = () => {
    if (!selectedHorse) { setFlash('馬を選択してください'); return }
    if (amount < 100)   { setFlash('最低100円から'); return }
    if (amount > user.balance) { setFlash('残高不足です'); return }
    onBet(betType, selectedHorse, amount)
    setFlash(`${selectedHorse}番に${betType === 'win' ? '単勝' : '複勝'} ${amount.toLocaleString()}円`)
    setTimeout(() => setFlash(null), 2000)
  }

  const selectedWinOdds  = (betType === 'win'  && selectedHorse) ? winOdds[String(selectedHorse)]  ?? null : null
  const selectedShowRange = (betType === 'show' && selectedHorse) ? showOdds[String(selectedHorse)] ?? null : null

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4 space-y-4 h-full">
      <div className="flex items-center justify-between">
        <h2 className="text-gray-900 font-bold text-lg">馬券購入</h2>
        <span className="text-yellow-600 font-mono text-sm">
          残高 ¥{user.balance.toLocaleString()}
        </span>
      </div>

      {/* bet type */}
      <div className="flex gap-2">
        {(['win', 'show'] as const).map(bt => (
          <button
            key={bt}
            onClick={() => setBetType(bt)}
            className={`flex-1 py-2 rounded font-bold text-sm transition
              ${betType === bt
                ? 'bg-yellow-400 text-black'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
          >
            {bt === 'win' ? '単勝' : '複勝'}
          </button>
        ))}
      </div>

      {/* horse grid */}
      <div className="grid grid-cols-4 gap-1.5">
        {horses.map(h => (
          <button
            key={h.number}
            onClick={() => setSelectedHorse(h.number)}
            disabled={disabled}
            style={{ borderColor: visibleBorderColor(h.color) }}
            className={`relative py-2 rounded text-xs font-bold transition border-2
              ${selectedHorse === h.number
                ? 'ring-2 ring-white scale-105'
                : 'opacity-80 hover:opacity-100'
              }
              ${disabled ? 'cursor-not-allowed' : ''}`}
          >
            <span
              className="block rounded-sm px-1 mb-0.5 text-center"
              style={{ background: h.color, color: needsDark(h.color) ? '#000' : '#fff' }}
            >
              {h.number}
            </span>
            <span className="text-gray-700 block text-center leading-tight">
              {h.name.slice(0, 4)}
            </span>
            <span className="text-green-600 block text-center leading-tight" style={{ fontSize: '0.6rem' }}>
              {betType === 'win'
                ? (winOdds[String(h.number)] ? `${winOdds[String(h.number)].toFixed(1)}倍` : '-')
                : (() => { const r = showOdds[String(h.number)]; return r ? `${r[0].toFixed(1)}〜${r[1].toFixed(1)}倍` : '-' })()
              }
            </span>
          </button>
        ))}
      </div>

      {/* amount */}
      <div className="space-y-2">
        <div className="flex flex-wrap gap-1">
          {PRESETS.map(p => (
            <button
              key={p}
              onClick={() => setAmount(p)}
              className={`px-2 py-1 rounded text-xs font-bold transition
                ${amount === p ? 'bg-yellow-400 text-black' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}
            >
              {p >= 1000 ? `${p / 1000}k` : p}
            </button>
          ))}
          <button
            onClick={() => setAmount(user.balance)}
            className="px-2 py-1 rounded text-xs font-bold bg-red-700 text-white hover:bg-red-600"
          >
            ALL IN
          </button>
        </div>
        <div className="flex gap-2 items-center">
          <input
            type="number"
            min={100}
            step={100}
            value={amount}
            onChange={e => setAmount(Math.max(0, parseInt(e.target.value) || 0))}
            className="flex-1 bg-gray-50 text-gray-900 rounded px-3 py-1.5 text-sm font-mono border border-gray-300 focus:border-yellow-500 outline-none"
          />
          <span className="text-gray-400 text-sm">円</span>
        </div>
      </div>

      {/* expected payout */}
      {selectedHorse && (selectedWinOdds != null || selectedShowRange != null) && (
        <div className="bg-gray-50 border border-gray-200 rounded px-3 py-2 text-sm flex justify-between items-center">
          <span className="text-gray-500">予想払戻</span>
          {selectedWinOdds != null ? (
            <span className="text-green-600 font-bold">
              ¥{(Math.floor(amount * selectedWinOdds / 10) * 10).toLocaleString()}
            </span>
          ) : selectedShowRange != null ? (
            <span className="text-green-600 font-bold text-xs">
              ¥{(Math.floor(amount * selectedShowRange[0] / 10) * 10).toLocaleString()}
              〜¥{(Math.floor(amount * selectedShowRange[1] / 10) * 10).toLocaleString()}
            </span>
          ) : null}
        </div>
      )}

      {/* submit */}
      <button
        onClick={handleBet}
        disabled={disabled || !selectedHorse}
        className={`w-full py-3 rounded-lg font-bold text-base transition
          ${disabled || !selectedHorse
            ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
            : 'bg-yellow-400 text-black hover:bg-yellow-300 active:scale-95'
          }`}
      >
        {disabled ? '受付終了' : '馬券を買う'}
      </button>

      {flash && (
        <div className="bg-green-100 text-green-700 text-sm text-center rounded px-2 py-1 animate-pulse">
          {flash}
        </div>
      )}

      {/* current bets */}
      {user.myBets.length > 0 && (
        <div className="border-t border-gray-200 pt-3">
          <p className="text-gray-500 text-xs mb-2">購入済み馬券</p>
          <div className="space-y-1 max-h-32 overflow-y-auto">
            {user.myBets.map((b, i) => (
              <div key={i} className="flex justify-between text-xs bg-gray-50 border border-gray-100 rounded px-2 py-1">
                <span className="text-gray-700">
                  {b.bet_type === 'win' ? '単勝' : '複勝'} {b.horse}番
                </span>
                <span className="text-yellow-600 font-mono">¥{b.amount.toLocaleString()}</span>
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

function visibleBorderColor(hex: string): string {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  const brightness = (r * 299 + g * 587 + b * 114) / 1000
  if (brightness < 60)  return '#999999'
  if (brightness > 200) return '#888888'
  return hex
}

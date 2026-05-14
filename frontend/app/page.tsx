'use client'

import { useState, useEffect } from 'react'
import { useGameSocket } from '@/hooks/useGameSocket'
import { useVersionCheck } from '@/hooks/useVersionCheck'
import GameCanvas from '@/components/GameCanvas'
import BettingPanel from '@/components/BettingPanel'
import OddsTable from '@/components/OddsTable'
import Leaderboard from '@/components/Leaderboard'
import ResultsPanel from '@/components/ResultsPanel'

function LoginScreen({ onJoin }: { onJoin: (name: string) => void }) {
  const [name, setName] = useState('')
  const submit = () => { const n = name.trim(); if (n) onJoin(n) }
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950 px-4">
      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-8 w-full max-w-sm shadow-2xl">
        <div className="text-center mb-6">
          <div className="text-5xl mb-3">🏇</div>
          <h1 className="text-white text-2xl font-bold tracking-tight">競馬ゲーム</h1>
          <p className="text-gray-500 text-sm mt-1">リアルタイム馬券ゲーム</p>
        </div>
        <div className="space-y-3">
          <input
            type="text" placeholder="プレイヤー名" value={name}
            onChange={e => setName(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && submit()}
            maxLength={20}
            className="w-full bg-gray-800 text-white rounded-xl px-4 py-3 border border-gray-700
              focus:border-yellow-400 focus:ring-1 focus:ring-yellow-400/30 outline-none
              text-center text-base placeholder:text-gray-600"
            autoFocus
          />
          <button onClick={submit} disabled={!name.trim()}
            className="w-full py-3 bg-yellow-400 text-black font-bold rounded-xl text-base
              hover:bg-yellow-300 active:scale-95 transition-all
              disabled:opacity-30 disabled:cursor-not-allowed">
            参加する
          </button>
        </div>
        <p className="text-center text-gray-600 text-xs mt-5">
          初回参加で ¥10,000 付与 · 単勝・複勝で勝負！
        </p>
      </div>
    </div>
  )
}

function PhaseBar({ phase, countdown, raceNumber }: { phase: string; countdown: number; raceNumber: number }) {
  const mm = String(Math.floor(countdown / 60)).padStart(2, '0')
  const ss = String(countdown % 60).padStart(2, '0')
  const badge: Record<string, { label: string; cls: string }> = {
    waiting: { label: '待機中',     cls: 'bg-gray-700 text-gray-300' },
    betting: { label: '馬券受付中', cls: 'bg-emerald-700 text-emerald-100' },
    racing:  { label: 'レース中',   cls: 'bg-red-700 text-red-100' },
    results: { label: '結果発表',   cls: 'bg-blue-700 text-blue-100' },
  }
  const b = badge[phase] ?? badge.waiting
  return (
    <div className="flex items-center gap-2 flex-wrap">
      {raceNumber > 0 && (
        <span className="text-xs font-semibold text-gray-400 bg-gray-800 px-2 py-1 rounded-lg">第{raceNumber}R</span>
      )}
      <span className={`text-xs font-bold px-3 py-1 rounded-lg ${b.cls}`}>{b.label}</span>
      {phase === 'betting' && countdown > 0 && (
        <span className="text-yellow-400 font-mono text-sm font-bold tabular-nums">{mm}:{ss}</span>
      )}
      {phase === 'results' && countdown > 0 && (
        <span className="text-gray-400 text-xs">次まで {ss}秒</span>
      )}
    </div>
  )
}

export default function Home() {
  const [playerName, setPlayerName] = useState<string | null>(null)
  const [toast, setToast] = useState<{ msg: string; type: 'win' | 'lose' } | null>(null)
  const { game, user, connected, error, placeBet } = useGameSocket(playerName)
  const updateAvailable = useVersionCheck()

  useEffect(() => {
    if (user.lastPayout == null) return
    setToast(user.lastPayout > 0
      ? { msg: `払い戻し ¥${user.lastPayout.toLocaleString()}`, type: 'win' }
      : { msg: 'ハズレ...', type: 'lose' }
    )
    const t = setTimeout(() => setToast(null), 3000)
    return () => clearTimeout(t)
  }, [user.lastPayout])

  if (!playerName) return <LoginScreen onJoin={setPlayerName} />

  const isBetting = game.phase === 'betting'
  const isRacing  = game.phase === 'racing'
  const isResults = game.phase === 'results'

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <header className="sticky top-0 z-40 bg-gray-900/95 backdrop-blur border-b border-gray-800/80">
        <div className="max-w-5xl mx-auto px-3 py-2 flex items-center gap-3">
          <span className="text-lg">🏇</span>
          <div className="flex-1 min-w-0">
            <PhaseBar phase={game.phase} countdown={game.countdown} raceNumber={game.raceNumber} />
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <span className="hidden sm:flex items-center gap-1 text-xs text-gray-500">
              <span className="w-1.5 h-1.5 rounded-full bg-green-400 inline-block" />
              {game.online}人
            </span>
            <div className="text-right">
              <div className="text-gray-400 text-xs leading-none mb-0.5">{user.displayName}</div>
              <div className="text-yellow-300 font-mono font-bold text-sm leading-none">¥{user.balance.toLocaleString()}</div>
            </div>
            <div className={`w-2 h-2 rounded-full shrink-0 ${connected ? 'bg-green-400' : 'bg-red-500'}`} />
          </div>
        </div>
      </header>
      {error && (
        <div className="bg-red-950 border-b border-red-800 text-red-300 text-center py-2 text-sm px-4">{error}</div>
      )}
      {updateAvailable && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3
          bg-blue-600 text-white text-sm font-medium px-5 py-3 rounded-xl shadow-xl">
          <span>新しいバージョンがあります</span>
          <button onClick={() => window.location.reload()}
            className="bg-white text-blue-700 px-3 py-1 rounded-lg text-xs font-bold hover:bg-blue-50 active:scale-95 transition-all">
            更新
          </button>
        </div>
      )}
      {toast && (
        <div className={`fixed top-14 left-1/2 -translate-x-1/2 z-50 px-5 py-2.5 rounded-xl shadow-xl text-sm font-bold
          ${toast.type === 'win' ? 'bg-emerald-600 text-white' : 'bg-gray-700 text-gray-300'}`}>
          {toast.msg}
        </div>
      )}
      <main className="max-w-5xl mx-auto p-3 space-y-3">
        <div className="rounded-xl overflow-hidden ring-1 ring-white/5 shadow-xl">
          <GameCanvas phase={game.phase} horses={game.horses} positions={game.positions}
            raceRanking={game.raceRanking} countdown={game.countdown} />
        </div>
        {(isBetting || isRacing) && (
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-3">
            <div className="lg:col-span-3">
              <OddsTable horses={game.horses} winOdds={game.winOdds} showOdds={game.showOdds} pools={game.pools} />
            </div>
            <div className="lg:col-span-2">
              <BettingPanel horses={game.horses} winOdds={game.winOdds} showOdds={game.showOdds}
                user={user} onBet={placeBet} disabled={!isBetting} />
            </div>
          </div>
        )}
        {isResults && (
          <ResultsPanel ranking={game.raceRanking} horses={game.horses} winOdds={game.winOdds}
            showOdds={game.showOdds} payouts={game.payouts} myUserId={user.userId} countdown={game.countdown} />
        )}
        {game.leaderboard.length > 0 && (
          <Leaderboard leaderboard={game.leaderboard} myName={user.displayName} />
        )}
      </main>
    </div>
  )
}

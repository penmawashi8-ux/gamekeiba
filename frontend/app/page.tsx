'use client'

import { useState, useEffect } from 'react'
import { useGameSocket } from '@/hooks/useGameSocket'
import GameCanvas from '@/components/GameCanvas'
import BettingPanel from '@/components/BettingPanel'
import OddsTable from '@/components/OddsTable'
import Leaderboard from '@/components/Leaderboard'
import ResultsPanel from '@/components/ResultsPanel'

// ── Login screen ──────────────────────────────────────────────────────────────

function LoginScreen({ onJoin }: { onJoin: (name: string) => void }) {
  const [name, setName] = useState('')

  const submit = () => {
    const n = name.trim()
    if (n) onJoin(n)
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950 px-4">
      <div className="bg-gray-900 rounded-2xl p-8 w-full max-w-sm space-y-6 shadow-2xl">
        <div className="text-center">
          <div className="text-5xl mb-3">🏇</div>
          <h1 className="text-white text-2xl font-bold">競馬ゲーム</h1>
          <p className="text-gray-400 text-sm mt-1">みんなで楽しむリアルタイム馬券ゲーム</p>
        </div>
        <div className="space-y-3">
          <input
            type="text"
            placeholder="プレイヤー名を入力"
            value={name}
            onChange={e => setName(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && submit()}
            maxLength={20}
            className="w-full bg-gray-800 text-white rounded-lg px-4 py-3 border border-gray-600 focus:border-yellow-400 outline-none text-center text-lg"
            autoFocus
          />
          <button
            onClick={submit}
            disabled={!name.trim()}
            className="w-full py-3 bg-yellow-400 text-black font-bold rounded-lg text-lg
              hover:bg-yellow-300 active:scale-95 transition disabled:opacity-40 disabled:cursor-not-allowed"
          >
            参加する
          </button>
        </div>
        <div className="text-center text-gray-500 text-xs space-y-1">
          <p>初回参加で ¥10,000 付与</p>
          <p>単勝・複勝で馬券を買ってレースを楽しもう！</p>
        </div>
      </div>
    </div>
  )
}

// ── Phase badge ───────────────────────────────────────────────────────────────

function PhaseBadge({ phase, countdown, raceNumber }: {
  phase: string, countdown: number, raceNumber: number
}) {
  const config: Record<string, { label: string, cls: string }> = {
    waiting: { label: '待機中',       cls: 'bg-gray-700 text-gray-300' },
    betting: { label: '馬券受付中',   cls: 'bg-green-700 text-green-100 animate-pulse' },
    racing:  { label: 'レース中',     cls: 'bg-red-700 text-red-100 animate-pulse' },
    results: { label: 'レース終了',   cls: 'bg-blue-700 text-blue-100' },
  }
  const c = config[phase] ?? config.waiting
  const mm = String(Math.floor(countdown / 60)).padStart(2, '0')
  const ss = String(countdown % 60).padStart(2, '0')

  return (
    <div className="flex items-center gap-2 flex-wrap">
      {raceNumber > 0 && (
        <span className="bg-gray-700 text-gray-300 text-xs font-bold px-2 py-1 rounded">
          第{raceNumber}レース
        </span>
      )}
      <span className={`text-xs font-bold px-3 py-1 rounded ${c.cls}`}>
        {c.label}
      </span>
      {(phase === 'betting' || phase === 'results') && countdown > 0 && (
        <span className="text-yellow-300 font-mono text-sm">
          {phase === 'betting' ? `残り ${mm}:${ss}` : `次まで ${ss}秒`}
        </span>
      )}
    </div>
  )
}

// ── Main game page ────────────────────────────────────────────────────────────

export default function Home() {
  const [playerName, setPlayerName] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)

  const { game, user, connected, error, placeBet } = useGameSocket(playerName)

  // toast on payout
  useEffect(() => {
    if (user.lastPayout && user.lastPayout > 0) {
      setToast(`払い戻し ¥${user.lastPayout.toLocaleString()}`)
      const t = setTimeout(() => setToast(null), 3500)
      return () => clearTimeout(t)
    }
  }, [user.lastPayout])

  if (!playerName) {
    return <LoginScreen onJoin={setPlayerName} />
  }

  const isBetting = game.phase === 'betting'
  const isRacing  = game.phase === 'racing'
  const isResults = game.phase === 'results'

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      {/* header */}
      <header className="bg-gray-900 border-b border-gray-800 px-4 py-2">
        <div className="max-w-6xl mx-auto flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <span className="text-xl">🏇</span>
            <h1 className="font-bold text-base hidden sm:block">競馬ゲーム</h1>
            <PhaseBadge phase={game.phase} countdown={game.countdown} raceNumber={game.raceNumber} />
          </div>
          <div className="flex items-center gap-3">
            <span className="text-gray-400 text-xs">
              🟢 {game.online}人オンライン
            </span>
            <div className="text-right">
              <div className="text-xs text-gray-400">{user.displayName}</div>
              <div className="text-yellow-300 font-mono font-bold text-sm">
                ¥{user.balance.toLocaleString()}
              </div>
            </div>
            <div className={`w-2 h-2 rounded-full ${connected ? 'bg-green-400' : 'bg-red-400'}`} />
          </div>
        </div>
      </header>

      {/* error banner */}
      {error && (
        <div className="bg-red-900 text-red-200 text-center py-2 text-sm">{error}</div>
      )}

      {/* toast */}
      {toast && (
        <div className="fixed top-16 right-4 z-50 bg-green-700 text-white px-4 py-2 rounded-lg shadow-lg text-sm font-bold animate-bounce">
          {toast}
        </div>
      )}

      {/* main content */}
      <main className="max-w-6xl mx-auto p-3 space-y-3">

        {/* canvas */}
        <GameCanvas
          phase={game.phase}
          horses={game.horses}
          positions={game.positions}
          raceRanking={game.raceRanking}
          countdown={game.countdown}
        />

        {/* betting + results row */}
        {(isBetting || isRacing) && (
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-3">
            <div className="lg:col-span-3">
              <OddsTable
                horses={game.horses}
                winOdds={game.winOdds}
                showOdds={game.showOdds}
                pools={game.pools}
              />
            </div>
            <div className="lg:col-span-2">
              <BettingPanel
                horses={game.horses}
                winOdds={game.winOdds}
                showOdds={game.showOdds}
                user={user}
                onBet={placeBet}
                disabled={!isBetting}
              />
            </div>
          </div>
        )}

        {isResults && (
          <ResultsPanel
            ranking={game.raceRanking}
            horses={game.horses}
            winOdds={game.winOdds}
            showOdds={game.showOdds}
            payouts={game.payouts}
            myUserId={user.userId}
            countdown={game.countdown}
          />
        )}

        {/* leaderboard */}
        <Leaderboard leaderboard={game.leaderboard} myName={user.displayName} />

        {/* waiting state */}
        {game.phase === 'waiting' && (
          <div className="text-center text-gray-500 py-8">
            サーバーに接続中...
          </div>
        )}
      </main>
    </div>
  )
}

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
    <div className="min-h-screen flex items-center justify-center bg-gray-100 px-4">
      <div className="bg-white border border-gray-200 rounded-2xl p-8 w-full max-w-sm shadow-xl">
        <div className="text-center mb-6">
          <div className="text-5xl mb-3">🏇</div>
          <h1 className="text-gray-900 text-2xl font-bold tracking-tight">競馬ゲーム</h1>
          <p className="text-gray-500 text-sm mt-1">リアルタイム馬券ゲーム</p>
        </div>
        <div className="space-y-3">
          <input
            type="text" placeholder="プレイヤー名" value={name}
            onChange={e => setName(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && submit()}
            maxLength={20}
            className="w-full bg-gray-50 text-gray-900 rounded-xl px-4 py-3 border border-gray-300
              focus:border-yellow-500 focus:ring-1 focus:ring-yellow-400/30 outline-none
              text-center text-base placeholder:text-gray-400"
            autoFocus
          />
          <button onClick={submit} disabled={!name.trim()}
            className="w-full py-3 bg-yellow-400 text-black font-bold rounded-xl text-base
              hover:bg-yellow-300 active:scale-95 transition-all
              disabled:opacity-30 disabled:cursor-not-allowed">
            参加する
          </button>
        </div>
        <p className="text-center text-gray-400 text-xs mt-5">
          初回参加で ¥10,000 付与 · 単勝・複勝で勝負！
        </p>
      </div>
    </div>
  )
}

function PhaseBar({ phase, countdown, raceNumber }: { phase: string; countdown: number; raceNumber: number }) {
  const mm = String(Math.floor(countdown / 60)).padStart(2, '0')
  const ss = String(countdown % 60).padStart(2, '0')
  const phaseLabel: Record<string, { label: string; color: string }> = {
    waiting: { label: '待機中',     color: 'text-gray-500' },
    betting: { label: '馬券受付中', color: 'text-emerald-600' },
    racing:  { label: 'レース中',   color: 'text-red-600' },
    results: { label: '結果発表',   color: 'text-blue-600' },
  }
  const b = phaseLabel[phase] ?? phaseLabel.waiting
  return (
    <div className="flex items-center gap-2 flex-wrap">
      {raceNumber > 0 && (
        <span className="text-xs font-semibold text-gray-500">第{raceNumber}R</span>
      )}
      <span className={`text-xs font-bold ${b.color}`}>{b.label}</span>
      {phase === 'betting' && countdown > 0 && (
        <span className="text-yellow-600 font-mono text-sm font-bold tabular-nums">{mm}:{ss}</span>
      )}
      {phase === 'results' && countdown > 0 && (
        <span className="text-gray-500 text-xs">次まで {ss}秒</span>
      )}
    </div>
  )
}

const NIGHT_START_JST = 1
const NIGHT_END_JST   = 8

function isNightJST(): boolean {
  const jstHour = new Date(Date.now() + 9 * 3600 * 1000).getUTCHours()
  return jstHour >= NIGHT_START_JST && jstHour < NIGHT_END_JST
}

function NightScreen() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100 px-4">
      <div className="text-center">
        <div className="text-7xl mb-6">🌙</div>
        <h1 className="text-gray-900 text-2xl font-bold mb-2">おやすみ中</h1>
        <p className="text-gray-500 text-sm mb-1">現在サーバーはお休みしています</p>
        <p className="text-gray-400 text-xs">
          毎日 {NIGHT_END_JST}:00 〜 翌 {NIGHT_START_JST}:00（JST）に営業しています
        </p>
      </div>
    </div>
  )
}

function BrokeModal({ onReset, onDismiss }: { onReset: () => void; onDismiss: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm px-4">
      <div className="bg-white border border-gray-200 rounded-2xl p-7 w-full max-w-xs shadow-2xl text-center">
        <div className="text-4xl mb-3">💸</div>
        <h2 className="text-gray-900 text-lg font-bold mb-1">所持金が尽きました</h2>
        <p className="text-gray-500 text-sm mb-5">¥10,000 にリセットしますか？</p>
        <div className="flex gap-3">
          <button onClick={onDismiss}
            className="flex-1 py-2.5 rounded-xl bg-gray-100 text-gray-700 text-sm font-semibold
              hover:bg-gray-200 active:scale-95 transition-all">
            このまま続ける
          </button>
          <button onClick={onReset}
            className="flex-1 py-2.5 rounded-xl bg-yellow-400 text-black text-sm font-bold
              hover:bg-yellow-300 active:scale-95 transition-all">
            リセット
          </button>
        </div>
      </div>
    </div>
  )
}

const PLAYER_NAME_KEY = 'keiba_player_name'
const BROKE_THRESHOLD = 100

function getSavedPlayerName(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem(PLAYER_NAME_KEY)
}

function savePlayerName(name: string) {
  localStorage.setItem(PLAYER_NAME_KEY, name)
}

export default function Home() {
  const [playerName, setPlayerName] = useState<string | null>(null)
  const [toast, setToast] = useState<{ msg: string; type: 'win' | 'lose' } | null>(null)
  const [brokeAcknowledged, setBrokeAcknowledged] = useState(false)
  const [isNight, setIsNight] = useState(false)
  const { game, user, connected, error, restoreError, payoutSettled, placeBet, requestRestore } = useGameSocket(playerName)

  useEffect(() => {
    const check = () => setIsNight(isNightJST())
    check()
    const t = setInterval(check, 60_000)
    return () => clearInterval(t)
  }, [])
  const updateAvailable = useVersionCheck()

  useEffect(() => {
    if (window.location.search) history.replaceState(null, '', window.location.pathname)
    const saved = getSavedPlayerName()
    if (saved) setPlayerName(saved)
  }, [])

  useEffect(() => {
    if (user.balance >= BROKE_THRESHOLD) setBrokeAcknowledged(false)
  }, [user.balance])

  // 払い戻し確定後（payoutSettled）に残高チェック → 100円未満なら表示可能にする
  // 馬券を買っていないレースは results フェーズ開始時にチェック
  useEffect(() => {
    if (game.phase === 'results') setBrokeAcknowledged(false)
  }, [payoutSettled, game.phase])

  // 結果フェーズ中のみ表示
  const showBrokeModal = user.userId !== ''
    && user.balance < BROKE_THRESHOLD
    && !brokeAcknowledged
    && game.phase === 'results'

  const handleJoin = (name: string) => {
    savePlayerName(name)
    setPlayerName(name)
  }

  const handleChangeName = () => {
    localStorage.removeItem(PLAYER_NAME_KEY)
    setPlayerName(null)
  }

  const handleRestore = () => {
    requestRestore()
    setBrokeAcknowledged(true)
  }

  useEffect(() => {
    if (user.lastPayout == null) return
    setToast(user.lastPayout > 0
      ? { msg: `払い戻し ¥${user.lastPayout.toLocaleString()}`, type: 'win' }
      : { msg: 'ハズレ...', type: 'lose' }
    )
    const t = setTimeout(() => setToast(null), 3000)
    return () => clearTimeout(t)
  }, [user.lastPayout])

  if (isNight && !connected) return <NightScreen />
  if (!playerName) return <LoginScreen onJoin={handleJoin} />

  const isBetting = game.phase === 'betting'
  const isRacing  = game.phase === 'racing'
  const isResults = game.phase === 'results'

  return (
    <div className="min-h-screen bg-gray-100 text-gray-900">
      {showBrokeModal && <BrokeModal onReset={handleRestore} onDismiss={() => setBrokeAcknowledged(true)} />}
      <header className="sticky top-0 z-40 bg-gray-50/95 backdrop-blur border-b border-gray-200">
        <div className="max-w-5xl mx-auto px-3 py-2 flex items-center gap-3">
          <div className="flex-1 min-w-0">
            <PhaseBar phase={game.phase} countdown={game.countdown} raceNumber={game.raceNumber} />
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <span className="hidden sm:flex items-center gap-1 text-xs text-gray-500">
              <span className="w-1.5 h-1.5 rounded-full bg-green-500 inline-block" />
              {game.online}人
            </span>
            <div className="text-right">
              <button onClick={handleChangeName}
                className="text-gray-500 text-xs leading-none mb-0.5 hover:text-gray-800 transition-colors cursor-pointer">
                {user.displayName}
              </button>
              <div className="text-yellow-600 font-mono font-bold text-sm leading-none">¥{user.balance.toLocaleString()}</div>
            </div>
            <div className={`w-2 h-2 rounded-full shrink-0 ${connected ? 'bg-green-500' : 'bg-red-500'}`} />
          </div>
        </div>
      </header>
      {error && (
        <div className="bg-red-50 border-b border-red-200 text-red-700 text-center py-2 text-sm px-4">{error}</div>
      )}
      {updateAvailable && (
        <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3
          bg-blue-600 text-white text-sm font-medium px-5 py-3 rounded-xl shadow-xl">
          <span>新しいバージョンがあります</span>
          <button onClick={() => { window.location.href = window.location.pathname + '?_v=' + Date.now() }}
            className="bg-white text-blue-700 px-3 py-1 rounded-lg text-xs font-bold hover:bg-blue-50 active:scale-95 transition-all">
            更新
          </button>
        </div>
      )}
      {toast && (
        <div className={`fixed top-14 left-1/2 -translate-x-1/2 z-50 px-5 py-2.5 rounded-xl shadow-xl text-sm font-bold
          ${toast.type === 'win' ? 'bg-emerald-600 text-white' : 'bg-gray-800 text-gray-200'}`}>
          {toast.msg}
        </div>
      )}
      {restoreError && (
        <div className="fixed top-14 left-1/2 -translate-x-1/2 z-50 px-5 py-2.5 rounded-xl shadow-xl text-sm font-bold bg-red-700 text-white">
          {restoreError}
        </div>
      )}
      <main className="max-w-5xl mx-auto p-3 space-y-3">
        <div className="rounded-xl overflow-hidden ring-1 ring-black/5 shadow-xl">
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

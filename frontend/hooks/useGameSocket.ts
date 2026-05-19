'use client'

import { useEffect, useRef, useCallback, useState } from 'react'
import type { GameState, UserState, Phase, Pools } from '@/types/game'

const DEFAULT_GAME: GameState = {
  phase: 'waiting',
  raceNumber: 0,
  countdown: 0,
  horses: [],
  positions: {},
  raceRanking: [],
  winOdds: {},
  showOdds: {},
  pools: { win: {}, show: {}, win_total: 0, show_total: 0 },
  payouts: [],
  leaderboard: [],
  online: 0,
}

const DEFAULT_USER: UserState = {
  userId: '',
  displayName: '',
  balance: 0,
  myBets: [],
  lastPayout: null,
}

function getOrCreateSessionId(): string {
  if (typeof window === 'undefined') return ''
  let id = localStorage.getItem('keiba_session_id')
  if (!id) {
    id = crypto.randomUUID()
    localStorage.setItem('keiba_session_id', id)
  }
  return id
}

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws'
const RECONNECT_DELAYS = [3000, 5000, 10000, 20000, 30000] // ms

export function useGameSocket(playerName: string | null) {
  const wsRef        = useRef<WebSocket | null>(null)
  const retryRef     = useRef<ReturnType<typeof setTimeout> | null>(null)
  const retryCount   = useRef(0)
  const destroyed    = useRef(false)
  const lastRaceRef  = useRef(0)

  const [game, setGame]                 = useState<GameState>(DEFAULT_GAME)
  const [user, setUser]                 = useState<UserState>(DEFAULT_USER)
  const [connected, setConnected]       = useState(false)
  const [error, setError]               = useState<string | null>(null)
  const [restoreError, setRestoreError] = useState<string | null>(null)
  const [payoutSettled, setPayoutSettled] = useState(false)

  const send = useCallback((msg: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg))
    }
  }, [])

  useEffect(() => {
    if (!playerName) return
    destroyed.current  = false
    retryCount.current = 0

    const sessionId = getOrCreateSessionId()

    function connect() {
      if (destroyed.current) return

      const ws = new WebSocket(WS_URL)
      wsRef.current = ws

      ws.onopen = () => {
        retryCount.current = 0
        setConnected(true)
        setError(null)
        ws.send(JSON.stringify({ type: 'join', name: playerName, session_id: sessionId }))
      }

      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data)

        switch (msg.type) {
          case 'joined':
            setUser(u => ({
              ...u,
              userId: msg.user_id,
              displayName: msg.display_name,
              balance: msg.balance,
              myBets: [],
              lastPayout: null,
            }))
            setGame(g => ({ ...g, online: msg.online }))
            break

          case 'game_state':
            setGame(g => ({
              ...g,
              phase: msg.phase as Phase,
              raceNumber: msg.race_number ?? g.raceNumber,
              countdown: msg.countdown ?? 0,
              horses: msg.horses ?? g.horses,
              winOdds: parseOdds(msg.win_odds),
              showOdds: parseOdds(msg.show_odds),
              pools: msg.pools ?? g.pools,
              leaderboard: msg.leaderboard ?? g.leaderboard,
              positions: {},
              raceRanking: [],
            }))
            // レース番号が変わったときだけ馬券・払い戻し状態をリセット
            if (msg.race_number && msg.race_number !== lastRaceRef.current) {
              lastRaceRef.current = msg.race_number
              setUser(u => ({ ...u, myBets: [], lastPayout: null }))
              setPayoutSettled(false)
            }
            break

          case 'race_update':
            setGame(g => ({
              ...g,
              phase: 'racing',
              positions: msg.positions ?? g.positions,
            }))
            break

          case 'results':
            setGame(g => ({
              ...g,
              phase: 'results',
              raceNumber: msg.race_number ?? g.raceNumber,
              raceRanking: msg.ranking ?? [],
              horses: msg.horses ?? g.horses,
              winOdds: parseOdds(msg.win_odds),
              showOdds: parseOdds(msg.show_odds),
              payouts: msg.payouts ?? [],
              leaderboard: msg.leaderboard ?? g.leaderboard,
            }))
            break

          case 'results_countdown':
            setGame(g => ({ ...g, countdown: msg.countdown }))
            break

          case 'odds_update':
            setGame(g => ({
              ...g,
              winOdds: parseOdds(msg.win_odds),
              showOdds: parseOdds(msg.show_odds),
              pools: msg.pools ?? g.pools,
            }))
            break

          case 'online_update':
            setGame(g => ({ ...g, online: msg.online }))
            break

          case 'bet_result':
            if (msg.ok) {
              setUser(u => ({
                ...u,
                balance: msg.balance,
                myBets: [...u.myBets, { bet_type: msg.bet_type, horse: msg.horse, amount: msg.amount }],
              }))
            }
            break

          case 'payout_notify':
            setUser(u => ({ ...u, balance: msg.balance, lastPayout: msg.payout }))
            setPayoutSettled(true)
            break

          case 'restored':
            setUser(u => ({ ...u, balance: msg.balance }))
            break

          case 'restore_denied':
            setRestoreError(msg.error ?? 'リセットできません')
            setTimeout(() => setRestoreError(null), 3000)
            break

          case 'my_bets':
            setUser(u => ({ ...u, myBets: msg.bets ?? [] }))
            break
        }
      }

      ws.onerror = () => {}

      ws.onclose = () => {
        if (destroyed.current) return
        setConnected(false)
        setUser(DEFAULT_USER)

        const delay = RECONNECT_DELAYS[Math.min(retryCount.current, RECONNECT_DELAYS.length - 1)]
        const sec   = Math.round(delay / 1000)
        setError(`再接続中... (${sec}秒後)`)
        retryCount.current += 1
        retryRef.current = setTimeout(connect, delay)
      }
    }

    connect()

    return () => {
      destroyed.current = true
      if (retryRef.current) clearTimeout(retryRef.current)
      wsRef.current?.close()
    }
  }, [playerName])

  const placeBet = useCallback((betType: 'win' | 'show', horse: number, amount: number) => {
    send({ type: 'bet', bet_type: betType, horse, amount })
  }, [send])

  const refreshBets = useCallback(() => {
    send({ type: 'get_bets' })
  }, [send])

  const requestRestore = useCallback(() => {
    send({ type: 'restore_request' })
  }, [send])

  return { game, user, connected, error, restoreError, payoutSettled, placeBet, refreshBets, requestRestore }
}

function parseOdds(raw: Record<string, number> | undefined): Record<string, number> {
  if (!raw) return {}
  return Object.fromEntries(
    Object.entries(raw).map(([k, v]) => [k, Number(v)])
  )
}

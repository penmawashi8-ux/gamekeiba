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

const BUILD_WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws'
const RECONNECT_DELAYS = [3000, 5000, 10000, 20000, 30000] // ms
// 何回失敗したら「繋がらない」と認めて接続先を画面に出すか。
// 再試行自体はこの後も続ける（サーバーが復帰したら自動で繋がる）。
//
// Render の無課金プランはインスタンスの復帰に50〜60秒かかることがある。
// RECONNECT_DELAYS の累計が復帰時間を十分に超えてから「接続できません」と
// 言わないと、正常な起動待ちを失敗と誤報する。
// 累計: 3+5+10+20+30+30 = 98秒
const ATTEMPTS_BEFORE_DIAGNOSIS = 6

export type ConnPhase = 'connecting' | 'waking' | 'connected' | 'retrying' | 'unreachable' | 'misconfigured'

/** 接続先を実行時に解決する。取れなければビルド時の値を使う。 */
async function resolveWsUrl(): Promise<string> {
  try {
    const res = await fetch('/api/config', { cache: 'no-store' })
    if (res.ok) {
      const json = await res.json()
      if (typeof json.wsUrl === 'string' && json.wsUrl) return json.wsUrl
    }
  } catch {
    // 設定APIが無い環境（静的書き出し等）ではビルド時の値で動かす
  }
  return BUILD_WS_URL
}

/** 接続先が明らかに繋がらない設定なら、その理由を返す。 */
function configProblem(wsUrl: string): string | null {
  let u: URL
  try {
    u = new URL(wsUrl)
  } catch {
    return `接続先の設定が不正です（${wsUrl || '未設定'}）`
  }
  if (typeof location === 'undefined') return null
  if (location.protocol !== 'https:') return null
  // https のページから ws:// は混在コンテンツとしてブラウザに遮断される。
  // 黙って再接続し続けると原因が分からないので、ここで止めて理由を出す。
  if (u.protocol === 'ws:') return `接続先が ws:// のため遮断されます（${wsUrl}）`
  if (/^(localhost|127\.0\.0\.1|\[::1\])$/.test(u.hostname)) {
    return `接続先が localhost のままです（${wsUrl}）`
  }
  return null
}

/** WebSocket URL から /health の URL を組み立てる。 */
function healthUrlFor(wsUrl: string): string | null {
  try {
    const u = new URL(wsUrl)
    u.protocol = u.protocol === 'wss:' ? 'https:' : 'http:'
    u.pathname = `${u.pathname.replace(/\/ws$/, '')}/health`.replace(/\/{2,}/g, '/')
    u.search = ''
    return u.toString()
  } catch {
    return null
  }
}

/**
 * バックエンドを HTTP で起こす。
 * Render の無課金プランは無通信15分でインスタンスが停止し、復帰に30〜60秒かかる。
 * WebSocket のハンドシェイクだけでは復帰前に失敗して「再接続中」を延々と出すため、
 * 先に HTTP を投げて起動させる。CORS 設定に依存しないよう no-cors で投げ、
 * 結果は見ない（起こすことだけが目的）。
 */
async function wakeBackend(healthUrl: string): Promise<void> {
  try {
    await fetch(healthUrl, { cache: 'no-store', mode: 'no-cors' })
  } catch {
    // 起こせなくても WebSocket は試す
  }
}

export function useGameSocket(playerName: string | null) {
  const wsRef        = useRef<WebSocket | null>(null)
  const retryRef     = useRef<ReturnType<typeof setTimeout> | null>(null)
  const retryCount   = useRef(0)
  const destroyed    = useRef(false)
  const lastRaceRef  = useRef(0)
  // 一度でも接続できたか。起動待ちと切断後の再接続を言い分けるために使う。
  const everConnected = useRef(false)

  const [game, setGame]                 = useState<GameState>(DEFAULT_GAME)
  const [user, setUser]                 = useState<UserState>(DEFAULT_USER)
  const [connected, setConnected]       = useState(false)
  const [error, setError]               = useState<string | null>(null)
  const [phase, setPhase]               = useState<ConnPhase>('connecting')
  const [wsUrl, setWsUrl]               = useState<string>('')
  const [attempts, setAttempts]         = useState(0)
  const [retryNonce, setRetryNonce]     = useState(0)
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
    setPhase('connecting')
    setAttempts(0)

    async function connect(url: string) {
      if (destroyed.current) return

      // 停止中のインスタンスを毎回先に起こしてから繋ぎにいく。
      // Render は起動が終わるまでこのリクエストを保持するため、
      //   ・起きていれば100ms程度で返り、ほぼ待たされない
      //   ・停止していれば起動完了まで待たされ、その直後に WebSocket が通る
      // WebSocket を先に投げると復帰前に弾かれ、再接続ループに入ってしまう。
      const health = healthUrlFor(url)
      if (health) {
        setPhase('waking')
        await wakeBackend(health)
        if (destroyed.current) return
      }

      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        retryCount.current = 0
        everConnected.current = true
        setConnected(true)
        setError(null)
        setPhase('connected')
        setAttempts(0)
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
              showOdds: parseShowOdds(msg.show_odds),
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
              showOdds: parseShowOdds(msg.show_odds),
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
              showOdds: parseShowOdds(msg.show_odds),
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

        retryCount.current += 1
        setAttempts(retryCount.current)

        const delay = RECONNECT_DELAYS[Math.min(retryCount.current - 1, RECONNECT_DELAYS.length - 1)]
        const sec   = Math.round(delay / 1000)

        if (retryCount.current >= ATTEMPTS_BEFORE_DIAGNOSIS) {
          // 何度やっても繋がらないなら、接続先を隠さず出す。
          // 「ずっと再接続中」だけでは原因が分からないため。
          setPhase('unreachable')
          setError(`サーバーに接続できません（接続先: ${url}）`)
        } else {
          setPhase('retrying')
          // 一度も繋がっていないなら「切断された」のではなく「まだ起きていない」。
          // 停止中のインスタンスの起動待ちなので、そう書いたほうが正確。
          setError(everConnected.current
            ? `再接続中... (${sec}秒後)`
            : `サーバーを起動しています… (${sec}秒後に再試行)`)
        }
        retryRef.current = setTimeout(() => connect(url), delay)
      }
    }

    let cancelled = false
    void (async () => {
      const url = await resolveWsUrl()
      if (cancelled || destroyed.current) return
      setWsUrl(url)

      const problem = configProblem(url)
      if (problem) {
        // 設定が原因なら何度再接続しても無駄なので、繰り返さず理由を出す
        setPhase('misconfigured')
        setError(problem)
        return
      }
      void connect(url)
    })()

    return () => {
      cancelled = true
      destroyed.current = true
      if (retryRef.current) clearTimeout(retryRef.current)
      wsRef.current?.close()
      // onclose は destroyed.current を見て早期 return するので、ここで落とす。
      // これがないと夜間に切り替わったとき connected が true のままになり、
      // 「おやすみ中」画面に切り替わらない
      setConnected(false)
    }
  }, [playerName, retryNonce])

  const placeBet = useCallback((betType: 'win' | 'show', horse: number, amount: number) => {
    send({ type: 'bet', bet_type: betType, horse, amount })
  }, [send])

  const refreshBets = useCallback(() => {
    send({ type: 'get_bets' })
  }, [send])

  const requestRestore = useCallback(() => {
    send({ type: 'restore_request' })
  }, [send])

  // 手動再試行。待ち時間を飛ばして即座に繋ぎ直す。
  const retry = useCallback(() => {
    if (retryRef.current) clearTimeout(retryRef.current)
    wsRef.current?.close()
    retryCount.current = 0
    setRetryNonce(n => n + 1)
  }, [])

  return {
    game, user, connected, error, restoreError, payoutSettled,
    phase, wsUrl, attempts, retry,
    placeBet, refreshBets, requestRestore,
  }
}

function parseOdds(raw: Record<string, number> | undefined): Record<string, number> {
  if (!raw) return {}
  return Object.fromEntries(
    Object.entries(raw).map(([k, v]) => [k, Number(v)])
  )
}

function parseShowOdds(raw: unknown): Record<string, [number, number]> {
  if (!raw || typeof raw !== 'object') return {}
  return Object.fromEntries(
    Object.entries(raw as Record<string, unknown>)
      .filter(([, v]) => Array.isArray(v) && (v as unknown[]).length >= 2)
      .map(([k, v]) => [k, [Number((v as number[])[0]), Number((v as number[])[1])] as [number, number]])
  )
}

export type Phase = 'waiting' | 'betting' | 'racing' | 'results'

export interface HorseInfo {
  number: number
  name: string
  color: string
  strength: number
  stars: string
  running_style: string
}

export interface HorsePosition {
  progress: number   // 0.0 ~ 1.0
  finished: boolean
  rank: number | null
  anim_t: number
}

export interface Bet {
  bet_type: 'win' | 'show'
  horse: number
  amount: number
}

export interface PayoutInfo {
  user_id: string
  display_name: string
  bet_type: string
  horse: number
  bet_amount: number
  payout_amount: number
  odds: number
}

export interface Pools {
  win: Record<string, number>
  show: Record<string, number>
  win_total: number
  show_total: number
}

export interface GameState {
  phase: Phase
  raceNumber: number
  countdown: number
  horses: HorseInfo[]
  positions: Record<string, HorsePosition>
  raceRanking: number[]
  winOdds: Record<string, number>
  showOdds: Record<string, number>
  pools: Pools
  payouts: PayoutInfo[]
  leaderboard: [string, number][]
  online: number
}

export interface UserState {
  userId: string
  displayName: string
  balance: number
  myBets: Bet[]
  lastPayout: number | null
}

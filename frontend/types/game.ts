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
  // anim_t はサーバーから送っていた時期があるが、脚の動きは GameCanvas が
  // 自前のタイマーで進めており使っていなかったため廃止した。
}

export interface Bet {
  bet_type: 'win' | 'show'
  horse: number
  amount: number
}

export interface PayoutInfo {
  // 他人に見せてよい識別子（user_id はセッションIDなので配られない）
  public_id?: string
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
  showOdds: Record<string, [number, number]>
  pools: Pools
  payouts: PayoutInfo[]
  // 複勝の確定オッズ {馬番: 倍率}。payouts には CPU が載らないので別に受け取る
  showPayoutOdds: Record<string, number>
  leaderboard: RankingRow[]
  // 今接続している人だけの残高ランキング
  onlineLeaderboard: RankingRow[]
  online: number
  maintenance: Maintenance
}

// [表示名, 残高, public_id]。public_id は古いサーバーだと付かない
export type RankingRow = [string, number, string?]

export interface Maintenance {
  at: number | null     // 開始予定（ミリ秒）。null なら予定なし
  active: boolean       // 停止中
}

export interface UserState {
  userId: string
  // ランキングや払い戻し一覧で自分の行を見分ける識別子（名前は重複しうる）
  publicId: string
  displayName: string
  balance: number
  myBets: Bet[]
  lastPayout: number | null
}

// 「ボドゲ広場の中（iframe）で遊んでいた人」と「このサイトを直接開いた人」を
// 同じ人として扱うための引き継ぎ。
//
// このゲームは boardgamecat.com のページに iframe で埋め込まれている。
// iframe は gamekeiba.boardgamecat.com、親は boardgamecat.com で、
// 同じドメインの下だが別オリジンである。ブラウザによっては埋め込みの
// 保存領域を親サイトごとに切り分けるため、iframe で書いた localStorage が
// 同じURLを直接開いたタブから見えないことがある。
// 実際に「別タブで大きく開く」を押すと名前の入力に戻り、所持金も消えて見える、
// という報告が出た。
//
// そこで保存領域の共有に頼らず、親ページ経由でURLに載せて渡す。
//   1) iframe 側（このファイル）が自分の識別子を親へ postMessage で知らせる
//   2) 親は「別タブで大きく開く」のリンクに ?sid=...&name=... を付ける
//   3) 新しいタブはそれを読んで localStorage に入れてから接続する
// URLに載るのはサーバーが発行した不透明な識別子と表示名だけ。

const SESSION_KEY = 'keiba_session_id'
const NAME_KEY = 'keiba_player_name'

/** 親ページへ知らせるときの合図。ボドゲ広場側と揃えること。 */
const TELL = 'bodoge:session'
/** 親ページから「今だれ？」と聞かれるときの合図。 */
const ASK = 'bodoge:whoami'

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    // プライベートウィンドウ等では例外が出る
    return null
  }
}

function write(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    // 保存できなくても、このタブで遊ぶぶんには支障がない
  }
}

export function getSessionId(): string {
  if (typeof window === 'undefined') return ''
  let id = read(SESSION_KEY)
  if (!id) {
    id = crypto.randomUUID()
    write(SESSION_KEY, id)
  }
  return id
}

export function getPlayerName(): string | null {
  if (typeof window === 'undefined') return null
  return read(NAME_KEY)
}

export function savePlayerName(name: string): void {
  if (typeof window === 'undefined') return
  write(NAME_KEY, name)
}

export function forgetPlayerName(): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.removeItem(NAME_KEY)
  } catch {
    // 消せなくても playerName を null にすれば入力画面には戻る
  }
}

/**
 * URL に載って来た識別子を受け取る。
 *
 * 親ページから渡された時点でそちらが本人なので、このタブに前の識別子が
 * あっても上書きする。保存領域が共有されているブラウザでは同じ値が来るので
 * 何も変わらない。共有されていないブラウザでは、これが唯一の引き継ぎ経路。
 *
 * 呼ぶのは location.search を消す前。消してから読んでも何も無い。
 */
export function adoptFromUrl(): void {
  if (typeof window === 'undefined') return
  const q = new URLSearchParams(window.location.search)
  const sid = q.get('sid')
  const name = q.get('name')
  // サーバーが発行するのは UUID。形が違うものは受け取らない
  if (sid && /^[0-9a-f-]{8,64}$/i.test(sid)) write(SESSION_KEY, sid)
  if (name) write(NAME_KEY, name.slice(0, 20))
}

function inIframe(): boolean {
  try {
    return window.parent !== window
  } catch {
    return true
  }
}

/**
 * 親ページ（ボドゲ広場）へ自分が誰かを知らせる。
 * 埋め込みで動いていないときは何もしない。
 *
 * 宛先オリジンは絞らない（'*'）。親がどのオリジンかは iframe からは
 * 読めず、ボドゲ広場は boardgamecat.com と www 付きの両方で開けるため。
 * 渡すのはサーバー発行の識別子と表示名だけで、
 * 親の受け取り側はこちらのオリジンを確認してから使う。
 */
export function tellParent(): void {
  if (typeof window === 'undefined' || !inIframe()) return
  const sessionId = read(SESSION_KEY)
  if (!sessionId) return
  try {
    window.parent.postMessage({ type: TELL, sessionId, name: read(NAME_KEY) ?? '' }, '*')
  } catch {
    // 親に届かなくても遊ぶぶんには支障がない
  }
}

/**
 * 親から「今だれ？」と聞かれたら答える、を仕掛ける。
 *
 * iframe の読み込みが終わった合図は親側のほうが確実に取れるので、
 * 親から聞いてもらう経路も用意しておく（こちらから一方的に送るだけだと、
 * 親が聞く用意を整える前に送ってしまう可能性がある）。
 *
 * 戻り値は後片付けの関数。
 */
export function answerParent(): () => void {
  if (typeof window === 'undefined') return () => {}
  const onMessage = (ev: MessageEvent) => {
    if (ev.data && typeof ev.data === 'object' && ev.data.type === ASK) tellParent()
  }
  window.addEventListener('message', onMessage)
  return () => window.removeEventListener('message', onMessage)
}

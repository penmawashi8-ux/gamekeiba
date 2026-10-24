import { useEffect, useState } from 'react'

const MY_BUILD_ID = process.env.BUILD_ID ?? 'dev'

// 新しいバージョンが出ていないかの確認間隔。
//
// 以前は開いているタブすべてが60秒おきに /api/version を叩いていて、
// 同時に数十人いると Vercel の無料枠（CDNリクエスト 月100万）を使い切りかけた。
// 26人 × 60回/時 × 24時間 × 30日 ≒ 112万回。
// 更新はめったに出ないので、間隔を大きく空け、見えていないタブでは確認しない。
const CHECK_INTERVAL_MS = 30 * 60_000

export function useVersionCheck(): boolean {
  const [updateAvailable, setUpdateAvailable] = useState(false)

  useEffect(() => {
    if (MY_BUILD_ID === 'dev') return

    let last = Date.now()
    let found = false

    const check = async () => {
      if (found || document.visibilityState !== 'visible') return
      last = Date.now()
      try {
        const res = await fetch('/api/version', { cache: 'no-store' })
        if (!res.ok) return
        const { buildId } = await res.json()
        if (buildId && buildId !== MY_BUILD_ID) {
          found = true
          setUpdateAvailable(true)
        }
      } catch {
        // ignore network errors
      }
    }

    // バックグラウンドから戻ってきたときに、前回から間隔以上空いていれば確認する
    const onVisible = () => {
      if (Date.now() - last >= CHECK_INTERVAL_MS) void check()
    }

    const timer = setInterval(check, CHECK_INTERVAL_MS)
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [])

  return updateAvailable
}

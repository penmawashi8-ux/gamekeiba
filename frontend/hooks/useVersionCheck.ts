import { useEffect, useState } from 'react'

const MY_BUILD_ID = process.env.BUILD_ID ?? 'dev'

export function useVersionCheck(): boolean {
  const [updateAvailable, setUpdateAvailable] = useState(false)

  useEffect(() => {
    if (MY_BUILD_ID === 'dev') return

    const check = async () => {
      try {
        const res = await fetch('/api/version', { cache: 'no-store' })
        if (!res.ok) return
        const { buildId } = await res.json()
        if (buildId && buildId !== MY_BUILD_ID) {
          setUpdateAvailable(true)
        }
      } catch {
        // ignore network errors
      }
    }

    const timer = setInterval(check, 60_000)
    const initial = setTimeout(check, 15_000)
    return () => { clearInterval(timer); clearTimeout(initial) }
  }, [])

  return updateAvailable
}

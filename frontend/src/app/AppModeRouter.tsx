import { useEffect, useState } from 'react'
import AppShell from './AppShell'
import RankingApp from '../features/ranking/RankingApp'
import { requestBootHealth } from './boot/bootHealth'
import { applyThemeFromBootHealth, commitBootHealth, type AppBootState } from './boot/bootTheme'

export default function AppModeRouter() {
  const [bootState, setBootState] = useState<AppBootState>({
    mode: 'browse',
    loading: true,
    error: null,
  })

  useEffect(() => {
    const request = requestBootHealth()
    request.promise
      .then((bootHealth) => {
        commitBootHealth(bootHealth, applyThemeFromBootHealth, setBootState)
      })
      .catch((error) => {
        const message = error instanceof Error ? error.message : 'health check failed'
        setBootState({
          mode: 'browse',
          loading: false,
          error: message,
        })
      })
    return () => request.abort()
  }, [])

  if (bootState.loading) {
    return <div className="boot-loading">Loading Lenslet...</div>
  }

  if (bootState.mode === 'ranking') {
    return <RankingApp />
  }

  return (
    <>
      {bootState.error ? (
        <div className="boot-warning" role="status">
          Health check failed; using browse mode fallback. ({bootState.error})
        </div>
      ) : null}
      <AppShell />
    </>
  )
}

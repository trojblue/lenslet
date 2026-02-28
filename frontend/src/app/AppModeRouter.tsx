import { useEffect, useState } from 'react'
import AppShell from './AppShell'
import RankingApp from '../features/ranking/RankingApp'
import { BASE } from '../api/base'
import { fetchJSON } from '../lib/fetcher'
import type { HealthResponse } from '../lib/types'
import { deriveAppModeFromHealth, type AppMode } from './model/appMode'

type BootState = {
  mode: AppMode
  loading: boolean
  error: string | null
}

export default function AppModeRouter() {
  const [bootState, setBootState] = useState<BootState>({
    mode: 'browse',
    loading: true,
    error: null,
  })

  useEffect(() => {
    const request = fetchJSON<HealthResponse>(`${BASE}/health`)
    request.promise
      .then((health) => {
        setBootState({
          mode: deriveAppModeFromHealth(health),
          loading: false,
          error: null,
        })
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

import { Suspense, lazy, useEffect, useState } from 'react'
import AppShell from './AppShell'
import { requestBootHealth } from './boot/bootHealth'
import { applyThemeFromBootHealth, commitBootHealth, type AppBootState } from './boot/bootTheme'

const RankingApp = lazy(() => import('../features/ranking/RankingApp'))

export default function AppModeRouter() {
  const [bootState, setBootState] = useState<AppBootState>({
    mode: 'browse',
    healthMode: null,
    workspaceId: null,
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
          healthMode: null,
          workspaceId: null,
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
    return (
      <Suspense fallback={<div className="boot-loading">Loading Lenslet...</div>}>
        <RankingApp />
      </Suspense>
    )
  }

  return (
    <>
      {bootState.error ? (
        <div className="boot-warning" role="status">
          Health check failed; using browse mode fallback. ({bootState.error})
        </div>
      ) : null}
      <AppShell
        themeHealthMode={bootState.healthMode}
        themeWorkspaceId={bootState.workspaceId}
      />
    </>
  )
}

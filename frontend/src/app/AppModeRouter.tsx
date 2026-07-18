import { Suspense, lazy, useEffect, useState } from 'react'
import AppShell from './AppShell'
import { requestBootHealth } from './boot/bootHealth'
import { applyThemeFromBootHealth, commitBootHealth, type AppBootState } from './boot/bootTheme'
import BootShell from '../shared/ui/BootShell'
import { useDelayedVisibility } from '../shared/hooks/useDelayedVisibility'
import { BOOT_LOADING_COPY_DELAY_MS } from './model/lazySurface'

const loadRankingApp = () => import('../features/ranking/RankingApp')
const RankingApp = lazy(loadRankingApp)

export default function AppModeRouter() {
  const [bootStartedAtMs] = useState(() => Date.now())
  const [bootState, setBootState] = useState<AppBootState>({
    mode: 'browse',
    healthMode: null,
    workspaceId: null,
    loading: true,
    error: null,
  })
  const [rankingModuleReady, setRankingModuleReady] = useState(false)

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

  useEffect(() => {
    if (bootState.loading || bootState.mode !== 'ranking') return
    let active = true
    void loadRankingApp().then(() => {
      if (active) setRankingModuleReady(true)
    })
    return () => {
      active = false
    }
  }, [bootState.loading, bootState.mode])

  const bootPending = bootState.loading || (bootState.mode === 'ranking' && !rankingModuleReady)
  const showBootLoadingCopy = useDelayedVisibility(
    bootPending,
    BOOT_LOADING_COPY_DELAY_MS,
    bootStartedAtMs,
  )

  if (bootState.loading) {
    return <BootShell showLoadingCopy={showBootLoadingCopy} />
  }

  if (bootState.mode === 'ranking') {
    return (
      <Suspense fallback={<BootShell showLoadingCopy={showBootLoadingCopy} />}>
        <RankingApp bootStartedAtMs={bootStartedAtMs} />
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

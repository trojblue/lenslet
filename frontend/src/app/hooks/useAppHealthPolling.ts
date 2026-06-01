import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { HealthMode, HealthResponse } from '../../lib/types'
import {
  indexingEquals,
  nextIndexingPollDelayMs,
  normalizeHealthIndexing,
  shouldContinueIndexingPoll,
  type HealthIndexing,
} from './healthIndexing'

const HEALTH_POLL_RUNNING_MS = 1_200
const HEALTH_POLL_RETRY_MS = 3_000
const REFRESH_UNAVAILABLE_FALLBACK = 'Refresh unavailable in current mode'

type RefreshCapability = {
  enabled: boolean
  note: string | null
}

export type AppHealthPollingState = {
  persistenceEnabled: boolean
  healthMode: HealthMode | null
  refreshEnabled: boolean
  refreshDisabledReason: string | null
  indexing: HealthIndexing | null
}

function normalizeHealthRefresh(health: HealthResponse | null | undefined): RefreshCapability {
  const refresh = health?.refresh
  if (refresh && typeof refresh.enabled === 'boolean') {
    if (refresh.enabled) return { enabled: true, note: null }
    const note = typeof refresh.note === 'string' && refresh.note.trim()
      ? refresh.note
      : REFRESH_UNAVAILABLE_FALLBACK
    return { enabled: false, note }
  }

  const mode = health?.mode ?? null
  if (mode === 'table' && health?.can_write === true) {
    return { enabled: true, note: null }
  }
  if (mode === 'dataset' || mode === 'table') {
    return { enabled: false, note: REFRESH_UNAVAILABLE_FALLBACK }
  }
  return { enabled: true, note: null }
}

export function useAppHealthPolling(): AppHealthPollingState {
  const [persistenceEnabled, setPersistenceEnabled] = useState(true)
  const [healthMode, setHealthMode] = useState<HealthMode | null>(null)
  const [refreshEnabled, setRefreshEnabled] = useState(true)
  const [refreshDisabledReason, setRefreshDisabledReason] = useState<string | null>(null)
  const [indexing, setIndexing] = useState<HealthIndexing | null>(null)

  useEffect(() => {
    let cancelled = false
    let timerId: number | null = null

    const clearPollTimer = () => {
      if (timerId == null) return
      window.clearTimeout(timerId)
      timerId = null
    }

    const schedulePoll = (ms: number) => {
      clearPollTimer()
      timerId = window.setTimeout(() => {
        void pollHealth()
      }, ms)
    }

    const pollHealth = async () => {
      try {
        const health = await api.getHealth()
        if (cancelled) return

        setPersistenceEnabled(health?.labels?.enabled ?? true)
        setHealthMode(health?.mode ?? null)
        const refreshCapability = normalizeHealthRefresh(health)
        setRefreshEnabled(refreshCapability.enabled)
        setRefreshDisabledReason(refreshCapability.note)
        const nextIndexing = normalizeHealthIndexing(health?.indexing)
        setIndexing((prev) => (indexingEquals(prev, nextIndexing) ? prev : nextIndexing))

        if (shouldContinueIndexingPoll(nextIndexing)) {
          schedulePoll(nextIndexingPollDelayMs(nextIndexing, HEALTH_POLL_RUNNING_MS, HEALTH_POLL_RETRY_MS))
        }
      } catch {
        if (cancelled) return
        schedulePoll(HEALTH_POLL_RETRY_MS)
      }
    }

    void pollHealth()
    return () => {
      cancelled = true
      clearPollTimer()
    }
  }, [])

  return {
    persistenceEnabled,
    healthMode,
    refreshEnabled,
    refreshDisabledReason,
    indexing,
  }
}

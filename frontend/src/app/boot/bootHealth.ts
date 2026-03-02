import { BASE } from '../../api/base'
import { fetchJSON } from '../../lib/fetcher'
import type { HealthMode, HealthResponse } from '../../lib/types'
import { deriveAppModeFromHealth, type AppMode } from '../model/appMode'

export type BootHealthState = {
  mode: AppMode
  healthMode: HealthMode | null
  workspaceId: string | null
  error: string | null
}

type AbortableRequest<T> = {
  promise: Promise<T>
  abort: () => void
}

function normalizeWorkspaceId(workspaceId: unknown): string | null {
  if (typeof workspaceId !== 'string') return null
  const trimmed = workspaceId.trim()
  return trimmed.length > 0 ? trimmed : null
}

function normalizeErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message.trim()) {
    return error.message
  }
  if (typeof error === 'string' && error.trim()) {
    return error
  }
  return 'health check failed'
}

export function parseBootHealth(health: HealthResponse | null | undefined): Omit<BootHealthState, 'error'> {
  return {
    mode: deriveAppModeFromHealth(health),
    healthMode: health?.mode ?? null,
    workspaceId: normalizeWorkspaceId(health?.workspace_id),
  }
}

export function buildBootHealthFailure(error: unknown): BootHealthState {
  return {
    mode: 'browse',
    healthMode: null,
    workspaceId: null,
    error: normalizeErrorMessage(error),
  }
}

export function requestBootHealth(): AbortableRequest<BootHealthState> {
  const request = fetchJSON<HealthResponse>(`${BASE}/health`)
  return {
    abort: request.abort,
    promise: request.promise
      .then((health) => ({
        ...parseBootHealth(health),
        error: null,
      }))
      .catch((error) => buildBootHealthFailure(error)),
  }
}

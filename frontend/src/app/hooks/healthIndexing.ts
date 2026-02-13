import type { HealthResponse } from '../../lib/types'

export type HealthIndexing = NonNullable<HealthResponse['indexing']>

function coerceProgressCount(value: unknown): number | undefined {
  if (typeof value !== 'number' || !Number.isFinite(value)) return undefined
  const whole = Math.trunc(value)
  return whole < 0 ? 0 : whole
}

function coerceGeneration(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined
  const trimmed = value.trim()
  return trimmed.length ? trimmed : undefined
}

export function normalizeHealthIndexing(indexing: HealthResponse['indexing']): HealthIndexing | null {
  if (!indexing) return null
  const state = indexing.state
  if (state !== 'idle' && state !== 'running' && state !== 'ready' && state !== 'error') {
    return null
  }

  let done = coerceProgressCount(indexing.done)
  const total = coerceProgressCount(indexing.total)
  if (done !== undefined && total !== undefined && done > total) {
    done = total
  }

  return {
    state,
    scope: typeof indexing.scope === 'string' ? indexing.scope : undefined,
    done,
    total,
    generation: coerceGeneration(indexing.generation),
    started_at: typeof indexing.started_at === 'string' ? indexing.started_at : undefined,
    finished_at: typeof indexing.finished_at === 'string' ? indexing.finished_at : undefined,
    error: typeof indexing.error === 'string' ? indexing.error : undefined,
  }
}

export function indexingEquals(a: HealthIndexing | null, b: HealthIndexing | null): boolean {
  if (a === b) return true
  if (!a || !b) return false
  return (
    a.state === b.state &&
    a.scope === b.scope &&
    a.done === b.done &&
    a.total === b.total &&
    a.generation === b.generation &&
    a.started_at === b.started_at &&
    a.finished_at === b.finished_at &&
    a.error === b.error
  )
}

export function shouldContinueIndexingPoll(indexing: HealthIndexing | null): boolean {
  return indexing?.state === 'idle' || indexing?.state === 'running'
}

export function nextIndexingPollDelayMs(
  indexing: HealthIndexing | null,
  runningPollMs: number,
  retryPollMs: number,
): number {
  return indexing?.state === 'running' ? runningPollMs : retryPollMs
}

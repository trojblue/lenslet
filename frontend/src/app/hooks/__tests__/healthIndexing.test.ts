import { describe, expect, it } from 'vitest'
import {
  indexingEquals,
  nextIndexingPollDelayMs,
  normalizeHealthIndexing,
  shouldContinueIndexingPoll,
  type HealthIndexing,
} from '../healthIndexing'

describe('health indexing contracts', () => {
  it('normalizes known lifecycle states and clamps progress', () => {
    const normalized = normalizeHealthIndexing({
      state: 'running',
      scope: '/shots',
      done: 12,
      total: 9,
      started_at: '2026-02-12T00:00:00Z',
    })
    expect(normalized).toEqual({
      state: 'running',
      scope: '/shots',
      done: 9,
      total: 9,
      generation: undefined,
      started_at: '2026-02-12T00:00:00Z',
      finished_at: undefined,
      error: undefined,
    })
  })

  it('rejects unknown indexing states', () => {
    const normalized = normalizeHealthIndexing({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      state: 'paused' as any,
    })
    expect(normalized).toBeNull()
  })

  it('keeps polling while indexing is non-terminal', () => {
    const idle: HealthIndexing = { state: 'idle' }
    const running: HealthIndexing = { state: 'running' }
    const ready: HealthIndexing = { state: 'ready' }
    const errored: HealthIndexing = { state: 'error', error: 'boom' }

    expect(shouldContinueIndexingPoll(idle)).toBe(true)
    expect(shouldContinueIndexingPoll(running)).toBe(true)
    expect(shouldContinueIndexingPoll(ready)).toBe(false)
    expect(shouldContinueIndexingPoll(errored)).toBe(false)
  })

  it('computes poll delay by lifecycle state', () => {
    const runningDelay = nextIndexingPollDelayMs({ state: 'running' }, 1200, 3000)
    const idleDelay = nextIndexingPollDelayMs({ state: 'idle' }, 1200, 3000)
    const unknownDelay = nextIndexingPollDelayMs(null, 1200, 3000)

    expect(runningDelay).toBe(1200)
    expect(idleDelay).toBe(3000)
    expect(unknownDelay).toBe(3000)
  })

  it('compares normalized lifecycle payloads deterministically', () => {
    const a: HealthIndexing = { state: 'running', scope: '/', done: 2, total: 5, generation: 'g1' }
    const b: HealthIndexing = { state: 'running', scope: '/', done: 2, total: 5, generation: 'g1' }
    const c: HealthIndexing = { state: 'running', scope: '/', done: 3, total: 5, generation: 'g1' }
    const d: HealthIndexing = { state: 'running', scope: '/', done: 2, total: 5, generation: 'g2' }

    expect(indexingEquals(a, b)).toBe(true)
    expect(indexingEquals(a, c)).toBe(false)
    expect(indexingEquals(a, d)).toBe(false)
    expect(indexingEquals(a, null)).toBe(false)
    expect(indexingEquals(null, null)).toBe(true)
  })
})

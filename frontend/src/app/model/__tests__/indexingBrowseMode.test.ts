import { describe, expect, it } from 'vitest'
import {
  captureScanGeneration,
  deriveIndexingBrowseMode,
  normalizeIndexingGeneration,
  type IndexingBrowseModeState,
} from '../indexingBrowseMode'

describe('indexing browse mode', () => {
  it('normalizes generation values', () => {
    expect(normalizeIndexingGeneration('  g-1  ')).toBe('g-1')
    expect(normalizeIndexingGeneration('')).toBeNull()
    expect(normalizeIndexingGeneration(undefined)).toBeNull()
  })

  it('captures scan generation only while indexing is active', () => {
    expect(captureScanGeneration(null, { state: 'running', generation: 'g1' })).toBe('g1')
    expect(captureScanGeneration('g1', { state: 'idle', generation: 'g2' })).toBe('g2')
    expect(captureScanGeneration('g2', { state: 'ready', generation: 'g3' })).toBe('g2')
    expect(captureScanGeneration('g2', { state: 'error', generation: 'g4' })).toBe('g2')
  })

  it('derives scan-stable lock and completion banner state', () => {
    const state: IndexingBrowseModeState = {
      scanGeneration: 'g1',
      recentGeneration: null,
    }

    expect(deriveIndexingBrowseMode({ state: 'running', generation: 'g1' }, state)).toMatchObject({
      scanStableActive: true,
      sortLocked: true,
      showSwitchToMostRecentBanner: false,
    })

    expect(deriveIndexingBrowseMode({ state: 'ready', generation: 'g1' }, state)).toMatchObject({
      scanStableActive: true,
      sortLocked: true,
      showSwitchToMostRecentBanner: true,
    })
  })

  it('resets deterministically for a new generation after switching to most recent', () => {
    const switched: IndexingBrowseModeState = {
      scanGeneration: 'g1',
      recentGeneration: 'g1',
    }

    expect(deriveIndexingBrowseMode({ state: 'ready', generation: 'g1' }, switched)).toMatchObject({
      scanStableActive: false,
      showSwitchToMostRecentBanner: false,
    })

    const nextScanGeneration = captureScanGeneration(switched.scanGeneration, {
      state: 'running',
      generation: 'g2',
    })
    const nextState: IndexingBrowseModeState = {
      scanGeneration: nextScanGeneration,
      recentGeneration: switched.recentGeneration,
    }

    expect(deriveIndexingBrowseMode({ state: 'ready', generation: 'g2' }, nextState)).toMatchObject({
      scanStableActive: true,
      showSwitchToMostRecentBanner: true,
    })
  })
})

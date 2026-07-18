import { describe, expect, it } from 'vitest'
import {
  METADATA_LOADING_COPY_DELAY_MS,
  projectSingleMetadataSnapshot,
} from '../useInspectorSingleMetadata'

describe('projectSingleMetadataSnapshot', () => {
  it('returns the active snapshot when context keys match', () => {
    const projected = projectSingleMetadataSnapshot(
      {
        contextKey: '/images/a.png',
        metaRaw: { quick_view_defaults: { prompt: 'sunset' } },
        metaError: null,
        metaState: 'loaded',
        showPilInfo: true,
      },
      '/images/a.png',
    )

    expect(projected).toEqual({
      metaRaw: { quick_view_defaults: { prompt: 'sunset' } },
      metaError: null,
      metaState: 'loaded',
      showPilInfo: true,
    })
  })

  it('hides out-of-order completion snapshots when the active context moved on', () => {
    const projected = projectSingleMetadataSnapshot(
      {
        contextKey: '/images/a.png',
        metaRaw: { quick_view_defaults: { prompt: 'stale prompt' } },
        metaError: null,
        metaState: 'loaded',
        showPilInfo: true,
      },
      '/images/b.png',
    )

    expect(projected).toEqual({
      metaRaw: null,
      metaError: null,
      metaState: 'idle',
      showPilInfo: false,
    })
  })

  it('projects target-owned pending synchronously for autoload context changes', () => {
    const projected = projectSingleMetadataSnapshot(
      {
        contextKey: '/images/a.png',
        metaRaw: { quick_view_defaults: { prompt: 'stale prompt' } },
        metaError: null,
        metaState: 'loaded',
        showPilInfo: true,
      },
      '/images/b.png',
      true,
    )

    expect(projected).toEqual({
      metaRaw: null,
      metaError: null,
      metaState: 'loading',
      showPilInfo: false,
    })
  })

  it('keeps the approved metadata loading-copy delay explicit', () => {
    expect(METADATA_LOADING_COPY_DELAY_MS).toBe(1_000)
  })
})

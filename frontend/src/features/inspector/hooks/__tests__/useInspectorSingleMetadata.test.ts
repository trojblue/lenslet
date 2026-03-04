import { describe, expect, it } from 'vitest'
import { projectSingleMetadataSnapshot } from '../useInspectorSingleMetadata'

describe('projectSingleMetadataSnapshot', () => {
  it('returns the active snapshot when context keys match', () => {
    const projected = projectSingleMetadataSnapshot(
      {
        contextKey: '/images/a.png::v1',
        metaRaw: { quick_view_defaults: { prompt: 'sunset' } },
        metaError: null,
        metaState: 'loaded',
        showPilInfo: true,
      },
      '/images/a.png::v1',
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
        contextKey: '/images/a.png::v1',
        metaRaw: { quick_view_defaults: { prompt: 'stale prompt' } },
        metaError: null,
        metaState: 'loaded',
        showPilInfo: true,
      },
      '/images/b.png::v2',
    )

    expect(projected).toEqual({
      metaRaw: null,
      metaError: null,
      metaState: 'idle',
      showPilInfo: false,
    })
  })
})

import { describe, expect, it } from 'vitest'
import {
  buildCompareMetadataContextKey,
  buildSingleMetadataContextKey,
  shouldApplyMetadataResponse,
} from '../metadataRequestGuards'

describe('inspector metadata request guards', () => {
  it('builds single metadata context keys only when a path is active', () => {
    expect(buildSingleMetadataContextKey(null, undefined)).toBeNull()
    expect(buildSingleMetadataContextKey('/images/cat.png', undefined)).toBe('/images/cat.png::')
    expect(buildSingleMetadataContextKey('/images/cat.png', '2026-02-12T00:00:00Z')).toBe(
      '/images/cat.png::2026-02-12T00:00:00Z',
    )
  })

  it('builds compare metadata context keys only for ready two-path compare contexts', () => {
    expect(buildCompareMetadataContextKey(false, '/a.png', '/b.png')).toBeNull()
    expect(buildCompareMetadataContextKey(true, null, '/b.png')).toBeNull()
    expect(buildCompareMetadataContextKey(true, '/a.png', null)).toBeNull()
    expect(buildCompareMetadataContextKey(true, '/a.png', '/b.png')).toBe('/a.png::/b.png')
  })

  it('applies responses only when request id and context key both match active state', () => {
    expect(
      shouldApplyMetadataResponse({
        activeRequestId: 4,
        responseRequestId: 4,
        activeContextKey: '/a.png::v2',
        responseContextKey: '/a.png::v2',
      }),
    ).toBe(true)

    expect(
      shouldApplyMetadataResponse({
        activeRequestId: 5,
        responseRequestId: 4,
        activeContextKey: '/b.png::v1',
        responseContextKey: '/b.png::v1',
      }),
    ).toBe(false)

    expect(
      shouldApplyMetadataResponse({
        activeRequestId: 6,
        responseRequestId: 6,
        activeContextKey: '/c.png::v2',
        responseContextKey: '/c.png::v1',
      }),
    ).toBe(false)
  })

  it('rejects stale single-metadata responses after rapid selection/context switches', () => {
    const initialContext = buildSingleMetadataContextKey('/images/a.png', 'v1')
    const nextContext = buildSingleMetadataContextKey('/images/b.png', 'v2')
    expect(initialContext).not.toBeNull()
    expect(nextContext).not.toBeNull()

    expect(
      shouldApplyMetadataResponse({
        activeRequestId: 2,
        responseRequestId: 1,
        activeContextKey: nextContext,
        responseContextKey: initialContext,
      }),
    ).toBe(false)
    expect(
      shouldApplyMetadataResponse({
        activeRequestId: 2,
        responseRequestId: 2,
        activeContextKey: nextContext,
        responseContextKey: nextContext,
      }),
    ).toBe(true)
  })

  it('rejects stale compare responses after rapid compare-context toggles', () => {
    const firstCompareContext = buildCompareMetadataContextKey(true, '/images/a.png', '/images/b.png')
    const nextCompareContext = buildCompareMetadataContextKey(true, '/images/c.png', '/images/d.png')
    expect(firstCompareContext).not.toBeNull()
    expect(nextCompareContext).not.toBeNull()

    expect(
      shouldApplyMetadataResponse({
        activeRequestId: 4,
        responseRequestId: 3,
        activeContextKey: nextCompareContext,
        responseContextKey: firstCompareContext,
      }),
    ).toBe(false)
    expect(
      shouldApplyMetadataResponse({
        activeRequestId: 4,
        responseRequestId: 4,
        activeContextKey: nextCompareContext,
        responseContextKey: firstCompareContext,
      }),
    ).toBe(false)
    expect(
      shouldApplyMetadataResponse({
        activeRequestId: 4,
        responseRequestId: 4,
        activeContextKey: nextCompareContext,
        responseContextKey: nextCompareContext,
      }),
    ).toBe(true)
  })
})

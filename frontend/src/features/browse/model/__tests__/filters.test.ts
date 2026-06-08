import { describe, it, expect } from 'vitest'
import {
  applyFilterAst,
  normalizeFilterAst,
  setNotesContainsFilter,
  setNotesNotContainsFilter,
  setDateRangeFilter,
  setHeightCompareFilter,
  setCategoricalInFilter,
  setMetricRangeFilter,
  setNameContainsFilter,
  setNameNotContainsFilter,
  setStarsInFilter,
  setStarsNotInFilter,
  setUrlContainsFilter,
  setWidthCompareFilter,
} from '../filters'
import type { BrowseItemPayload } from '../../../../lib/types'

const baseItem = (overrides: Partial<BrowseItemPayload>): BrowseItemPayload => ({
  path: 'a',
  name: 'a',
  mime: 'image/jpeg',
  width: 0,
  height: 0,
  size: 0,
  has_thumbnail: true,
  has_metadata: true,
  notes: null,
  url: null,
  ...overrides,
})

describe('filter AST', () => {
  it('filters by star ratings', () => {
    const items = [
      baseItem({ path: 'a', star: 5 }),
      baseItem({ path: 'b', star: 3 }),
      baseItem({ path: 'c', star: 0 }),
    ]
    const filters = setStarsInFilter({ and: [] }, [5])
    const result = applyFilterAst(items, filters)
    expect(result.map((i) => i.path)).toEqual(['a'])
  })

  it('filters by excluded stars', () => {
    const items = [
      baseItem({ path: 'a', star: 5 }),
      baseItem({ path: 'b', star: 2 }),
      baseItem({ path: 'c', star: 0 }),
    ]
    const filters = setStarsNotInFilter({ and: [] }, [2, 0])
    const result = applyFilterAst(items, filters)
    expect(result.map((i) => i.path)).toEqual(['a'])
  })

  it('drops retired stars clauses at ingress', () => {
    expect(normalizeFilterAst({ and: [{ stars: [5, 0] }] })).toEqual({ and: [] })
  })

  it('filters by metric range and treats non-finite metric values as missing', () => {
    const items = [
      baseItem({ path: 'a', metrics: { score: 0.9 } }),
      baseItem({ path: 'b', metrics: { score: 0.4 } }),
      baseItem({ path: 'c', metrics: { score: null } }),
      baseItem({ path: 'd', metrics: { score: Number.NaN } }),
      baseItem({ path: 'e', metrics: { score: Number.POSITIVE_INFINITY } }),
      baseItem({ path: 'f', metrics: { score: Number.NEGATIVE_INFINITY } }),
    ]
    const filters = setMetricRangeFilter({ and: [] }, 'score', { min: 0.5, max: 1.0 })
    const result = applyFilterAst(items, filters)
    expect(result.map((i) => i.path)).toEqual(['a'])
  })

  it('drops metric range filters with non-finite bounds', () => {
    expect(setMetricRangeFilter({ and: [] }, 'score', { min: 0, max: Number.POSITIVE_INFINITY })).toEqual({ and: [] })
    expect(setMetricRangeFilter({ and: [] }, 'score', { min: Number.NaN, max: 1 })).toEqual({ and: [] })
  })

  it('filters by categorical membership', () => {
    const items = [
      baseItem({ path: 'a', categoricals: { l0r_viewpoint_family: 'frontal' } }),
      baseItem({ path: 'b', categoricals: { l0r_viewpoint_family: 'profile' } }),
      baseItem({ path: 'c', categoricals: { l0r_focus_mechanism: 'face_or_gaze' } }),
    ]
    const filters = setCategoricalInFilter({ and: [] }, 'l0r_viewpoint_family', ['frontal'])
    const result = applyFilterAst(items, filters)
    expect(result.map((i) => i.path)).toEqual(['a'])
  })

  it('filters by filename contains and not contains', () => {
    const items = [
      baseItem({ path: 'a', name: 'draft-shot.png' }),
      baseItem({ path: 'b', name: 'final-shot.png' }),
      baseItem({ path: 'c', name: 'draft-v1.png' }),
    ]
    let filters = setNameContainsFilter({ and: [] }, 'draft')
    filters = setNameNotContainsFilter(filters, 'v1')
    const result = applyFilterAst(items, filters)
    expect(result.map((i) => i.path)).toEqual(['a'])
  })

  it('filters by comments contains and not contains', () => {
    const items = [
      baseItem({ path: 'a', notes: 'Hero shot' }),
      baseItem({ path: 'b', notes: 'needs crop' }),
      baseItem({ path: 'c', notes: null }),
    ]
    let filters = setNotesContainsFilter({ and: [] }, 'hero')
    const containsResult = applyFilterAst(items, filters)
    expect(containsResult.map((i) => i.path)).toEqual(['a'])

    filters = setNotesNotContainsFilter({ and: [] }, 'hero')
    const notContainsResult = applyFilterAst(items, filters)
    expect(notContainsResult.map((i) => i.path)).toEqual(['b'])
  })

  it('filters by url contains', () => {
    const items = [
      baseItem({ path: 'a', url: 's3://bucket/hero.png' }),
      baseItem({ path: 'b', url: 'https://example.com/other.png' }),
      baseItem({ path: 'c', url: null }),
    ]
    const filters = setUrlContainsFilter({ and: [] }, 's3://bucket')
    const result = applyFilterAst(items, filters)
    expect(result.map((i) => i.path)).toEqual(['a'])
  })

  it('filters by date range', () => {
    const items = [
      baseItem({ path: 'a', added_at: '2024-02-01T00:00:00Z' }),
      baseItem({ path: 'b', added_at: '2023-12-15T12:00:00Z' }),
      baseItem({ path: 'c', added_at: null }),
    ]
    const filters = setDateRangeFilter({ and: [] }, { from: '2024-01-01', to: '2024-06-30' })
    const result = applyFilterAst(items, filters)
    expect(result.map((i) => i.path)).toEqual(['a'])
  })

  it('filters by width and height comparisons', () => {
    const items = [
      baseItem({ path: 'a', width: 2048, height: 1024 }),
      baseItem({ path: 'b', width: 1024, height: 2048 }),
      baseItem({ path: 'c', width: 0, height: 0 }),
    ]
    let filters = setWidthCompareFilter({ and: [] }, { op: '>=', value: 2000 })
    filters = setHeightCompareFilter(filters, { op: '<', value: 1500 })
    const result = applyFilterAst(items, filters)
    expect(result.map((i) => i.path)).toEqual(['a'])
  })
})

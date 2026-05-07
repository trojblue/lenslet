import { describe, it, expect } from 'vitest'
import {
  applyFilterAst,
  normalizeFilterAst,
  setNotesContainsFilter,
  setNotesNotContainsFilter,
  setDateRangeFilter,
  setHeightCompareFilter,
  setMetricRangeFilter,
  setNameContainsFilter,
  setNameNotContainsFilter,
  setStarFilter,
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
  hasThumbnail: true,
  hasMetadata: true,
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
    const filters = setStarFilter({ and: [] }, [5])
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

  it('normalizes legacy stars clauses to starsIn at ingress', () => {
    expect(normalizeFilterAst({ and: [{ stars: [5, 0] }] })).toEqual({
      and: [{ starsIn: { values: [5, 0] } }],
    })
  })

  it('filters by metric range', () => {
    const items = [
      baseItem({ path: 'a', metrics: { score: 0.9 } }),
      baseItem({ path: 'b', metrics: { score: 0.4 } }),
      baseItem({ path: 'c', metrics: { score: null } }),
    ]
    const filters = setMetricRangeFilter({ and: [] }, 'score', { min: 0.5, max: 1.0 })
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
      baseItem({ path: 'a', addedAt: '2024-02-01T00:00:00Z' }),
      baseItem({ path: 'b', addedAt: '2023-12-15T12:00:00Z' }),
      baseItem({ path: 'c', addedAt: null }),
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

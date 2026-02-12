import { describe, expect, it, vi } from 'vitest'
import type { FilterAST } from '../../../lib/types'
import { buildFilterChips } from '../filterChips'

function createActions() {
  return {
    clearStars: vi.fn(),
    clearStarsNotIn: vi.fn(),
    clearNameContains: vi.fn(),
    clearNameNotContains: vi.fn(),
    clearCommentsContains: vi.fn(),
    clearCommentsNotContains: vi.fn(),
    clearUrlContains: vi.fn(),
    clearUrlNotContains: vi.fn(),
    clearDateRange: vi.fn(),
    clearWidthCompare: vi.fn(),
    clearHeightCompare: vi.fn(),
    clearMetricRange: vi.fn(),
  }
}

describe('filterChips', () => {
  it('builds labels and clear handlers for all supported clause types', () => {
    const filters: FilterAST = {
      and: [
        { stars: [5, 0] },
        { starsIn: { values: [3, 1] } },
        { starsNotIn: { values: [4, 0] } },
        { nameContains: { value: '  cat  ' } },
        { nameNotContains: { value: 'dog' } },
        { commentsContains: { value: 'bright' } },
        { commentsNotContains: { value: 'blur' } },
        { urlContains: { value: 'cdn' } },
        { urlNotContains: { value: 'tmp' } },
        { dateRange: { from: '2025-01-01', to: '2025-01-31' } },
        { widthCompare: { op: '>=', value: 640 } },
        { heightCompare: { op: '<', value: 800 } },
        { metricRange: { key: 'aesthetic', min: 0.1, max: 0.9 } },
      ],
    }
    const actions = createActions()

    const chips = buildFilterChips(filters, actions)

    expect(chips.map((chip) => ({ id: chip.id, label: chip.label }))).toEqual([
      { id: 'stars', label: 'Rating in: 5, None' },
      { id: 'stars-in', label: 'Rating in: 3, 1' },
      { id: 'stars-not-in', label: 'Rating not in: 4, None' },
      { id: 'name-contains', label: 'Filename contains: cat' },
      { id: 'name-not-contains', label: 'Filename not: dog' },
      { id: 'comments-contains', label: 'Comments contain: bright' },
      { id: 'comments-not-contains', label: 'Comments not: blur' },
      { id: 'url-contains', label: 'URL contains: cdn' },
      { id: 'url-not-contains', label: 'URL not: tmp' },
      { id: 'date-range', label: 'Date: 2025-01-01 to 2025-01-31' },
      { id: 'width-compare', label: 'Width >= 640' },
      { id: 'height-compare', label: 'Height < 800' },
      { id: 'metric:aesthetic', label: 'aesthetic: 0.100–0.900' },
    ])

    for (const chip of chips) chip.onRemove()

    expect(actions.clearStars).toHaveBeenCalledTimes(2)
    expect(actions.clearStarsNotIn).toHaveBeenCalledTimes(1)
    expect(actions.clearNameContains).toHaveBeenCalledTimes(1)
    expect(actions.clearNameNotContains).toHaveBeenCalledTimes(1)
    expect(actions.clearCommentsContains).toHaveBeenCalledTimes(1)
    expect(actions.clearCommentsNotContains).toHaveBeenCalledTimes(1)
    expect(actions.clearUrlContains).toHaveBeenCalledTimes(1)
    expect(actions.clearUrlNotContains).toHaveBeenCalledTimes(1)
    expect(actions.clearDateRange).toHaveBeenCalledTimes(1)
    expect(actions.clearWidthCompare).toHaveBeenCalledTimes(1)
    expect(actions.clearHeightCompare).toHaveBeenCalledTimes(1)
    expect(actions.clearMetricRange).toHaveBeenCalledTimes(1)
    expect(actions.clearMetricRange).toHaveBeenCalledWith('aesthetic')
  })

  it('skips empty star/text/date clauses', () => {
    const filters: FilterAST = {
      and: [
        { stars: [] },
        { starsIn: { values: [] } },
        { starsNotIn: { values: [] } },
        { nameContains: { value: '   ' } },
        { nameNotContains: { value: '' } },
        { commentsContains: { value: ' ' } },
        { commentsNotContains: { value: '' } },
        { urlContains: { value: '' } },
        { urlNotContains: { value: '   ' } },
        { dateRange: {} },
      ],
    }

    expect(buildFilterChips(filters, createActions())).toEqual([])
  })
})

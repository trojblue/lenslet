import { describe, expect, it } from 'vitest'
import type { BrowseItemPayload } from '../../../../lib/types'
import { computeAdaptiveRows, type AdaptiveRow } from '../adaptive'

const CONTAINER_WIDTH = 760
const TARGET_HEIGHT = 220
const GAP = 16
const CAPTION_HEIGHT = 28
const MIN_IMAGE_HEIGHT = TARGET_HEIGHT * 0.65
const MAX_IMAGE_HEIGHT = TARGET_HEIGHT * 1.35
const WIDTH_TOLERANCE = 0.5

function makeItem(path: string, width: number, height: number): BrowseItemPayload {
  const name = path.split('/').pop() ?? path
  return {
    path,
    name,
    mime: 'image/jpeg',
    width,
    height,
    size: 1,
    hasThumbnail: true,
    hasMetadata: true,
  }
}

function compute(items: BrowseItemPayload[]): AdaptiveRow[] {
  return computeAdaptiveRows({
    items,
    containerWidth: CONTAINER_WIDTH,
    targetHeight: TARGET_HEIGHT,
    gap: GAP,
    captionH: CAPTION_HEIGHT,
  })
}

function rowWidth(row: AdaptiveRow): number {
  return row.items.reduce((sum, item) => sum + item.displayW, 0) + Math.max(0, row.items.length - 1) * GAP
}

function expectNoHorizontalOverflow(rows: AdaptiveRow[]): void {
  for (const row of rows) {
    expect(rowWidth(row)).toBeLessThanOrEqual(CONTAINER_WIDTH + WIDTH_TOLERANCE)
  }
}

function expectBoundedNonLastRows(rows: AdaptiveRow[]): void {
  for (const row of rows.slice(0, -1)) {
    expect(row.imageH).toBeGreaterThanOrEqual(MIN_IMAGE_HEIGHT)
    expect(row.imageH).toBeLessThanOrEqual(MAX_IMAGE_HEIGHT)
  }
}

describe('computeAdaptiveRows', () => {
  it('uses the existing fallback aspect ratio for missing dimensions', () => {
    const [row] = compute([makeItem('/missing-size.jpg', 0, 0)])

    expect(row.items).toHaveLength(1)
    expect(row.imageH).toBe(TARGET_HEIGHT)
    expect(row.items[0].displayW).toBeCloseTo(1.333 * TARGET_HEIGHT, 2)
    expect(row.items[0].fit).toBeUndefined()
    expectNoHorizontalOverflow([row])
  })

  it('isolates panorama outliers as contained full-row cards instead of tiny strips', () => {
    const rows = compute([
      makeItem('/panorama-10x1.jpg', 1000, 100),
      makeItem('/normal.jpg', 100, 100),
      makeItem('/panorama-6x1.jpg', 600, 100),
    ])

    expect(rows[0].items).toHaveLength(1)
    expect(rows[0].imageH).toBeGreaterThanOrEqual(MIN_IMAGE_HEIGHT)
    expect(rows[0].items[0]).toMatchObject({
      originalIndex: 0,
      displayW: CONTAINER_WIDTH,
      fit: 'contain',
    })
    expect(rows[2].items[0]).toMatchObject({
      originalIndex: 2,
      displayW: CONTAINER_WIDTH,
      fit: 'contain',
    })
    expectNoHorizontalOverflow(rows)
    expectBoundedNonLastRows(rows)
  })

  it('isolates very tall images as contained full-row cards', () => {
    const rows = compute([
      makeItem('/tall-1x8.jpg', 100, 800),
      makeItem('/normal-a.jpg', 100, 100),
      makeItem('/normal-b.jpg', 100, 100),
    ])

    expect(rows[0].items).toHaveLength(1)
    expect(rows[0].imageH).toBeGreaterThanOrEqual(MIN_IMAGE_HEIGHT)
    expect(rows[0].items[0]).toMatchObject({
      originalIndex: 0,
      displayW: CONTAINER_WIDTH,
      fit: 'contain',
    })
    expectNoHorizontalOverflow(rows)
    expectBoundedNonLastRows(rows)
  })

  it('keeps one-image rows within the container when target height would overflow', () => {
    const [row] = compute([makeItem('/wide-but-not-contained.jpg', 400, 100)])

    expect(row.items).toHaveLength(1)
    expect(row.imageH).toBeGreaterThanOrEqual(MIN_IMAGE_HEIGHT)
    expect(row.imageH).toBeLessThanOrEqual(TARGET_HEIGHT)
    expect(row.items[0].fit).toBeUndefined()
    expectNoHorizontalOverflow([row])
  })

  it('chooses bounded rows for mixed screenshots and last-row leftovers', () => {
    const rows = compute([
      makeItem('/square-0.jpg', 100, 100),
      makeItem('/square-1.jpg', 100, 100),
      makeItem('/square-2.jpg', 100, 100),
      makeItem('/wide-leftover.jpg', 400, 100),
      makeItem('/portrait.jpg', 80, 160),
      makeItem('/unknown.jpg', 0, 0),
    ])

    expect(rows.map((row) => row.items.map((entry) => entry.originalIndex))).toEqual([
      [0, 1, 2],
      [3],
      [4, 5],
    ])
    expectNoHorizontalOverflow(rows)
    expectBoundedNonLastRows(rows)
    expect(rows.at(-1)?.imageH).toBe(TARGET_HEIGHT)
  })
})

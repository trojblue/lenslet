import { describe, expect, it } from 'vitest'
import { RANKING_DOT_COLORS, buildDotColorByImageId } from '../palette'

describe('ranking image color dots', () => {
  it('assigns colors by initial order and wraps the palette', () => {
    const mapping = buildDotColorByImageId(['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i'])

    expect(mapping.a).toBe(RANKING_DOT_COLORS[0])
    expect(mapping.h).toBe(RANKING_DOT_COLORS[7])
    expect(mapping.i).toBe(RANKING_DOT_COLORS[0])
  })

  it('ignores duplicates and keeps first-assignment colors stable', () => {
    const mapping = buildDotColorByImageId(['a', 'b', 'a', 'c', 'b'])

    expect(mapping).toEqual({
      a: RANKING_DOT_COLORS[0],
      b: RANKING_DOT_COLORS[1],
      c: RANKING_DOT_COLORS[2],
    })
  })

  it('is deterministic for repeated calls with same initial order', () => {
    const order = ['x', 'y', 'z', 'w']
    const first = buildDotColorByImageId(order)
    const second = buildDotColorByImageId(order)
    expect(second).toEqual(first)
  })
})

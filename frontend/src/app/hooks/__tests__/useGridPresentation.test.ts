import { describe, expect, it } from 'vitest'
import type { BrowseItemPayload } from '../../../lib/types'
import {
  GRID_PRESENTATION_GRACE_MS,
  resolveGridPresentation,
} from '../useGridPresentation'

function item(path: string): BrowseItemPayload {
  return {
    path,
    name: path.slice(1),
    mime: 'image/jpeg',
    width: 10,
    height: 10,
    size: 1,
    has_thumbnail: true,
    has_metadata: false,
  }
}

describe('grid presentation continuity', () => {
  const previousItems = [item('/previous.jpg')]

  it('retains the prior gallery while a replacement is inside the grace window', () => {
    expect(resolveGridPresentation({
      targetItems: [],
      previousItems,
      pending: true,
      graceExpired: false,
    })).toEqual({ items: previousItems, phase: 'grace', retained: true })
    expect(GRID_PRESENTATION_GRACE_MS).toBe(800)
  })

  it('shows explicit loading after grace expires or on an initial load', () => {
    expect(resolveGridPresentation({
      targetItems: [],
      previousItems,
      pending: true,
      graceExpired: true,
    })).toEqual({ items: [], phase: 'loading', retained: false })
    expect(resolveGridPresentation({
      targetItems: [],
      previousItems: [],
      pending: true,
      graceExpired: false,
    })).toEqual({ items: [], phase: 'loading', retained: false })
  })

  it('commits fast success and terminal empty results immediately', () => {
    const nextItems = [item('/next.jpg')]
    expect(resolveGridPresentation({
      targetItems: nextItems,
      previousItems,
      pending: false,
      graceExpired: false,
    })).toEqual({ items: nextItems, phase: 'steady', retained: false })
    expect(resolveGridPresentation({
      targetItems: [],
      previousItems,
      pending: false,
      graceExpired: false,
    })).toEqual({ items: [], phase: 'steady', retained: false })
  })
})

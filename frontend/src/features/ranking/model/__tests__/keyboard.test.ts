import { describe, expect, it } from 'vitest'
import {
  getBoardKeyAction,
  getFullscreenKeyAction,
  shouldIgnoreRankingHotkey,
} from '../keyboard'

describe('ranking keyboard routing', () => {
  it('maps board mode key actions', () => {
    expect(getBoardKeyAction('1', 3)).toEqual({ type: 'assign-rank', rankIndex: 0 })
    expect(getBoardKeyAction('3', 3)).toEqual({ type: 'assign-rank', rankIndex: 2 })
    expect(getBoardKeyAction('ArrowLeft', 3)).toEqual({
      type: 'select-neighbor',
      direction: 'left',
    })
    expect(getBoardKeyAction('ArrowRight', 3)).toEqual({
      type: 'select-neighbor',
      direction: 'right',
    })
    expect(getBoardKeyAction('a', 3)).toEqual({
      type: 'select-neighbor',
      direction: 'left',
    })
    expect(getBoardKeyAction('D', 3)).toEqual({
      type: 'select-neighbor',
      direction: 'right',
    })
    expect(getBoardKeyAction('q', 3)).toEqual({ type: 'instance-nav', direction: 'prev' })
    expect(getBoardKeyAction('E', 3)).toEqual({ type: 'instance-nav', direction: 'next' })
    expect(getBoardKeyAction('Enter', 3)).toEqual({ type: 'fullscreen-open' })
  })

  it('maps fullscreen key actions and ignores board-only keys', () => {
    expect(getFullscreenKeyAction('2', 3)).toEqual({ type: 'assign-rank', rankIndex: 1 })
    expect(getFullscreenKeyAction('a', 3)).toEqual({ type: 'fullscreen-nav', direction: 'prev' })
    expect(getFullscreenKeyAction('D', 3)).toEqual({ type: 'fullscreen-nav', direction: 'next' })
    expect(getFullscreenKeyAction('ArrowLeft', 3)).toEqual({
      type: 'fullscreen-nav',
      direction: 'prev',
    })
    expect(getFullscreenKeyAction('ArrowRight', 3)).toEqual({
      type: 'fullscreen-nav',
      direction: 'next',
    })
    expect(getFullscreenKeyAction('Escape', 3)).toEqual({ type: 'fullscreen-close' })
    expect(getFullscreenKeyAction('q', 3)).toEqual({ type: 'none' })
    expect(getFullscreenKeyAction('Backspace', 3)).toEqual({ type: 'none' })
  })

  it('rejects rank keys that exceed max ranks', () => {
    expect(getBoardKeyAction('4', 3)).toEqual({ type: 'none' })
    expect(getFullscreenKeyAction('9', 2)).toEqual({ type: 'none' })
  })

  it('ignores hotkeys for editable targets and Enter on interactive controls', () => {
    expect(
      shouldIgnoreRankingHotkey('1', {
        isContentEditable: true,
        tagName: 'div',
        insideInteractiveControl: false,
      }),
    ).toBe(true)
    expect(
      shouldIgnoreRankingHotkey('2', {
        isContentEditable: false,
        tagName: 'input',
        insideInteractiveControl: true,
      }),
    ).toBe(true)
    expect(
      shouldIgnoreRankingHotkey('Enter', {
        isContentEditable: false,
        tagName: 'button',
        insideInteractiveControl: true,
      }),
    ).toBe(true)
    expect(
      shouldIgnoreRankingHotkey('3', {
        isContentEditable: false,
        tagName: 'button',
        insideInteractiveControl: true,
      }),
    ).toBe(false)
  })
})

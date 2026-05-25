import { describe, expect, it } from 'vitest'
import {
  LEFT_SIDEBAR_RAIL_WIDTH_PX,
  resolveLeftToolToggle,
  resolveSidebarHotkeyToggle,
  toggleLeftPanelContent,
} from '../sidebarLayout'

describe('sidebarLayout helpers', () => {
  it('toggles left panel content for toolbar and hotkey handlers', () => {
    expect(toggleLeftPanelContent(true)).toBe(false)
    expect(toggleLeftPanelContent(false)).toBe(true)
  })

  it('toggles only the left content panel for Ctrl+B', () => {
    expect(resolveSidebarHotkeyToggle({
      leftContentOpen: true,
      rightOpen: true,
      altKey: false,
    })).toEqual({
      leftContentOpen: false,
      rightOpen: true,
    })
  })

  it('toggles only the right panel for Ctrl+Alt+B', () => {
    expect(resolveSidebarHotkeyToggle({
      leftContentOpen: true,
      rightOpen: true,
      altKey: true,
    })).toEqual({
      leftContentOpen: true,
      rightOpen: false,
    })
  })

  it('collapses and expands content when clicking the active tab', () => {
    expect(resolveLeftToolToggle({
      activeTool: 'folders',
      contentOpen: true,
      clickedTool: 'folders',
    })).toEqual({
      nextTool: 'folders',
      contentOpen: false,
    })

    expect(resolveLeftToolToggle({
      activeTool: 'metrics',
      contentOpen: false,
      clickedTool: 'metrics',
    })).toEqual({
      nextTool: 'metrics',
      contentOpen: true,
    })
  })

  it('switches tools and ensures content is visible for inactive-tab clicks', () => {
    expect(resolveLeftToolToggle({
      activeTool: 'folders',
      contentOpen: false,
      clickedTool: 'metrics',
    })).toEqual({
      nextTool: 'metrics',
      contentOpen: true,
    })
  })

  it('keeps the rail width constant aligned with the responsive policy', () => {
    expect(LEFT_SIDEBAR_RAIL_WIDTH_PX).toBe(48)
  })
})

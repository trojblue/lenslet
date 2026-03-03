import { describe, expect, it } from 'vitest'
import {
  LEFT_SIDEBAR_RAIL_WIDTH_PX,
  resolveLeftColumnLayout,
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

  it('keeps the icon rail visible on desktop when content is collapsed', () => {
    expect(resolveLeftColumnLayout({
      isNarrowViewport: false,
      contentOpen: false,
      contentWidth: 320,
    })).toEqual({
      railVisible: true,
      columnWidth: LEFT_SIDEBAR_RAIL_WIDTH_PX,
    })
  })

  it('uses full content width when content is open', () => {
    expect(resolveLeftColumnLayout({
      isNarrowViewport: false,
      contentOpen: true,
      contentWidth: 286,
    })).toEqual({
      railVisible: true,
      columnWidth: 286,
    })
  })

  it('hides the left rail entirely on narrow viewports when content is collapsed', () => {
    expect(resolveLeftColumnLayout({
      isNarrowViewport: true,
      contentOpen: false,
      contentWidth: 286,
    })).toEqual({
      railVisible: false,
      columnWidth: 0,
    })
  })
})

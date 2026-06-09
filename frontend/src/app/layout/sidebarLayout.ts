import { RESPONSIVE_LAYOUT_CONSTANTS } from './responsiveLayoutPolicy'

export const LEFT_SIDEBAR_RAIL_WIDTH_PX = RESPONSIVE_LAYOUT_CONSTANTS.leftRailWidth

export type LeftTool = 'folders' | 'metrics' | 'derived'

export function toggleLeftPanelContent(open: boolean): boolean {
  return !open
}

export function resolveLeftToolToggle({
  activeTool,
  contentOpen,
  clickedTool,
}: {
  activeTool: LeftTool
  contentOpen: boolean
  clickedTool: LeftTool
}): {
  nextTool: LeftTool
  contentOpen: boolean
} {
  if (clickedTool === activeTool) {
    return {
      nextTool: activeTool,
      contentOpen: toggleLeftPanelContent(contentOpen),
    }
  }
  return {
    nextTool: clickedTool,
    contentOpen: true,
  }
}

export function resolveSidebarHotkeyToggle({
  leftContentOpen,
  rightOpen,
  altKey,
}: {
  leftContentOpen: boolean
  rightOpen: boolean
  altKey: boolean
}): {
  leftContentOpen: boolean
  rightOpen: boolean
} {
  if (altKey) {
    return {
      leftContentOpen,
      rightOpen: !rightOpen,
    }
  }
  return {
    leftContentOpen: toggleLeftPanelContent(leftContentOpen),
    rightOpen,
  }
}

export const LEFT_SIDEBAR_RAIL_WIDTH_PX = 48

type LeftTool = 'folders' | 'metrics'

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

export function resolveLeftColumnLayout({
  isNarrowViewport,
  contentOpen,
  contentWidth,
}: {
  isNarrowViewport: boolean
  contentOpen: boolean
  contentWidth: number
}): {
  railVisible: boolean
  columnWidth: number
} {
  const railVisible = !isNarrowViewport || contentOpen
  if (!railVisible) {
    return { railVisible: false, columnWidth: 0 }
  }
  if (!contentOpen) {
    return { railVisible: true, columnWidth: LEFT_SIDEBAR_RAIL_WIDTH_PX }
  }
  return {
    railVisible: true,
    columnWidth: Math.max(LEFT_SIDEBAR_RAIL_WIDTH_PX, contentWidth),
  }
}

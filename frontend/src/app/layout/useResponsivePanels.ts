import { useCallback, useLayoutEffect, useState } from 'react'
import type { ResponsiveLayoutModel } from './responsiveLayoutPolicy'

export type PanelSide = 'left' | 'right'

/** Overlay intent is transient; persisted desktop preferences never open a modal. */
export function useResponsivePanels(
  layout: ResponsiveLayoutModel,
  blocked: boolean,
  setLeftOpen: (open: boolean) => void,
  setRightOpen: (open: boolean) => void,
) {
  const [requestedSheet, setRequestedSheet] = useState<PanelSide | null>(null)
  const sheet = !blocked && requestedSheet && layout.panelModes[requestedSheet] === 'overlay'
    ? requestedSheet
    : null
  useLayoutEffect(() => {
    if (requestedSheet && sheet !== requestedSheet) setRequestedSheet(null)
  }, [requestedSheet, sheet])
  const closeSheet = useCallback(() => setRequestedSheet(null), [])
  const setPanelOpen = useCallback((side: PanelSide, open: boolean) => {
    if (layout.panelModes[side] === 'overlay') {
      setRequestedSheet((current) => open ? side : current === side ? null : current)
    } else {
      (side === 'left' ? setLeftOpen : setRightOpen)(open)
    }
  }, [layout.panelModes, setLeftOpen, setRightOpen])
  const leftVisible = layout.effectiveLeftOpen || sheet === 'left'
  const rightVisible = layout.effectiveRightOpen || sheet === 'right'
  return { sheet, closeSheet, setPanelOpen, leftVisible, rightVisible,
    leftRailVisible: layout.leftRailVisible || sheet === 'left' }
}

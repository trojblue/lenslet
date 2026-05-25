import { useEffect, useRef, useState } from 'react'
import {
  RESPONSIVE_LAYOUT_CONSTANTS,
  clampSidebarDragWidth,
  resolveSidebarDragConstraint,
} from './responsiveLayoutPolicy'

export const SIDEBAR_STORAGE_KEYS = {
  leftFolders: 'leftW.folders',
  leftMetrics: 'leftW.metrics',
  right: 'rightW',
} as const

type LeftTool = 'folders' | 'metrics'
type SidebarStorageKey = (typeof SIDEBAR_STORAGE_KEYS)[keyof typeof SIDEBAR_STORAGE_KEYS]

function isPositiveFiniteNumber(value: number): boolean {
  return Number.isFinite(value) && value > 0
}

function parseStoredWidth(value: string | null): number | null {
  const parsed = Number(value)
  return isPositiveFiniteNumber(parsed) ? parsed : null
}

export function getLeftSidebarStorageKey(leftTool: LeftTool): SidebarStorageKey {
  return leftTool === 'metrics' ? SIDEBAR_STORAGE_KEYS.leftMetrics : SIDEBAR_STORAGE_KEYS.leftFolders
}

export function readPersistedSidebarWidths(storage: Pick<Storage, 'getItem'>): {
  leftFoldersW: number | null
  leftMetricsW: number | null
  rightW: number | null
} {
  const leftFoldersW = parseStoredWidth(storage.getItem(SIDEBAR_STORAGE_KEYS.leftFolders))
  const leftMetricsW = parseStoredWidth(storage.getItem(SIDEBAR_STORAGE_KEYS.leftMetrics))
  const rightW = parseStoredWidth(storage.getItem(SIDEBAR_STORAGE_KEYS.right))
  return { leftFoldersW, leftMetricsW, rightW }
}

export function persistSidebarWidth(
  storage: Pick<Storage, 'setItem'>,
  key: SidebarStorageKey,
  width: number,
): void {
  storage.setItem(key, String(width))
}

export function clampLeftSidebarWidth({
  clientX,
  appLeft,
  appWidth,
  rightWidth,
  leftWidth = RESPONSIVE_LAYOUT_CONSTANTS.leftContentMinWidth,
  userLeftOpen = true,
  userRightOpen = true,
}: {
  clientX: number
  appLeft: number
  appWidth: number
  leftWidth?: number
  rightWidth: number
  userLeftOpen?: boolean
  userRightOpen?: boolean
}): number {
  const x = clientX - appLeft
  return clampSidebarDragWidth(x, resolveSidebarDragConstraint({
    viewportWidth: appWidth,
    activeSide: 'left',
    userLeftOpen,
    userRightOpen,
    leftPreferredWidth: leftWidth,
    rightPreferredWidth: rightWidth,
  }))
}

export function clampRightSidebarWidth({
  clientX,
  appLeft,
  appWidth,
  leftWidth,
  rightWidth = RESPONSIVE_LAYOUT_CONSTANTS.rightInspectorMinUsableWidth,
  userLeftOpen = true,
  userRightOpen = true,
}: {
  clientX: number
  appLeft: number
  appWidth: number
  leftWidth: number
  rightWidth?: number
  userLeftOpen?: boolean
  userRightOpen?: boolean
}): number {
  const x = clientX - appLeft
  const fromRight = appWidth - x
  return clampSidebarDragWidth(fromRight, resolveSidebarDragConstraint({
    viewportWidth: appWidth,
    activeSide: 'right',
    userLeftOpen,
    userRightOpen,
    leftPreferredWidth: leftWidth,
    rightPreferredWidth: rightWidth,
  }))
}

function isNonPrimaryMousePointer(event: React.PointerEvent<HTMLDivElement>): boolean {
  return (event.pointerType ?? 'mouse') === 'mouse' && event.button !== 0
}

function trySetPointerCapture(target: HTMLDivElement, pointerId: number): void {
  try {
    target.setPointerCapture(pointerId)
  } catch {
    // Ignore unsupported capture attempts.
  }
}

function tryReleasePointerCapture(target: HTMLDivElement, pointerId: number): void {
  try {
    target.releasePointerCapture(pointerId)
  } catch {
    // Ignore unsupported release attempts.
  }
}

export function useSidebars(
  appRef: React.RefObject<HTMLDivElement | null>,
  leftTool: LeftTool,
  options: {
    userLeftOpen: boolean
    userRightOpen: boolean
  },
) {
  const [leftFoldersW, setLeftFoldersW] = useState<number>(240)
  const [leftMetricsW, setLeftMetricsW] = useState<number>(320)
  const [rightW, setRightW] = useState<number>(240)
  const leftW = leftTool === 'metrics' ? leftMetricsW : leftFoldersW
  const leftWRef = useRef(leftW)
  const rightWRef = useRef(rightW)
  const userLeftOpenRef = useRef(options.userLeftOpen)
  const userRightOpenRef = useRef(options.userRightOpen)
  useEffect(() => { leftWRef.current = leftW }, [leftW])
  useEffect(() => { rightWRef.current = rightW }, [rightW])
  useEffect(() => { userLeftOpenRef.current = options.userLeftOpen }, [options.userLeftOpen])
  useEffect(() => { userRightOpenRef.current = options.userRightOpen }, [options.userRightOpen])
  useEffect(() => {
    try {
      const persisted = readPersistedSidebarWidths(window.localStorage)
      if (persisted.leftFoldersW !== null) setLeftFoldersW(persisted.leftFoldersW)
      if (persisted.leftMetricsW !== null) setLeftMetricsW(persisted.leftMetricsW)
      if (persisted.rightW !== null) setRightW(persisted.rightW)
    } catch {}
  }, [])

  const bindPointerDrag = (
    event: React.PointerEvent<HTMLDivElement>,
    onMove: (event: PointerEvent) => void,
    onComplete: () => void,
  ): void => {
    if (isNonPrimaryMousePointer(event)) return
    event.preventDefault()
    const handle = event.currentTarget
    const pointerId = event.pointerId
    trySetPointerCapture(handle, pointerId)

    const onPointerMove = (nextEvent: PointerEvent) => {
      if (nextEvent.pointerId !== pointerId) return
      onMove(nextEvent)
    }

    function cleanup(): void {
      window.removeEventListener('pointermove', onPointerMove)
      window.removeEventListener('pointerup', onPointerUp)
      window.removeEventListener('pointercancel', onPointerUp)
      tryReleasePointerCapture(handle, pointerId)
    }

    function onPointerUp(nextEvent: PointerEvent): void {
      if (nextEvent.pointerId !== pointerId) return
      cleanup()
      onComplete()
    }

    window.addEventListener('pointermove', onPointerMove)
    window.addEventListener('pointerup', onPointerUp)
    window.addEventListener('pointercancel', onPointerUp)
  }

  const onResizeLeft = (e: React.PointerEvent<HTMLDivElement>) => {
    const app = appRef.current
    if (!app) return
    const rect = app.getBoundingClientRect()
    const storageKey = getLeftSidebarStorageKey(leftTool)
    const constraint = resolveSidebarDragConstraint({
      viewportWidth: rect.width,
      activeSide: 'left',
      userLeftOpen: userLeftOpenRef.current,
      userRightOpen: userRightOpenRef.current,
      leftPreferredWidth: leftWRef.current,
      rightPreferredWidth: rightWRef.current,
    })
    if (constraint.disabled) return
    let latestWidth = clampSidebarDragWidth(leftWRef.current, constraint)
    bindPointerDrag(
      e,
      (event) => {
        const nw = clampSidebarDragWidth(event.clientX - rect.left, constraint)
        latestWidth = nw
        if (leftTool === 'metrics') {
          setLeftMetricsW(nw)
        } else {
          setLeftFoldersW(nw)
        }
      },
      () => {
        try {
          persistSidebarWidth(window.localStorage, storageKey, latestWidth)
        } catch {}
      },
    )
  }

  const onResizeRight = (e: React.PointerEvent<HTMLDivElement>) => {
    const app = appRef.current
    if (!app) return
    const rect = app.getBoundingClientRect()
    const constraint = resolveSidebarDragConstraint({
      viewportWidth: rect.width,
      activeSide: 'right',
      userLeftOpen: userLeftOpenRef.current,
      userRightOpen: userRightOpenRef.current,
      leftPreferredWidth: leftWRef.current,
      rightPreferredWidth: rightWRef.current,
    })
    if (constraint.disabled) return
    let latestWidth = clampSidebarDragWidth(rightWRef.current, constraint)
    bindPointerDrag(
      e,
      (event) => {
        const nw = clampSidebarDragWidth(rect.width - (event.clientX - rect.left), constraint)
        latestWidth = nw
        rightWRef.current = nw
        setRightW(nw)
      },
      () => {
        try {
          persistSidebarWidth(window.localStorage, SIDEBAR_STORAGE_KEYS.right, latestWidth)
        } catch {}
      },
    )
  }

  return { leftW, rightW, onResizeLeft, onResizeRight }
}

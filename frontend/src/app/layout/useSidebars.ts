import { useEffect, useRef, useState } from 'react'

export const SIDEBAR_STORAGE_KEYS = {
  leftFolders: 'leftW.folders',
  leftMetrics: 'leftW.metrics',
  leftLegacy: 'leftW',
  right: 'rightW',
} as const

type LeftTool = 'folders' | 'metrics'
type SidebarStorageKey = (typeof SIDEBAR_STORAGE_KEYS)[keyof typeof SIDEBAR_STORAGE_KEYS]

const LEFT_MIN_WIDTH = 200
const RIGHT_MIN_WIDTH = 240
const MIN_CENTER_WIDTH = 200

function isPositiveFiniteNumber(value: number): boolean {
  return Number.isFinite(value) && value > 0
}

function parseStoredWidth(value: string | null): number | null {
  const parsed = Number(value)
  return isPositiveFiniteNumber(parsed) ? parsed : null
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max)
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
    ?? parseStoredWidth(storage.getItem(SIDEBAR_STORAGE_KEYS.leftLegacy))
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
}: {
  clientX: number
  appLeft: number
  appWidth: number
  rightWidth: number
}): number {
  const x = clientX - appLeft
  const max = Math.max(LEFT_MIN_WIDTH, appWidth - rightWidth - MIN_CENTER_WIDTH)
  return clamp(x, LEFT_MIN_WIDTH, max)
}

export function clampRightSidebarWidth({
  clientX,
  appLeft,
  appWidth,
  leftWidth,
}: {
  clientX: number
  appLeft: number
  appWidth: number
  leftWidth: number
}): number {
  const x = clientX - appLeft
  const fromRight = appWidth - x
  const max = Math.max(RIGHT_MIN_WIDTH, appWidth - leftWidth - MIN_CENTER_WIDTH)
  return clamp(fromRight, RIGHT_MIN_WIDTH, max)
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
) {
  const [leftFoldersW, setLeftFoldersW] = useState<number>(240)
  const [leftMetricsW, setLeftMetricsW] = useState<number>(320)
  const [rightW, setRightW] = useState<number>(240)
  const leftW = leftTool === 'metrics' ? leftMetricsW : leftFoldersW
  const leftWRef = useRef(leftW)
  const rightWRef = useRef(rightW)
  useEffect(() => { leftWRef.current = leftW }, [leftW])
  useEffect(() => { rightWRef.current = rightW }, [rightW])
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
    let latestWidth = leftWRef.current
    bindPointerDrag(
      e,
      (event) => {
        const nw = clampLeftSidebarWidth({
          clientX: event.clientX,
          appLeft: rect.left,
          appWidth: rect.width,
          rightWidth: rightWRef.current,
        })
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
    let latestWidth = rightWRef.current
    bindPointerDrag(
      e,
      (event) => {
        const nw = clampRightSidebarWidth({
          clientX: event.clientX,
          appLeft: rect.left,
          appWidth: rect.width,
          leftWidth: leftWRef.current,
        })
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

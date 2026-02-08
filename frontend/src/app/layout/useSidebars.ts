import { useEffect, useRef, useState } from 'react'

const LEFT_FOLDERS_KEY = 'leftW.folders'
const LEFT_METRICS_KEY = 'leftW.metrics'
const LEFT_LEGACY_KEY = 'leftW'
const RIGHT_KEY = 'rightW'
const LEFT_MIN_WIDTH = 200
const RIGHT_MIN_WIDTH = 240
const MIN_CENTER_WIDTH = 200

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
  leftTool: 'folders' | 'metrics',
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
      const ls = window.localStorage
      const lvFolders = Number(ls.getItem(LEFT_FOLDERS_KEY) ?? ls.getItem(LEFT_LEGACY_KEY))
      if (Number.isFinite(lvFolders) && lvFolders > 0) setLeftFoldersW(lvFolders)
      const lvMetrics = Number(ls.getItem(LEFT_METRICS_KEY))
      if (Number.isFinite(lvMetrics) && lvMetrics > 0) setLeftMetricsW(lvMetrics)
      const rv = Number(ls.getItem(RIGHT_KEY))
      if (Number.isFinite(rv) && rv > 0) setRightW(rv)
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
    const storageKey = leftTool === 'metrics' ? LEFT_METRICS_KEY : LEFT_FOLDERS_KEY
    let latestWidth = leftWRef.current
    bindPointerDrag(
      e,
      (event) => {
        const x = event.clientX - rect.left
        const max = Math.max(LEFT_MIN_WIDTH, rect.width - rightWRef.current - MIN_CENTER_WIDTH)
        const nw = Math.min(Math.max(x, LEFT_MIN_WIDTH), max)
        latestWidth = nw
        if (leftTool === 'metrics') {
          setLeftMetricsW(nw)
        } else {
          setLeftFoldersW(nw)
        }
      },
      () => {
        try {
          window.localStorage.setItem(storageKey, String(latestWidth))
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
        const x = event.clientX - rect.left
        const fromRight = rect.width - x
        const max = Math.max(RIGHT_MIN_WIDTH, rect.width - leftWRef.current - MIN_CENTER_WIDTH)
        const nw = Math.min(Math.max(fromRight, RIGHT_MIN_WIDTH), max)
        latestWidth = nw
        rightWRef.current = nw
        setRightW(nw)
      },
      () => {
        try {
          window.localStorage.setItem(RIGHT_KEY, String(latestWidth))
        } catch {}
      },
    )
  }

  return { leftW, rightW, onResizeLeft, onResizeRight }
}

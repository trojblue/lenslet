import { useEffect, useRef, useState } from 'react'

const LEFT_FOLDERS_KEY = 'leftW.folders'
const LEFT_METRICS_KEY = 'leftW.metrics'
const LEFT_LEGACY_KEY = 'leftW'
const RIGHT_KEY = 'rightW'

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

  const onResizeLeft = (e: React.MouseEvent) => {
    e.preventDefault()
    const app = appRef.current
    if (!app) return
    const rect = app.getBoundingClientRect()
    const storageKey = leftTool === 'metrics' ? LEFT_METRICS_KEY : LEFT_FOLDERS_KEY
    let latestWidth = leftWRef.current
    const onMove = (ev: MouseEvent) => {
      const x = ev.clientX - rect.left
      const min = 200
      const max = Math.max(min, rect.width - rightWRef.current - 200)
      const nw = Math.min(Math.max(x, min), max)
      latestWidth = nw
      if (leftTool === 'metrics') {
        setLeftMetricsW(nw)
      } else {
        setLeftFoldersW(nw)
      }
    }
    const onUp = () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
      try { window.localStorage.setItem(storageKey, String(latestWidth)) } catch {}
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  const onResizeRight = (e: React.MouseEvent) => {
    e.preventDefault()
    const app = appRef.current
    if (!app) return
    const rect = app.getBoundingClientRect()
    const onMove = (ev: MouseEvent) => {
      const x = ev.clientX - rect.left
      const fromRight = rect.width - x
      const min = 240
      const max = Math.max(min, rect.width - leftWRef.current - 200)
      const nw = Math.min(Math.max(fromRight, min), max)
      setRightW(nw)
    }
    const onUp = () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
      try { window.localStorage.setItem(RIGHT_KEY, String(rightWRef.current)) } catch {}
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  return { leftW, rightW, onResizeLeft, onResizeRight }
}

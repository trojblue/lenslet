import React, { useEffect, useMemo, useRef, useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import Toolbar from './components/Toolbar'
import FolderTree from './components/FolderTree'
import Grid from './components/Grid'
import Viewer from './components/Viewer'
import Inspector from './components/Inspector'
import { useFolder } from './api/folders'
import { api } from './api/client'
import './styles.css'

const qc = new QueryClient()

export default function AppRoot(){
  return (
    <QueryClientProvider client={qc}>
      <App/>
    </QueryClientProvider>
  )
}

function App(){
  const [current, setCurrent] = useState<string>('/')
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<string | null>(null)
  const [viewer, setViewer] = useState<string | null>(null)
  const [requestedZoom, setRequestedZoom] = useState<number | null>(null)
  const [currentZoom, setCurrentZoom] = useState<number>(100)
  const [leftW, setLeftW] = useState<number>(160)
  const [rightW, setRightW] = useState<number>(240)
  const appRef = useRef<HTMLDivElement | null>(null)
  const viewerHistoryPushedRef = useRef(false)
  const leftWRef = useRef(leftW)
  const rightWRef = useRef(rightW)
  useEffect(() => { leftWRef.current = leftW }, [leftW])
  useEffect(() => { rightWRef.current = rightW }, [rightW])
  // load from localStorage after mount; ignore if access is blocked
  useEffect(() => {
    try {
      const ls = window.localStorage
      const lv = Number(ls.getItem('leftW'))
      if (Number.isFinite(lv) && lv > 0) setLeftW(lv)
      const rv = Number(ls.getItem('rightW'))
      if (Number.isFinite(rv) && rv > 0) setRightW(rv)
    } catch {}
  }, [])
  const { data } = useFolder(current)

  const items = useMemo(()=> data?.items ?? [], [data])

  const startResizeLeft = (e: React.MouseEvent) => {
    e.preventDefault()
    const app = appRef.current
    if (!app) return
    const rect = app.getBoundingClientRect()
    const onMove = (ev: MouseEvent) => {
      const x = ev.clientX - rect.left
      const min = 160
      const max = Math.max(min, rect.width - rightW - 200)
      const nw = Math.min(Math.max(x, min), max)
      setLeftW(nw)
    }
    const onUp = () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
      try { window.localStorage.setItem('leftW', String(leftWRef.current)) } catch {}
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  const startResizeRight = (e: React.MouseEvent) => {
    e.preventDefault()
    const app = appRef.current
    if (!app) return
    const rect = app.getBoundingClientRect()
    const onMove = (ev: MouseEvent) => {
      const x = ev.clientX - rect.left
      const fromRight = rect.width - x
      const min = 240
      const max = Math.max(min, rect.width - leftW - 200)
      const nw = Math.min(Math.max(fromRight, min), max)
      setRightW(nw)
    }
    const onUp = () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
      try { window.localStorage.setItem('rightW', String(rightWRef.current)) } catch {}
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  // Prefetch neighbors for the open viewer (previous and next)
  useEffect(() => {
    if (!viewer) return
    const paths = items.map(i=> i.path)
    const idx = paths.indexOf(viewer)
    if (idx === -1) return
    const prevs = [paths[idx - 1], paths[idx - 2]].filter(Boolean) as string[]
    const nexts = [paths[idx + 1], paths[idx + 2]].filter(Boolean) as string[]
    for (const p of prevs) { try { api.prefetchFile(p) } catch {} }
    for (const p of nexts) { try { api.prefetchFile(p) } catch {} }
    // Prefetch their thumbnails too (very cheap)
    for (const p of [...prevs, ...nexts]) { try { api.prefetchThumb(p) } catch {} }
  }, [viewer, items])

  // On folder load, prefetch fullsize for the first 5 items (respect size cap)
  useEffect(() => {
    if (!data || !Array.isArray(data.items)) return
    const firstFive = data.items.slice(0, 5)
    for (const it of firstFive) { try { api.prefetchFile(it.path) } catch {} }
  }, [data?.path])

  // Initialize current folder from URL hash and keep in sync
  useEffect(() => {
    try {
      const raw = window.location.hash.startsWith('#') ? window.location.hash.slice(1) : window.location.hash
      const initial = raw ? decodeURI(raw) : '/'
      if (initial && typeof initial === 'string') setCurrent(initial.startsWith('/') ? initial : `/${initial}`)
    } catch {}
    const onHash = () => {
      try {
        const raw = window.location.hash.startsWith('#') ? window.location.hash.slice(1) : window.location.hash
        const next = raw ? decodeURI(raw) : '/'
        const norm = next.startsWith('/') ? next : `/${next}`
        // Any folder hash navigation should exit fullscreen
        setViewer(null)
        setCurrent(prev => (prev === norm ? prev : norm))
      } catch {}
    }
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const openFolder = (p: string) => {
    // Close fullscreen viewer when navigating to another folder
    setViewer(null)
    setCurrent(p)
    try {
      const nextHash = `#${encodeURI(p)}`
      if (window.location.hash !== nextHash) window.location.hash = nextHash
    } catch {}
  }

  // Manage viewer history entry so browser Back closes fullscreen first
  const openViewer = (p: string) => {
    setViewer(p)
    if (!viewerHistoryPushedRef.current) {
      try { window.history.pushState({ viewer: true }, '', window.location.href); viewerHistoryPushedRef.current = true } catch {}
    }
  }

  const closeViewer = () => {
    setViewer(null)
    if (viewerHistoryPushedRef.current) {
      viewerHistoryPushedRef.current = false
      try { window.history.back() } catch {}
    }
  }

  useEffect(() => {
    const onPop = () => {
      if (viewer) {
        viewerHistoryPushedRef.current = false
        setViewer(null)
      }
    }
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [viewer])

  return (
    <div className="app" ref={appRef} style={{ ['--left' as any]: `${leftW}px`, ['--right' as any]: `${rightW}px` }}>
      <Toolbar
        onSearch={setQuery}
        viewerActive={!!viewer}
        onBack={closeViewer}
        zoomPercent={viewer ? currentZoom : undefined}
        onZoomPercentChange={(p)=> setRequestedZoom(p)}
      />
      <FolderTree current={current} roots={[{label:'Root', path:'/'}]} data={data} onOpen={openFolder} onResize={startResizeLeft} />
      <div className="main">
        <Grid items={items} onOpen={(p)=>{ setSelected(p); }} onOpenViewer={(p)=> { openViewer(p); setSelected(p) }} />
      </div>
      <Inspector path={selected} item={items.find(i=>i.path===selected) ?? undefined} onResize={startResizeRight} />
      {viewer && (
        <Viewer
          path={viewer}
          onClose={closeViewer}
          onZoomChange={(p)=> setCurrentZoom(Math.round(p))}
          requestedZoomPercent={requestedZoom}
          onZoomRequestConsumed={()=> setRequestedZoom(null)}
          onNavigate={(delta)=>{
            const paths = items.map(i=> i.path)
            const idx = paths.indexOf(viewer)
            if (idx === -1) return
            const next = Math.min(paths.length - 1, Math.max(0, idx + delta))
            const np = paths[next]
            if (np && np !== viewer) { setViewer(np); setSelected(np) }
          }}
        />
      )}
    </div>
  )
}

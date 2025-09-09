import React, { useEffect, useMemo, useRef, useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import Toolbar from './components/Toolbar'
import FolderTree from './components/FolderTree'
import Grid from './components/Grid'
import Viewer from './components/Viewer'
import Inspector from './components/Inspector'
import { useFolder } from './api/folders'
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
  const [leftW, setLeftW] = useState<number>(160)
  const [rightW, setRightW] = useState<number>(240)
  const appRef = useRef<HTMLDivElement | null>(null)
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

  return (
    <div className="app" ref={appRef} style={{ ['--left' as any]: `${leftW}px`, ['--right' as any]: `${rightW}px` }}>
      <Toolbar onSearch={setQuery} />
      <FolderTree current={current} roots={[{label:'Root', path:'/'}]} data={data} onOpen={setCurrent} onResize={startResizeLeft} />
      <div className="main">
        <Grid items={items} onOpen={(p)=>{ setSelected(p); }} onOpenViewer={(p)=> setViewer(p)} />
      </div>
      <Inspector path={selected} item={items.find(i=>i.path===selected) ?? undefined} onResize={startResizeRight} />
      {viewer && <Viewer path={viewer} onClose={()=> setViewer(null)} />}
    </div>
  )
}

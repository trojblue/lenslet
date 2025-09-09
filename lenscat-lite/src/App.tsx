import React, { useMemo, useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import Toolbar from './components/Toolbar'
import FolderTree from './components/FolderTree'
import Grid from './components/Grid'
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
  const { data } = useFolder(current)

  const items = useMemo(()=> data?.items ?? [], [data])

  return (
    <div className="app">
      <Toolbar onSearch={setQuery} />
      <FolderTree current={current} roots={[{label:'Root', path:'/'}]} onOpen={setCurrent} />
      <div className="main">
        <Grid items={items} onOpen={(p)=>{ setSelected(p) }} />
      </div>
      <Inspector path={selected} item={items.find(i=>i.path===selected) ?? undefined} />
    </div>
  )
}

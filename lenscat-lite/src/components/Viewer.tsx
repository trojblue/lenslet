import React, { useEffect, useState } from 'react'
import { api } from '../api/client'

export default function Viewer({ path, onClose }:{ path: string; onClose:()=>void }){
  const [url, setUrl] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    api.getFile(path).then(b => { if (!alive) return; setUrl(URL.createObjectURL(b)) }).catch(()=>{})
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => { alive = false; window.removeEventListener('keydown', onKey); if (url) URL.revokeObjectURL(url) }
  }, [path])

  return (
    <div style={{ position:'fixed', inset:0, background:'rgba(0,0,0,0.92)', display:'flex', alignItems:'center', justifyContent:'center', zIndex: 50 }} onClick={onClose}>
      <button onClick={(e)=>{ e.stopPropagation(); onClose() }} style={{ position:'absolute', top:12, left:12, padding:'6px 10px', background:'#111', color:'#fff', border:'1px solid rgba(255,255,255,0.2)', borderRadius:8, cursor:'pointer' }}>← Back</button>
      {url && <img src={url} alt="viewer" onClick={(e)=> e.stopPropagation()} style={{ maxWidth:'96%', maxHeight:'92%', objectFit:'contain', transition:'opacity 180ms ease', opacity:0.99 }} />}
    </div>
  )
}



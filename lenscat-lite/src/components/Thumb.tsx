import React, { useEffect, useState } from 'react'
import { api } from '../api/client'

const blobUrlCache = new Map<string, string>()
const lruOrder: string[] = []
const MAX_BLOBS = 400

function remember(key: string, url: string) {
  blobUrlCache.set(key, url)
  lruOrder.push(key)
  if (lruOrder.length > MAX_BLOBS) {
    const old = lruOrder.shift()
    if (old) {
      const u = blobUrlCache.get(old)
      if (u) { try { URL.revokeObjectURL(u) } catch {} }
      blobUrlCache.delete(old)
    }
  }
}

if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', () => {
    for (const u of blobUrlCache.values()) { try { URL.revokeObjectURL(u) } catch {} }
    blobUrlCache.clear()
  }, { once: true } as any)
}

export default function Thumb({ path, name, onClick, selected, displayW, displayH }:{ path:string; name:string; onClick:(e:React.MouseEvent)=>void; selected?: boolean; displayW?: number; displayH?: number }){
  const [url, setUrl] = useState<string | null>(blobUrlCache.get(path) ?? null)
  useEffect(() => {
    let alive = true
    if (!url) {
      api.getThumb(path)
        .then(b => { if (!alive) return; const u = URL.createObjectURL(b); remember(path, u); setUrl(u) })
        .catch(()=>{})
    }
    return () => { alive = false }
  }, [path, url])
  return (
    <div className={`cell${selected ? ' selected' : ''}`} onClick={onClick}>
      {url ? (
        <img
          className="thumb"
          src={url}
          alt={name}
          loading="lazy"
          decoding="async"
          width={displayW ? Math.round(displayW) : undefined}
          height={displayH ? Math.round(displayH) : undefined}
        />
      ) : null}
      <div className="meta">{name}</div>
    </div>
  )
}

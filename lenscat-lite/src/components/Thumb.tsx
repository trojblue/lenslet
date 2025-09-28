import React, { useEffect, useState } from 'react'
import { api } from '../api/client'

const blobUrlCache = new Map<string, string>()
const MAX_BLOBS = 400

function remember(key: string, url: string) {
  if (blobUrlCache.has(key)) blobUrlCache.delete(key)
  blobUrlCache.set(key, url)
  while (blobUrlCache.size > MAX_BLOBS) {
    const first = blobUrlCache.entries().next().value as [string, string]
    if (!first) break
    const [oldKey, oldUrl] = first
    blobUrlCache.delete(oldKey)
    try { URL.revokeObjectURL(oldUrl) } catch {}
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
        .then(b => { if (!alive) return; const u = URL.createObjectURL(b); remember(path, u); setUrl(prev => { if (prev && prev !== u) { try { URL.revokeObjectURL(prev) } catch {} } return u }) })
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

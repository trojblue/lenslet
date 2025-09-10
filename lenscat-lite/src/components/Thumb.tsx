import React, { useEffect, useState } from 'react'
import { api } from '../api/client'

const blobUrlCache = new Map<string, string>()

export default function Thumb({ path, name, onClick, selected, displayW, displayH }:{ path:string; name:string; onClick:(e:React.MouseEvent)=>void; selected?: boolean; displayW?: number; displayH?: number }){
  const [url, setUrl] = useState<string | null>(blobUrlCache.get(path) ?? null)
  useEffect(() => {
    let alive = true
    if (!url) {
      api.getThumb(path)
        .then(b => { if (!alive) return; const u = URL.createObjectURL(b); blobUrlCache.set(path, u); setUrl(u) })
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

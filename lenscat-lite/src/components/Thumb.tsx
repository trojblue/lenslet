import React, { useEffect, useState } from 'react'
import { api } from '../api/client'

const blobUrlCache = new Map<string, string>()

export default function Thumb({ path, name, onClick }:{ path:string; name:string; onClick:()=>void }){
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
    <div className="cell" onClick={onClick}>
      {url ? <img className="thumb" src={url} alt={name} loading="lazy" decoding="async" /> : null}
      <div className="meta">{name}</div>
    </div>
  )
}

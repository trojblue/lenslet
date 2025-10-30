import React, { useEffect, useRef, useState } from 'react'
import { api } from '../../../shared/api/client'

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

export default function ThumbCard({ path, name, onClick, selected, displayW, displayH, ioRoot, isScrolling, priority }:{ path:string; name:string; onClick:(e:React.MouseEvent)=>void; selected?: boolean; displayW?: number; displayH?: number; ioRoot?: Element | null; isScrolling?: boolean; priority?: boolean }){
  const hostRef = useRef<HTMLDivElement | null>(null)
  const [url, setUrl] = useState<string | null>(blobUrlCache.get(path) ?? null)
  const [inView, setInView] = useState<boolean>(false)
  const [loaded, setLoaded] = useState<boolean>(false)

  useEffect(() => {
    const host = hostRef.current
    if (!host) return
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.target === host) { setInView(entry.isIntersecting || entry.intersectionRatio > 0) }
        }
      },
      { root: ioRoot ?? null, rootMargin: '200px 0px', threshold: 0.01 }
    )
    observer.observe(host)
    return () => { try { observer.unobserve(host) } catch {} ; try { observer.disconnect() } catch {} }
  }, [ioRoot, path])

  useEffect(() => {
    let alive = true
    if (!url && ((inView && !isScrolling) || priority)) {
      api.getThumb(path)
        .then(b => {
          if (!alive) return
          const u = URL.createObjectURL(b)
          remember(path, u)
          setUrl(prev => { if (prev && prev !== u) { try { URL.revokeObjectURL(prev) } catch {} } ; return u })
        })
        .catch(()=>{})
    }
    return () => { alive = false }
  }, [path, url, inView, isScrolling, priority])

  useEffect(() => { setLoaded(false) }, [url])
  return (
    <div ref={hostRef} className={`cell${selected ? ' selected' : ''}`} onClick={onClick}>
      {url ? (
        <img
          className={`thumb${loaded ? ' is-loaded' : ''}`}
          src={url}
          alt={name}
          loading="lazy"
          decoding="async"
          onLoad={()=> setLoaded(true)}
          width={displayW ? Math.round(displayW) : undefined}
          height={displayH ? Math.round(displayH) : undefined}
        />
      ) : null}
      <div className="meta">{name}</div>
    </div>
  )
}



import React, { useEffect, useMemo, useState } from 'react'
import { useSidecar, useUpdateSidecar, bulkUpdateSidecars } from '../api/items'
import { fmtBytes } from '../lib/util'
import { api } from '../api/client'

export default function Inspector({ path, selectedPaths = [], items = [], onResize }:{ path: string | null; selectedPaths?: string[]; items?: { path:string; size:number; w:number; h:number; type:string; }[]; onResize?:(e:React.MouseEvent)=>void }){
  const enabled = !!path
  const { data, isLoading } = useSidecar(path ?? '')
  const mut = useUpdateSidecar(path ?? '')
  const [tags, setTags] = useState<string>('')
  const [notes, setNotes] = useState<string>('')
  const [thumbUrl, setThumbUrl] = useState<string | null>(null)
  const star = (data as any)?.star ?? null

  const multi = (selectedPaths?.length ?? 0) > 1
  const selectedItems = useMemo(() => {
    if (!Array.isArray(items)) return [] as any[]
    const set = new Set(selectedPaths)
    return items.filter(i => set.has(i.path))
  }, [items, selectedPaths])
  const totalSize = useMemo(() => selectedItems.reduce((a, b:any)=> a + (b.size||0), 0), [selectedItems])

  useEffect(() => { if (data) { setTags((data.tags||[]).join(', ')); setNotes(data.notes||'') } }, [data?.updated_at])

  // Keyboard shortcuts for rating: 1..5 sets, 0 unsets
  useEffect(() => {
    if (!path) return
    const onKey = (e: KeyboardEvent) => {
      if (!path) return
      const target = e.target as HTMLElement | null
      if (target && (target.closest('input, textarea, [contenteditable="true"]'))) return
      const k = e.key
      if (!/^[0-5]$/.test(k)) return
      e.preventDefault()
      const val = k === '0' ? null : Number(k)
      if (multi && selectedPaths.length) {
        bulkUpdateSidecars(selectedPaths, { star: val })
      } else {
        const base = (data||{v:1,tags:[],notes:'',updated_at:'',updated_by:''}) as any
        mut.mutate({ ...base, star: val, updated_at: new Date().toISOString(), updated_by: 'web' })
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [path, data?.updated_at])

  // Load thumbnail for the selected item
  useEffect(() => {
    let alive = true
    if (!path) { if (thumbUrl) { try { URL.revokeObjectURL(thumbUrl) } catch {} } setThumbUrl(null); return }
    api.getThumb(path).then(b => { if (!alive) return; try { const u = URL.createObjectURL(b); if (thumbUrl) URL.revokeObjectURL(thumbUrl); setThumbUrl(u) } catch {} }).catch(()=>{})
    return () => { alive = false }
  }, [path])

  // Revoke on unmount if still present
  useEffect(() => {
    return () => { if (thumbUrl) { try { URL.revokeObjectURL(thumbUrl) } catch {} } }
  }, [thumbUrl])

  const filename = path ? path.split('/').pop() || path : ''
  const ext = (() => {
    if (filename.includes('.')) return filename.slice(filename.lastIndexOf('.') + 1).toUpperCase()
    const it = (items.find(i=>i.path===path) as any)
    if (it?.type && typeof it.type === 'string' && it.type.includes('/')) return it.type.split('/')[1].toUpperCase()
    return ''
  })()

  if (!enabled) return <div className="inspector"><div className="resizer resizer-right" onMouseDown={onResize} /></div>
  return (
    <div className="inspector">
      {/* Thumbnail */}
      {!multi && (
        <div className="panel" style={{ display:'flex', justifyContent:'center' }}>
          <div style={{ position:'relative', borderRadius:8, overflow:'hidden', border:'1px solid var(--border)', width: 220, height: 160, background:'var(--panel)' }}>
            {thumbUrl && <img src={thumbUrl} alt="thumb" style={{ display:'block', width:'100%', height:'100%', objectFit:'contain' }} />}
            {!!ext && <div style={{ position:'absolute', top:6, left:6, background:'#1b1b1b', border:'1px solid var(--border)', color:'var(--text)', fontSize:12, padding:'2px 6px', borderRadius:6 }}>{ext}</div>}
          </div>
        </div>
      )}
      {/* Filename or multi selection summary */}
      <div className="panel">
        {multi ? (
          <>
            <div className="label">Selection</div>
            <div className="url">{selectedPaths.length} files selected</div>
            <div className="url">Total size: {fmtBytes(totalSize)}</div>
          </>
        ) : (
          <>
            <div className="label">Filename</div>
            <div className="url" title={filename}>{filename}</div>
          </>
        )}
      </div>
      {/* Notes */}
      <div className="panel">
        <div className="label">{multi ? 'Notes (apply to all)' : 'Notes'}</div>
        <textarea
          className="textarea"
          value={notes}
          onChange={e=>setNotes(e.target.value)}
          onBlur={()=> {
            if (multi && selectedPaths.length) {
              bulkUpdateSidecars(selectedPaths, { notes })
            } else {
              mut.mutate({ ...(data||{v:1,tags:[],notes:'',updated_at:'',updated_by:''}), notes, updated_at: new Date().toISOString(), updated_by: 'web' })
            }
          }}
        />
      </div>
      {/* Tags */}
      <div className="panel">
        <div className="label">{multi ? 'Tags (apply to all, comma-separated)' : 'Tags (comma-separated)'}</div>
        <input
          className="input"
          value={tags}
          onChange={e=>setTags(e.target.value)}
          onBlur={()=> {
            const parsed = tags.split(',').map(s=>s.trim()).filter(Boolean)
            if (multi && selectedPaths.length) {
              bulkUpdateSidecars(selectedPaths, { tags: parsed })
            } else {
              mut.mutate({ ...(data||{v:1,tags:[],notes:'',updated_at:'',updated_by:''}), tags: parsed, updated_at: new Date().toISOString(), updated_by: 'web' })
            }
          }}
        />
      </div>
      <div className="panel">
        <div className="label">{multi ? 'Rating (apply to all)' : 'Rating'}</div>
        <div style={{ display:'flex', gap: 6, alignItems:'center' }}>
          {Array.from({ length: 5 }).map((_, i) => {
            const v = i + 1
            const filled = (star ?? 0) >= v
            return (
              <button
                key={v}
                className="button"
                style={{ width: 28, height: 28, padding: 0, borderRadius: 6, background: filled? 'rgba(255, 200, 0, 0.15)': '#1b1b1b', border:'1px solid var(--border)', color: filled? '#ffd166':'#aaa' }}
                onClick={()=>{
                  const val = (star===v && !multi) ? null : v
                  if (multi && selectedPaths.length) {
                    bulkUpdateSidecars(selectedPaths, { star: val })
                  } else {
                    const next = (data||{v:1,tags:[],notes:'',updated_at:'',updated_by:''}) as any
                    mut.mutate({ ...next, star: val, updated_at: new Date().toISOString(), updated_by: 'web' })
                  }
                }}
                title={`${v} star${v>1?'s':''} (key ${v})`}
              >
                {filled ? '★' : '☆'}
              </button>
            )
          })}
          <button className="button" style={{ marginLeft: 8 }} onClick={()=>{
            if (multi && selectedPaths.length) {
              bulkUpdateSidecars(selectedPaths, { star: null })
            } else {
              mut.mutate({ ...(data||{v:1,tags:[],notes:'',updated_at:'',updated_by:''}), star: null, updated_at: new Date().toISOString(), updated_by: 'web' })
            }
          }} title="Clear (key 0)">0</button>
        </div>
      </div>
      {!multi && (
        <div className="panel">
          <div className="label">Details</div>
          <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap:8}}>
            <div>Type<br/><span className="url">{(items.find(i=>i.path===path)||{} as any)?.type}</span></div>
            <div>Size<br/><span className="url">{(() => { const it = items.find(i=>i.path===path) as any; return it? fmtBytes(it.size): '-' })()}</span></div>
            <div>Dims<br/><span className="url">{(() => { const it = items.find(i=>i.path===path) as any; return it? `${it.w}×${it.h}`: '-' })()}</span></div>
          </div>
        </div>
      )}
      {!multi && (
        <div className="panel">
          <div className="label">Source URL</div>
          <div className="url">{path}</div>
        </div>
      )}
      <div className="resizer resizer-right" onMouseDown={onResize} />
    </div>
  )
}

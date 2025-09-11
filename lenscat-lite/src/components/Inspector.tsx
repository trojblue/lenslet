import React, { useEffect, useMemo, useState } from 'react'
import { useSidecar, useUpdateSidecar } from '../api/items'
import { fmtBytes } from '../lib/util'
import { api } from '../api/client'

export default function Inspector({ path, selectedPaths = [], items = [], onResize }:{ path: string | null; selectedPaths?: string[]; items?: { path:string; size:number; w:number; h:number; type:string; }[]; onResize?:(e:React.MouseEvent)=>void }){
  const enabled = !!path
  const { data, isLoading } = useSidecar(path ?? '')
  const mut = useUpdateSidecar(path ?? '')
  const [tags, setTags] = useState<string>('')
  const [notes, setNotes] = useState<string>('')
  const [thumbUrl, setThumbUrl] = useState<string | null>(null)

  const multi = (selectedPaths?.length ?? 0) > 1
  const selectedItems = useMemo(() => {
    if (!Array.isArray(items)) return [] as any[]
    const set = new Set(selectedPaths)
    return items.filter(i => set.has(i.path))
  }, [items, selectedPaths])
  const totalSize = useMemo(() => selectedItems.reduce((a, b:any)=> a + (b.size||0), 0), [selectedItems])

  useEffect(() => { if (data) { setTags((data.tags||[]).join(', ')); setNotes(data.notes||'') } }, [data?.updated_at])

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
      {!multi && (
        <div className="panel">
          <div className="label">Notes</div>
          <textarea className="textarea" value={notes} onChange={e=>setNotes(e.target.value)} onBlur={()=> mut.mutate({ ...(data||{v:1,tags:[],notes:'',updated_at:'',updated_by:''}), notes, updated_at: new Date().toISOString(), updated_by: 'web' })} />
        </div>
      )}
      {/* Tags */}
      {!multi && (
        <div className="panel">
          <div className="label">Tags (comma-separated)</div>
          <input className="input" value={tags} onChange={e=>setTags(e.target.value)} onBlur={()=> mut.mutate({ ...(data||{v:1,tags:[],notes:'',updated_at:'',updated_by:''}), tags: tags.split(',').map(s=>s.trim()).filter(Boolean), updated_at: new Date().toISOString(), updated_by: 'web' })} />
        </div>
      )}
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

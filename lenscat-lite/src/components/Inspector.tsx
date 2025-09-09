import React, { useEffect, useState } from 'react'
import { useSidecar, useUpdateSidecar } from '../api/items'
import { fmtBytes } from '../lib/util'

export default function Inspector({ path, item, onResize }:{ path: string | null; item?: { size:number; w:number; h:number; type:string; }; onResize?:(e:React.MouseEvent)=>void }){
  const enabled = !!path
  const { data, isLoading } = useSidecar(path ?? '')
  const mut = useUpdateSidecar(path ?? '')
  const [tags, setTags] = useState<string>('')
  const [notes, setNotes] = useState<string>('')

  useEffect(() => { if (data) { setTags((data.tags||[]).join(', ')); setNotes(data.notes||'') } }, [data?.updated_at])

  if (!enabled) return <div className="inspector"><div className="resizer resizer-right" onMouseDown={onResize} /></div>
  return (
    <div className="inspector">
      <div className="panel">
        <div className="label">Details</div>
        <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap:8}}>
          <div>Type<br/><span className="url">{item?.type}</span></div>
          <div>Size<br/><span className="url">{item? fmtBytes(item.size): '-'}</span></div>
          <div>Dims<br/><span className="url">{item? `${item.w}×${item.h}`: '-'}</span></div>
        </div>
      </div>
      <div className="panel">
        <div className="label">Tags (comma-separated)</div>
        <input className="input" value={tags} onChange={e=>setTags(e.target.value)} onBlur={()=> mut.mutate({ ...(data||{v:1,tags:[],notes:'',updated_at:'',updated_by:''}), tags: tags.split(',').map(s=>s.trim()).filter(Boolean), updated_at: new Date().toISOString(), updated_by: 'web' })} />
      </div>
      <div className="panel">
        <div className="label">Notes</div>
        <textarea className="textarea" value={notes} onChange={e=>setNotes(e.target.value)} onBlur={()=> mut.mutate({ ...(data||{v:1,tags:[],notes:'',updated_at:'',updated_by:''}), notes, updated_at: new Date().toISOString(), updated_by: 'web' })} />
      </div>
      <div className="panel">
        <div className="label">Source URL</div>
        <div className="url">{path}</div>
      </div>
      <div className="resizer resizer-right" onMouseDown={onResize} />
    </div>
  )
}

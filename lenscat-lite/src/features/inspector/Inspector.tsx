import React, { useEffect, useMemo, useState, useCallback } from 'react'
import { useSidecar, useUpdateSidecar, bulkUpdateSidecars, queueSidecarUpdate } from '../../shared/api/items'
import { fmtBytes } from '../../lib/util'
import { api } from '../../shared/api/client'
import type { Item, StarRating, Sidecar } from '../../lib/types'
import { isInputElement } from '../../lib/keyboard'

interface InspectorItem {
  path: string
  size: number
  w: number
  h: number
  type: string
  star?: number | null
}

interface InspectorProps {
  path: string | null
  selectedPaths?: string[]
  items?: InspectorItem[]
  onResize?: (e: React.MouseEvent) => void
  onStarChanged?: (paths: string[], val: StarRating) => void
}

export default function Inspector({
  path,
  selectedPaths = [],
  items = [],
  onResize,
  onStarChanged,
}: InspectorProps) {
  const enabled = !!path
  const { data, isLoading } = useSidecar(path ?? '')
  const mut = useUpdateSidecar(path ?? '')
  
  // Form state
  const [tags, setTags] = useState('')
  const [notes, setNotes] = useState('')
  const [thumbUrl, setThumbUrl] = useState<string | null>(null)
  
  // Get star from item list (optimistic local value) or sidecar
  const itemStarFromList = useMemo((): number | null => {
    const it = items.find((i) => i.path === path)
    if (it && it.star !== undefined) return it.star
    return null
  }, [items, path])
  
  const star = itemStarFromList ?? data?.star ?? null

  const multi = selectedPaths.length > 1
  
  const selectedItems = useMemo(() => {
    const set = new Set(selectedPaths)
    return items.filter((i) => set.has(i.path))
  }, [items, selectedPaths])
  
  const totalSize = useMemo(
    () => selectedItems.reduce((acc, it) => acc + (it.size || 0), 0),
    [selectedItems]
  )

  // Sync form state when sidecar data changes
  useEffect(() => {
    if (data) {
      setTags((data.tags || []).join(', '))
      setNotes(data.notes || '')
    }
  }, [data?.updated_at])

  // Create a base sidecar for updates
  const createBaseSidecar = useCallback((): Sidecar => {
    return data ?? {
      v: 1,
      tags: [],
      notes: '',
      updated_at: '',
      updated_by: 'web',
    }
  }, [data])

  // Keyboard shortcuts for star ratings (0-5)
  useEffect(() => {
    if (!path) return
    
    const onKey = (e: KeyboardEvent) => {
      if (isInputElement(e.target)) return
      
      const k = e.key
      if (!/^[0-5]$/.test(k)) return
      
      e.preventDefault()
      const val: StarRating = k === '0' ? null : (Number(k) as 1 | 2 | 3 | 4 | 5)
      
      if (multi && selectedPaths.length) {
        bulkUpdateSidecars(selectedPaths, { star: val })
        onStarChanged?.(selectedPaths, val)
      } else {
        const base = createBaseSidecar()
        mut.mutate({
          ...base,
          star: val,
          updated_at: new Date().toISOString(),
          updated_by: 'web',
        })
        onStarChanged?.([path], val)
      }
    }
    
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [path, multi, selectedPaths, createBaseSidecar, mut, onStarChanged])

  // Load thumbnail when path changes
  useEffect(() => {
    if (!path) {
      if (thumbUrl) {
        URL.revokeObjectURL(thumbUrl)
      }
      setThumbUrl(null)
      return
    }
    
    let alive = true
    api.getThumb(path)
      .then((blob) => {
        if (!alive) return
        const url = URL.createObjectURL(blob)
        setThumbUrl((prev) => {
          if (prev) URL.revokeObjectURL(prev)
          return url
        })
      })
      .catch(() => {
        // Ignore thumbnail load errors
      })
    
    return () => {
      alive = false
    }
  }, [path])

  // Clean up thumbnail URL on unmount
  useEffect(() => {
    return () => {
      if (thumbUrl) {
        URL.revokeObjectURL(thumbUrl)
      }
    }
  }, [thumbUrl])

  const filename = path ? path.split('/').pop() || path : ''
  const ext = useMemo(() => {
    if (filename.includes('.')) {
      return filename.slice(filename.lastIndexOf('.') + 1).toUpperCase()
    }
    const it = items.find((i) => i.path === path)
    if (it?.type?.includes('/')) {
      return it.type.split('/')[1].toUpperCase()
    }
    return ''
  }, [filename, items, path])
  
  const currentItem = useMemo(
    () => items.find((i) => i.path === path),
    [items, path]
  )

  if (!enabled) return <div className="inspector"><div className="resizer resizer-right" onMouseDown={onResize} /></div>
  return (
    <div className="inspector">
      {!multi && (
        <div className="panel" style={{ display:'flex', justifyContent:'center' }}>
          <div style={{ position:'relative', borderRadius:8, overflow:'hidden', border:'1px solid var(--border)', width: 220, height: 160, background:'var(--panel)' }}>
            {thumbUrl && <img src={thumbUrl} alt="thumb" style={{ display:'block', width:'100%', height:'100%', objectFit:'contain' }} />}
            {!!ext && <div style={{ position:'absolute', top:6, left:6, background:'#1b1b1b', border:'1px solid var(--border)', color:'var(--text)', fontSize:12, padding:'2px 6px', borderRadius:6 }}>{ext}</div>}
          </div>
        </div>
      )}
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
      <div className="panel">
        <div className="label">{multi ? 'Notes (apply to all)' : 'Notes'}</div>
        <textarea
          className="textarea"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          onBlur={() => {
            if (multi && selectedPaths.length) {
              bulkUpdateSidecars(selectedPaths, { notes })
            } else {
              const base = createBaseSidecar()
              mut.mutate({
                ...base,
                notes,
                updated_at: new Date().toISOString(),
                updated_by: 'web',
              })
            }
          }}
          aria-label={multi ? 'Notes for selected items' : 'Notes'}
        />
      </div>
      <div className="panel">
        <div className="label">{multi ? 'Tags (apply to all, comma-separated)' : 'Tags (comma-separated)'}</div>
        <input
          className="input"
          value={tags}
          onChange={(e) => setTags(e.target.value)}
          onBlur={() => {
            const parsed = tags.split(',').map((s) => s.trim()).filter(Boolean)
            if (multi && selectedPaths.length) {
              bulkUpdateSidecars(selectedPaths, { tags: parsed })
            } else {
              const base = createBaseSidecar()
              mut.mutate({
                ...base,
                tags: parsed,
                updated_at: new Date().toISOString(),
                updated_by: 'web',
              })
            }
          }}
          aria-label={multi ? 'Tags for selected items' : 'Tags'}
        />
      </div>
      <div className="panel">
        <div className="label">{multi ? 'Rating (apply to all)' : 'Rating'}</div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }} role="radiogroup" aria-label="Star rating">
          {[1, 2, 3, 4, 5].map((v) => {
            const filled = (star ?? 0) >= v
            return (
              <button
                key={v}
                className="button"
                style={{
                  width: 28,
                  height: 28,
                  padding: 0,
                  borderRadius: 6,
                  background: filled ? 'rgba(255, 200, 0, 0.15)' : '#1b1b1b',
                  border: '1px solid var(--border)',
                  color: filled ? '#ffd166' : '#aaa',
                }}
                onClick={() => {
                  const val: StarRating = star === v && !multi ? null : (v as 1 | 2 | 3 | 4 | 5)
                  if (multi && selectedPaths.length) {
                    onStarChanged?.(selectedPaths, val)
                    bulkUpdateSidecars(selectedPaths, { star: val })
                  } else if (path) {
                    onStarChanged?.([path], val)
                    queueSidecarUpdate(path, { star: val })
                  }
                }}
                title={`${v} star${v > 1 ? 's' : ''} (key ${v})`}
                aria-label={`${v} star${v > 1 ? 's' : ''}`}
                aria-pressed={star === v}
              >
                {filled ? '★' : '☆'}
              </button>
            )
          })}
          <button
            className="button"
            style={{ marginLeft: 8 }}
            onClick={async () => {
              if (multi && selectedPaths.length) {
                await bulkUpdateSidecars(selectedPaths, { star: null })
                onStarChanged?.(selectedPaths, null)
              } else if (path) {
                const base = createBaseSidecar()
                await mut.mutateAsync({
                  ...base,
                  star: null,
                  updated_at: new Date().toISOString(),
                  updated_by: 'web',
                }).catch(() => {})
                onStarChanged?.([path], null)
              }
            }}
            title="Clear rating (key 0)"
            aria-label="Clear rating"
          >
            0
          </button>
        </div>
      </div>
      {!multi && currentItem && (
        <div className="panel">
          <div className="label">Details</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <div>
              Type
              <br />
              <span className="url">{currentItem.type}</span>
            </div>
            <div>
              Size
              <br />
              <span className="url">{fmtBytes(currentItem.size)}</span>
            </div>
            <div>
              Dimensions
              <br />
              <span className="url">{currentItem.w}×{currentItem.h}</span>
            </div>
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



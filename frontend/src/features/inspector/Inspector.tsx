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

  if (!enabled) return (
    <div className="col-start-3 row-start-2 border-l border-border bg-panel overflow-auto scrollbar-thin relative">
      <div className="absolute top-12 bottom-0 w-1.5 cursor-col-resize z-10 right-[calc(var(--right)-3px)] hover:bg-accent/20" onMouseDown={onResize} />
    </div>
  )

  return (
    <div className="col-start-3 row-start-2 border-l border-border bg-panel overflow-auto scrollbar-thin relative text-sm">
      {/* Header - Filename or Selection */}
      <div className="p-4 border-b border-border bg-bg/30">
        {multi ? (
          <div className="flex flex-col gap-1">
            <div className="text-base font-medium text-text flex items-center gap-2">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-accent"><path d="M20 7h-3a2 2 0 0 1-2-2V2"/><path d="M9 18a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h7l4 4v10a2 2 0 0 1-2 2Z"/><path d="M3 8v10a2 2 0 0 0 2 2h13"/></svg>
              {selectedPaths.length} Selected
            </div>
            <div className="text-xs text-muted font-mono pl-6">{fmtBytes(totalSize)} total</div>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
             <div className="font-medium text-text break-all leading-snug select-text" title={filename}>
                {filename}
             </div>
             <div className="flex items-center gap-3 text-xs text-muted">
                <span className="bg-white/5 px-1.5 rounded border border-white/5">{ext}</span>
                {currentItem && <span>{fmtBytes(currentItem.size)}</span>}
             </div>
          </div>
        )}
      </div>

      {/* Thumbnail Preview (Single only) */}
      {!multi && (
        <div className="p-4 border-b border-border flex justify-center bg-bg/10">
          <div className="relative rounded-lg overflow-hidden border border-border/50 w-full aspect-[4/3] bg-black/20 flex items-center justify-center">
            {thumbUrl ? (
               <img src={thumbUrl} alt="thumb" className="max-w-full max-h-full object-contain shadow-lg" />
            ) : (
               <div className="text-muted opacity-20 text-4xl">🖼</div>
            )}
          </div>
        </div>
      )}

      {/* Basic Info Section */}
      {!multi && currentItem && (
        <div className="p-4 border-b border-border">
          <h3 className="text-xs font-semibold text-muted uppercase tracking-wider mb-3">Basic Info</h3>
          <div className="grid grid-cols-[80px_1fr] gap-y-2 text-[13px]">
            <div className="text-muted">Dimensions</div>
            <div className="font-mono select-text">{currentItem.w} × {currentItem.h}</div>
            
            <div className="text-muted">Path</div>
            <div className="font-mono text-xs text-muted break-all select-text leading-relaxed opacity-80" title={path || ''}>{path}</div>
          </div>
        </div>
      )}

      {/* Tags Section */}
      <div className="p-4 border-b border-border">
        <h3 className="text-xs font-semibold text-muted uppercase tracking-wider mb-3 flex justify-between">
           <span>Tags</span>
           {multi && <span className="text-[10px] bg-accent/10 text-accent px-1 rounded">Multi-edit</span>}
        </h3>
        <input
          className="w-full h-8 bg-black/20 focus:bg-black/40 text-text border border-border rounded-md px-2.5 text-[13px] placeholder:text-muted/40 outline-none focus:border-accent/50 transition-colors"
          placeholder="Add tags (comma separated)..."
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
        />
        <div className="flex flex-wrap gap-1.5 mt-2.5">
           {tags.split(',').filter(t => t.trim()).map(t => (
              <span key={t} className="inline-flex items-center px-2 py-0.5 rounded text-xs bg-accent/10 text-accent/90 border border-accent/20">
                 {t.trim()}
              </span>
           ))}
        </div>
      </div>

      {/* Notes Section */}
      <div className="p-4 border-b border-border">
        <h3 className="text-xs font-semibold text-muted uppercase tracking-wider mb-3">Notes</h3>
        <textarea
          className="w-full bg-black/20 focus:bg-black/40 text-text border border-border rounded-md p-2.5 text-[13px] min-h-[80px] resize-y scrollbar-thin placeholder:text-muted/40 outline-none focus:border-accent/50 transition-colors"
          placeholder="Add notes..."
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
        />
      </div>

      {/* Rating Section */}
      <div className="p-4">
        <h3 className="text-xs font-semibold text-muted uppercase tracking-wider mb-3">Rating</h3>
        <div className="flex gap-1 items-center bg-black/20 p-1.5 rounded-lg w-fit border border-border/50" role="radiogroup" aria-label="Star rating">
          {[1, 2, 3, 4, 5].map((v) => {
            const filled = (star ?? 0) >= v
            return (
              <button
                key={v}
                className={`w-8 h-8 p-0 rounded flex items-center justify-center transition-all duration-150 ${filled ? 'text-[#ffd166] scale-110' : 'text-muted hover:text-text hover:bg-white/5'}`}
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
                title={`${v} star${v > 1 ? 's' : ''}`}
              >
                <span className="text-lg leading-none">{filled ? '★' : '☆'}</span>
              </button>
            )
          })}
          <div className="w-px h-4 bg-border mx-1" />
          <button
            className="px-2 py-1 text-xs text-muted hover:text-text hover:bg-white/5 rounded transition-colors"
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
            title="Clear rating"
          >
            Clear
          </button>
        </div>
      </div>

      <div className="absolute top-12 bottom-0 w-1.5 cursor-col-resize z-10 right-[calc(var(--right)-3px)] hover:bg-accent/20" onMouseDown={onResize} />
    </div>
  )
}

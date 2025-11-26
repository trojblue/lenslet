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
    <div className="col-start-3 row-start-2 border-l border-border bg-panel overflow-auto scrollbar-thin relative">
      {!multi && (
        <div className="p-3 border-b border-border flex justify-center">
          <div className="relative rounded-lg overflow-hidden border border-border w-[220px] h-[160px] bg-panel">
            {thumbUrl && <img src={thumbUrl} alt="thumb" className="block w-full h-full object-contain" />}
            {!!ext && <div className="absolute top-1.5 left-1.5 bg-[#1b1b1b] border border-border text-text text-xs px-1.5 py-0.5 rounded-md">{ext}</div>}
          </div>
        </div>
      )}
      <div className="p-3 border-b border-border">
        {multi ? (
          <>
            <div className="text-muted text-xs uppercase tracking-wide mb-1.5">Selection</div>
            <div className="font-mono text-muted break-all">{selectedPaths.length} files selected</div>
            <div className="font-mono text-muted break-all">Total size: {fmtBytes(totalSize)}</div>
          </>
        ) : (
          <>
            <div className="text-muted text-xs uppercase tracking-wide mb-1.5">Filename</div>
            <div className="font-mono text-muted break-all" title={filename}>{filename}</div>
          </>
        )}
      </div>
      <div className="p-3 border-b border-border">
        <div className="text-muted text-xs uppercase tracking-wide mb-1.5">{multi ? 'Notes (apply to all)' : 'Notes'}</div>
        <textarea
          className="w-full bg-[#1b1b1b] text-text border border-border rounded-lg p-2 min-h-[100px] resize-y scrollbar-thin"
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
      <div className="p-3 border-b border-border">
        <div className="text-muted text-xs uppercase tracking-wide mb-1.5">{multi ? 'Tags (apply to all, comma-separated)' : 'Tags (comma-separated)'}</div>
        <input
          className="w-full h-8 bg-[#1b1b1b] text-text border border-border rounded-lg px-2"
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
      <div className="p-3 border-b border-border">
        <div className="text-muted text-xs uppercase tracking-wide mb-1.5">{multi ? 'Rating (apply to all)' : 'Rating'}</div>
        <div className="flex gap-1.5 items-center" role="radiogroup" aria-label="Star rating">
          {[1, 2, 3, 4, 5].map((v) => {
            const filled = (star ?? 0) >= v
            return (
              <button
                key={v}
                className={`w-7 h-7 p-0 rounded-md border border-border ${filled ? 'bg-[rgba(255,200,0,0.15)] text-[#ffd166]' : 'bg-[#1b1b1b] text-[#aaa]'}`}
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
            className="ml-2 px-2 py-1 bg-[#1b1b1b] text-text border border-border rounded-md"
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
        <div className="p-3 border-b border-border">
          <div className="text-muted text-xs uppercase tracking-wide mb-1.5">Details</div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              Type
              <br />
              <span className="font-mono text-muted break-all">{currentItem.type}</span>
            </div>
            <div>
              Size
              <br />
              <span className="font-mono text-muted break-all">{fmtBytes(currentItem.size)}</span>
            </div>
            <div>
              Dimensions
              <br />
              <span className="font-mono text-muted break-all">{currentItem.w}×{currentItem.h}</span>
            </div>
          </div>
        </div>
      )}
      {!multi && (
        <div className="p-3 border-b border-border">
          <div className="text-muted text-xs uppercase tracking-wide mb-1.5">Source URL</div>
          <div className="font-mono text-muted break-all">{path}</div>
        </div>
      )}
      <div className="absolute top-12 bottom-0 w-1.5 cursor-col-resize z-10 right-[calc(var(--right)-3px)] hover:bg-accent/20" onMouseDown={onResize} />
    </div>
  )
}

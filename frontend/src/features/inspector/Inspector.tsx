import React, { useEffect, useMemo, useState, useCallback } from 'react'
import { useSidecar, useUpdateSidecar, bulkUpdateSidecars, queueSidecarUpdate } from '../../shared/api/items'
import { fmtBytes } from '../../lib/util'
import { api } from '../../shared/api/client'
import { useBlobUrl } from '../../shared/hooks/useBlobUrl'
import type { Item, StarRating, Sidecar } from '../../lib/types'
import { isInputElement } from '../../lib/keyboard'

// Try to turn JSON-looking strings (common in PNG text chunks) back into objects
function normalizeMetadata(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(normalizeMetadata)
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([k, v]) => [k, normalizeMetadata(v)])
    )
  }
  if (typeof value === 'string') {
    const trimmed = value.trim()
    const looksJson =
      (trimmed.startsWith('{') && trimmed.endsWith('}')) ||
      (trimmed.startsWith('[') && trimmed.endsWith(']')) ||
      (trimmed.startsWith('"') && trimmed.endsWith('"'))

    if (looksJson) {
      try {
        const parsed = JSON.parse(trimmed)
        return normalizeMetadata(parsed)
      } catch {
        return value
      }
    }
  }
  return value
}

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function formatMetricValue(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '–'
  const abs = Math.abs(value)
  if (abs >= 1000) return value.toFixed(0)
  if (abs >= 10) return value.toFixed(2)
  return value.toFixed(3)
}

function parseTags(value: string): string[] {
  return value.split(',').map((tag) => tag.trim()).filter(Boolean)
}

// Lightweight JSON-ish syntax highlighting without extra deps
function highlightJson(json: string): string {
  const tokenRe = /(\"(\\u[a-fA-F0-9]{4}|\\[^u]|[^\\"])*\"(?:\s*:)?|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?|\btrue\b|\bfalse\b|\bnull\b)/g
  let result = ''
  let lastIndex = 0

  for (const match of json.matchAll(tokenRe)) {
    const start = match.index ?? 0
    const token = match[0]
    result += escapeHtml(json.slice(lastIndex, start))

    let color = '#cdd3dd' // fallback muted
    if (token.startsWith('"') && token.trimEnd().endsWith(':')) {
      color = '#a7c4ff' // keys
    } else if (token.startsWith('"')) {
      color = '#9ad4b5' // strings
    } else if (/true|false|null/.test(token)) {
      color = '#c4b4f5' // literals
    } else {
      color = '#d7c08c' // numbers
    }

    result += `<span style="color:${color}">${escapeHtml(token)}</span>`
    lastIndex = start + token.length
  }

  result += escapeHtml(json.slice(lastIndex))
  return result
}

interface InspectorItem {
  path: string
  size: number
  w: number
  h: number
  type: string
  source?: string | null
  star?: number | null
  metrics?: Record<string, number | null> | null
}

interface InspectorProps {
  path: string | null
  selectedPaths?: string[]
  items?: InspectorItem[]
  onResize?: (e: React.MouseEvent) => void
  onStarChanged?: (paths: string[], val: StarRating) => void
}

type InspectorSectionKey = 'overview' | 'notes' | 'metadata' | 'basics'

const INSPECTOR_SECTION_KEYS: InspectorSectionKey[] = ['overview', 'notes', 'metadata', 'basics']
const INSPECTOR_SECTION_STORAGE_KEY = 'lenslet.inspector.sections'
const DEFAULT_SECTION_STATE: Record<InspectorSectionKey, boolean> = {
  overview: true,
  notes: true,
  metadata: true,
  basics: true,
}

interface InspectorSectionProps {
  title: string
  open: boolean
  onToggle: () => void
  actions?: React.ReactNode
  children: React.ReactNode
  contentClassName?: string
}

function InspectorSection({
  title,
  open,
  onToggle,
  actions,
  children,
  contentClassName,
}: InspectorSectionProps): JSX.Element {
  const [renderBody, setRenderBody] = useState(open)
  const [bodyState, setBodyState] = useState(open ? 'open' : 'closed')

  useEffect(() => {
    if (open) {
      setRenderBody(true)
      const id = window.requestAnimationFrame(() => setBodyState('open'))
      return () => window.cancelAnimationFrame(id)
    }
    setBodyState('closing')
    const timeoutId = window.setTimeout(() => {
      setRenderBody(false)
      setBodyState('closed')
    }, 140)
    return () => window.clearTimeout(timeoutId)
  }, [open])

  return (
    <div className="border-b border-border">
      <div className="flex items-center justify-between px-3 py-2">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          className="flex items-center gap-2 text-xs uppercase tracking-wide text-muted hover:text-text transition-colors"
        >
          <svg
            width="12"
            height="12"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className={`transition-transform ${open ? 'rotate-90' : ''}`}
            aria-hidden="true"
          >
            <path d="m9 18 6-6-6-6" />
          </svg>
          <span>{title}</span>
        </button>
        {actions}
      </div>
      {renderBody && (
        <div className="inspector-section-body" data-state={bodyState} aria-hidden={!open}>
          <div className={contentClassName ?? 'px-3 pb-3'}>
            {children}
          </div>
        </div>
      )}
    </div>
  )
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

  const [openSections, setOpenSections] = useState<Record<InspectorSectionKey, boolean>>(DEFAULT_SECTION_STATE)
  const toggleSection = useCallback((key: InspectorSectionKey) => {
    setOpenSections((prev) => ({ ...prev, [key]: !prev[key] }))
  }, [])
  
  // Form state
  const [tags, setTags] = useState('')
  const [notes, setNotes] = useState('')
  const [metaText, setMetaText] = useState('')
  const [metaError, setMetaError] = useState<string | null>(null)
  const [metaState, setMetaState] = useState<'idle' | 'loading' | 'loaded' | 'error'>('idle')
  const [copied, setCopied] = useState(false)
  const [copiedField, setCopiedField] = useState<string | null>(null)
  const [valueHeights, setValueHeights] = useState<Record<string, number>>({})
  
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
    setMetaText('')
    setMetaError(null)
    setMetaState('idle')
    setCopied(false)
  }, [data?.updated_at, path])

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

  const commitSidecar = useCallback((patch: Partial<Omit<Sidecar, 'v' | 'updated_at' | 'updated_by'>>) => {
    if (multi && selectedPaths.length) {
      bulkUpdateSidecars(selectedPaths, patch)
      return
    }
    if (!path) return
    const base = createBaseSidecar()
    mut.mutate({
      ...base,
      ...patch,
      updated_at: new Date().toISOString(),
      updated_by: 'web',
    })
  }, [multi, selectedPaths, path, createBaseSidecar, mut])

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
        commitSidecar({ star: val })
        onStarChanged?.(selectedPaths, val)
        return
      }
      commitSidecar({ star: val })
      onStarChanged?.([path], val)
    }
    
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [path, multi, selectedPaths, commitSidecar, onStarChanged])

  const thumbUrl = useBlobUrl(path ? () => api.getThumb(path) : null, [path])

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
  const sourceValue = useMemo(() => {
    if (!path) return ''
    return currentItem?.source ?? path
  }, [currentItem, path])

  const fetchMetadata = useCallback(async () => {
    if (!path) return
    setMetaState('loading')
    setMetaError(null)
    try {
      const res = await api.getMetadata(path)
      const normalized = normalizeMetadata(res.meta)
      const pretty = JSON.stringify(normalized, null, 2)
      setMetaText(pretty)
      setMetaState('loaded')
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to load metadata'
      setMetaText(msg)
      setMetaError(msg)
      setMetaState('error')
    }
  }, [path])

  const copyMetadata = useCallback(() => {
    if (!metaText) return
    navigator.clipboard?.writeText(metaText).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1200)
    }).catch((err) => {
      const msg = err instanceof Error ? err.message : 'Copy failed'
      setMetaError(msg)
    })
  }, [metaText])

  const highlightedMeta = useMemo(() => (metaText ? highlightJson(metaText) : ''), [metaText])
  const metaContent = metaState === 'loading'
    ? 'Loading metadata…'
    : (metaText || 'PNG metadata not loaded yet.')
  const metaLoaded = metaState === 'loaded' && !!metaText
  const metaHeightClass = metaLoaded ? 'h-48' : 'h-24'

  const metadataActions = !multi ? (
    <div className="flex items-center gap-2 text-xs">
      {metaText && (
        <button
          className="text-muted underline underline-offset-2 hover:text-text disabled:opacity-60 min-w-[48px] text-center"
          onClick={copyMetadata}
          disabled={!metaText}
          title="Copy metadata"
        >
          {copied ? 'Copied' : 'Copy'}
        </button>
      )}
      <button
        className="px-2 py-1 bg-transparent text-muted border border-border/60 rounded-md disabled:opacity-60 hover:border-border hover:text-text transition-colors min-w-[78px]"
        onClick={fetchMetadata}
        disabled={!path || metaState === 'loading'}
      >
        {metaState === 'loading' ? 'Loading…' : 'Load meta'}
      </button>
    </div>
  ) : null

  useEffect(() => {
    try {
      const raw = localStorage.getItem(INSPECTOR_SECTION_STORAGE_KEY)
      if (!raw) return
      const parsed = JSON.parse(raw) as Record<string, unknown>
      if (!parsed || typeof parsed !== 'object') return
      const restored: Partial<Record<InspectorSectionKey, boolean>> = {}
      for (const key of INSPECTOR_SECTION_KEYS) {
        if (typeof parsed[key] === 'boolean') restored[key] = parsed[key] as boolean
      }
      if (Object.keys(restored).length > 0) {
        setOpenSections((prev) => ({ ...prev, ...restored }))
      }
    } catch {
      // Ignore localStorage parsing errors
    }
  }, [])

  useEffect(() => {
    try {
      localStorage.setItem(INSPECTOR_SECTION_STORAGE_KEY, JSON.stringify(openSections))
    } catch {
      // Ignore localStorage write errors
    }
  }, [openSections])

  const copyInfo = useCallback((key: string, text: string) => {
    if (!text) return
    navigator.clipboard?.writeText(text).then(() => {
      setCopiedField(key)
      setTimeout(() => setCopiedField((curr) => (curr === key ? null : curr)), 1000)
    }).catch(() => {})
  }, [])

  const rememberHeight = useCallback((key: string, el: HTMLSpanElement | null) => {
    if (el && !valueHeights[key]) {
      const h = el.offsetHeight
      if (h) {
        setValueHeights((prev) => (prev[key] ? prev : { ...prev, [key]: h }))
      }
    }
  }, [valueHeights])

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
            {!!ext && <div className="absolute top-1.5 left-1.5 bg-surface border border-border text-text text-xs px-1.5 py-0.5 rounded-md">{ext}</div>}
          </div>
        </div>
      )}
      <InspectorSection
        title={multi ? 'Selection' : 'Item'}
        open={openSections.overview}
        onToggle={() => toggleSection('overview')}
      >
        {multi ? (
          <>
            <div className="font-mono text-muted break-all">{selectedPaths.length} files selected</div>
            <div className="font-mono text-muted break-all">Total size: {fmtBytes(totalSize)}</div>
          </>
        ) : (
          <div className="font-mono text-text break-all" title={filename}>{filename}</div>
        )}
      </InspectorSection>

      <InspectorSection
        title="Notes & Tags"
        open={openSections.notes}
        onToggle={() => toggleSection('notes')}
        contentClassName="px-3 pb-3 space-y-1.5"
      >
        <textarea
          className="w-full bg-transparent text-text border border-border/60 rounded-md px-2 py-1 min-h-[32px] resize-y scrollbar-thin placeholder:text-muted focus:border-border"
          placeholder="Add notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          onBlur={() => {
            commitSidecar({ notes })
          }}
          aria-label={multi ? 'Notes for selected items' : 'Notes'}
        />
        <div>
          <div className="text-[11px] text-muted mb-1">{multi ? 'Tags (apply to all, comma-separated)' : 'Tags (comma-separated)'}</div>
          <input
            className="w-full h-9 bg-transparent text-text border border-border/60 rounded-md px-2 placeholder:text-muted focus:border-border"
            placeholder="tag1, tag2"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            onBlur={() => {
              commitSidecar({ tags: parseTags(tags) })
            }}
            aria-label={multi ? 'Tags for selected items' : 'Tags'}
          />
        </div>
      </InspectorSection>

      {!multi && (
        <InspectorSection
          title="Metadata"
          open={openSections.metadata}
          onToggle={() => toggleSection('metadata')}
          actions={metadataActions}
        >
          <pre className={`bg-surface-inset text-[11px] font-mono text-muted border border-border rounded-lg p-2 ${metaHeightClass} overflow-auto whitespace-pre-wrap leading-[1.3]`}>
            {metaLoaded ? (
              <code
                className="block whitespace-pre-wrap"
                dangerouslySetInnerHTML={{ __html: highlightedMeta }}
              />
            ) : metaContent}
          </pre>
          {metaError && <div className="text-[11px] text-danger mt-1 break-words">{metaError}</div>}
        </InspectorSection>
      )}

      <InspectorSection
        title="Basics"
        open={openSections.basics}
        onToggle={() => toggleSection('basics')}
      >
        <div className="flex items-center gap-2 text-[12px] mb-1" role="radiogroup" aria-label="Star rating">
          <span className="text-muted w-16 shrink-0">{multi ? 'Rating (all)' : 'Rating'}</span>
          <div className="flex items-center gap-1">
            {[1, 2, 3, 4, 5].map((v) => {
              const filled = (star ?? 0) >= v
              return (
                <button
                  key={v}
                  className={`w-6 h-6 flex items-center justify-center rounded border border-border/60 bg-transparent text-[13px] ${filled ? 'text-star-active' : 'text-star-inactive'} hover:border-border hover:text-star-hover transition-colors`}
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
          </div>
        </div>
        {!multi && currentItem && (
          <div className="text-[12px] space-y-1">
            <div className="flex justify-between">
              <span
                className="text-muted w-20 shrink-0 cursor-pointer"
                onClick={() => copyInfo('dimensions', `${currentItem.w}×${currentItem.h}`)}
              >
                Dimensions
              </span>
              <span
                className="font-mono text-text inline-block text-right min-w-[80px]"
                ref={(el) => rememberHeight('dimensions', el)}
                style={valueHeights.dimensions ? { minHeight: valueHeights.dimensions } : undefined}
              >
                {copiedField === 'dimensions' ? 'Copied' : `${currentItem.w}×${currentItem.h}`}
              </span>
            </div>
            <div className="flex justify-between">
              <span
                className="text-muted w-20 shrink-0 cursor-pointer"
                onClick={() => copyInfo('size', fmtBytes(currentItem.size))}
              >
                Size
              </span>
              <span
                className="font-mono text-text inline-block text-right min-w-[80px]"
                ref={(el) => rememberHeight('size', el)}
                style={valueHeights.size ? { minHeight: valueHeights.size } : undefined}
              >
                {copiedField === 'size' ? 'Copied' : fmtBytes(currentItem.size)}
              </span>
            </div>
            <div className="flex justify-between">
              <span
                className="text-muted w-20 shrink-0 cursor-pointer"
                onClick={() => copyInfo('type', currentItem.type)}
              >
                Type
              </span>
              <span
                className="font-mono text-text break-all text-right inline-block min-w-[80px]"
                ref={(el) => rememberHeight('type', el)}
                style={valueHeights.type ? { minHeight: valueHeights.type } : undefined}
              >
                {copiedField === 'type' ? 'Copied' : currentItem.type}
              </span>
            </div>
            <div className="flex justify-between">
              <span
                className="text-muted w-20 shrink-0 cursor-pointer"
                onClick={() => sourceValue && copyInfo('source', sourceValue)}
              >
                Source
              </span>
              <span
                className="font-mono text-text break-all text-right max-w-[70%] inline-block min-w-[80px]"
                ref={(el) => rememberHeight('source', el)}
                style={valueHeights.source ? { minHeight: valueHeights.source } : undefined}
              >
                {copiedField === 'source' ? 'Copied' : sourceValue}
              </span>
            </div>
            {(() => {
              const metrics = currentItem.metrics || null
              if (!metrics) return null
              const entries = Object.entries(metrics).filter(([, v]) => v != null)
              if (!entries.length) return null
              const sorted = entries.sort(([a], [b]) => a.localeCompare(b))
              const show = sorted.slice(0, 12)
              const remaining = sorted.length - show.length
              return (
                <div className="mt-3">
                  <div className="text-muted text-xs uppercase tracking-wide mb-1">Metrics</div>
                  <div className="space-y-1">
                    {show.map(([key, val]) => (
                      <div key={key} className="flex justify-between">
                        <span className="text-muted w-24 shrink-0">{key}</span>
                        <span className="font-mono text-text text-right">{formatMetricValue(val)}</span>
                      </div>
                    ))}
                    {remaining > 0 && (
                      <div className="text-[11px] text-muted">+{remaining} more</div>
                    )}
                  </div>
                </div>
              )
            })()}
          </div>
        )}
      </InspectorSection>
      <div className="absolute top-12 bottom-0 w-1.5 cursor-col-resize z-10 right-[calc(var(--right)-3px)] hover:bg-accent/20" onMouseDown={onResize} />
    </div>
  )
}

import React, { useEffect, useMemo, useState, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useSidecar, useUpdateSidecar, bulkUpdateSidecars, queueSidecarUpdate, useSidecarConflict, clearConflict, sidecarQueryKey } from '../../shared/api/items'
import { fmtBytes } from '../../lib/util'
import { api, makeIdempotencyKey } from '../../shared/api/client'
import { useBlobUrl } from '../../shared/hooks/useBlobUrl'
import type { Item, SortSpec, StarRating } from '../../lib/types'
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

    let color = 'var(--json-fallback)'
    if (token.startsWith('"') && token.trimEnd().endsWith(':')) {
      color = 'var(--json-key)'
    } else if (token.startsWith('"')) {
      color = 'var(--json-string)'
    } else if (/true|false|null/.test(token)) {
      color = 'var(--json-literal)'
    } else {
      color = 'var(--json-number)'
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
  sortSpec?: SortSpec
  onFindSimilar?: () => void
  embeddingsAvailable?: boolean
  embeddingsLoading?: boolean
}

type InspectorSectionKey = 'overview' | 'basics' | 'metadata' | 'notes'

const INSPECTOR_SECTION_KEYS: InspectorSectionKey[] = ['overview', 'basics', 'metadata', 'notes']
const INSPECTOR_SECTION_STORAGE_KEY = 'lenslet.inspector.sections'
const INSPECTOR_METRICS_EXPANDED_KEY = 'lenslet.inspector.metricsExpanded'
const METRICS_PREVIEW_LIMIT = 12
const DEFAULT_SECTION_STATE: Record<InspectorSectionKey, boolean> = {
  overview: true,
  metadata: true,
  basics: true,
  notes: true,
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
    <div className="border-b border-border/60">
      <div className="flex items-center justify-between px-3 py-2.5">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          className="flex items-center gap-2 inspector-section-title hover:text-text transition-colors"
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
  sortSpec,
  onFindSimilar,
  embeddingsAvailable = false,
  embeddingsLoading = false,
}: InspectorProps) {
  const enabled = !!path
  const { data, isLoading } = useSidecar(path ?? '')
  const mut = useUpdateSidecar(path ?? '')
  const qc = useQueryClient()

  const [openSections, setOpenSections] = useState<Record<InspectorSectionKey, boolean>>(DEFAULT_SECTION_STATE)
  const toggleSection = useCallback((key: InspectorSectionKey) => {
    setOpenSections((prev) => ({ ...prev, [key]: !prev[key] }))
  }, [])
  
  const [metricsExpanded, setMetricsExpanded] = useState(false)
  const multi = selectedPaths.length > 1

  const canFindSimilar = !!onFindSimilar && embeddingsAvailable && !multi
  const findSimilarDisabledReason = (() => {
    if (!onFindSimilar) return null
    if (!embeddingsAvailable) return embeddingsLoading ? 'Loading embeddings...' : 'No embeddings detected.'
    if (multi) return 'Select a single image to search.'
    return null
  })()

  // Form state
  const [tags, setTags] = useState('')
  const [notes, setNotes] = useState('')
  const [metaText, setMetaText] = useState('')
  const [metaError, setMetaError] = useState<string | null>(null)
  const [metaState, setMetaState] = useState<'idle' | 'loading' | 'loaded' | 'error'>('idle')
  const [metaCopied, setMetaCopied] = useState(false)
  const [copiedField, setCopiedField] = useState<string | null>(null)
  const [valueHeights, setValueHeights] = useState<Record<string, number>>({})
  
  // Get star from item list (optimistic local value) or sidecar
  const itemStarFromList = useMemo((): number | null => {
    const it = items.find((i) => i.path === path)
    if (it && it.star !== undefined) return it.star
    return null
  }, [items, path])
  
  const star = itemStarFromList ?? data?.star ?? null
  const conflict = useSidecarConflict(!multi ? path : null)
  const conflictFields = {
    tags: !!conflict?.pending.set_tags,
    notes: conflict?.pending.set_notes !== undefined,
    star: conflict?.pending.set_star !== undefined,
  }
  
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
    setMetaCopied(false)
  }, [data?.updated_at, path])

  const commitSidecar = useCallback((patch: { notes?: string; tags?: string[]; star?: StarRating | null }) => {
    if (multi && selectedPaths.length) {
      bulkUpdateSidecars(selectedPaths, patch)
      return
    }
    if (!path) return
    const baseVersion = data?.version ?? 1
    mut.mutate({ patch, baseVersion, idempotencyKey: makeIdempotencyKey('patch') })
  }, [multi, selectedPaths, path, data?.version, mut])

  const applyConflict = useCallback(() => {
    if (!conflict || !path) return
    const patch: { notes?: string; tags?: string[]; star?: StarRating | null } = {}
    if (conflict.pending.set_tags !== undefined) {
      patch.tags = parseTags(tags)
    }
    if (conflict.pending.set_notes !== undefined) {
      patch.notes = notes
    }
    if (conflict.pending.set_star !== undefined) {
      patch.star = star ?? null
    }
    const baseVersion = conflict.current.version ?? 1
    mut.mutate({ patch, baseVersion, idempotencyKey: makeIdempotencyKey('patch') })
  }, [conflict, path, tags, notes, star, mut])

  const keepTheirs = useCallback(() => {
    if (!conflict || !path) return
    const current = conflict.current
    setTags((current.tags || []).join(', '))
    setNotes(current.notes || '')
    qc.setQueryData(sidecarQueryKey(path), current)
    clearConflict(path)
    onStarChanged?.([path], current.star ?? null)
  }, [conflict, path, qc, onStarChanged])

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
      const pretty = JSON.stringify(normalized, null, 1)
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
      setMetaCopied(true)
      setTimeout(() => setMetaCopied(false), 1200)
    }).catch((err) => {
      const msg = err instanceof Error ? err.message : 'Copy failed'
      setMetaError(msg)
    })
  }, [metaText])

  const highlightedMeta = useMemo(() => (metaText ? highlightJson(metaText) : ''), [metaText])
  const metaContent = metaState === 'loading'
    ? 'Loading metadata…'
    : (metaText || 'PNG metadata not loaded yet.')
  const metadataLoading = metaState === 'loading'
  const metaLoaded = metaState === 'loaded' && !!metaText
  const metaHeightClass = metaLoaded ? 'h-48' : 'h-24'
  const metadataActionLabel = metadataLoading
    ? 'Loading…'
    : metaLoaded
      ? (metaCopied ? 'Copied' : 'Copy')
      : 'Load meta'
  const handleMetadataAction = metaLoaded ? copyMetadata : fetchMetadata

  const metadataActions = !multi ? (
    <div className="flex items-center gap-2 text-xs">
      <button
        className="px-2 py-1 bg-transparent text-muted border border-border/60 rounded-md disabled:opacity-60 hover:border-border hover:text-text transition-colors min-w-[78px]"
        onClick={handleMetadataAction}
        disabled={!path || metadataLoading}
      >
        {metadataActionLabel}
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

  useEffect(() => {
    try {
      const raw = localStorage.getItem(INSPECTOR_METRICS_EXPANDED_KEY)
      if (raw === '1' || raw === 'true') {
        setMetricsExpanded(true)
      } else if (raw === '0' || raw === 'false') {
        setMetricsExpanded(false)
      }
    } catch {
      // Ignore localStorage parsing errors
    }
  }, [])

  useEffect(() => {
    try {
      localStorage.setItem(INSPECTOR_METRICS_EXPANDED_KEY, metricsExpanded ? '1' : '0')
    } catch {
      // Ignore localStorage write errors
    }
  }, [metricsExpanded])

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

  const resizeHandleClass = 'toolbar-offset absolute bottom-0 left-0 w-1.5 cursor-col-resize z-10 hover:bg-accent/20'

  if (!enabled) return (
    <div className="app-right-panel col-start-3 row-start-2 border-l border-border bg-panel overflow-auto scrollbar-thin relative">
      <div className={resizeHandleClass} onMouseDown={onResize} />
    </div>
  )

  return (
    <div className="app-right-panel col-start-3 row-start-2 border-l border-border bg-panel overflow-auto scrollbar-thin relative">
      {!multi && (
        <div className="p-3 border-b border-border flex justify-center">
          <div className="relative rounded-lg overflow-hidden border border-border w-[220px] h-[160px] bg-panel select-none">
            {thumbUrl && <img src={thumbUrl} alt="thumb" className="block w-full h-full object-contain" />}
            {!!ext && <div className="absolute top-1.5 left-1.5 bg-surface border border-border text-text text-xs px-1.5 py-0.5 rounded-md select-none">{ext}</div>}
          </div>
        </div>
      )}
      <InspectorSection
        title={multi ? 'Selection' : 'Item'}
        open={openSections.overview}
        onToggle={() => toggleSection('overview')}
        contentClassName="px-3 pb-3 space-y-2"
        actions={onFindSimilar && (
          <button
            type="button"
            className="btn btn-sm"
            onClick={onFindSimilar}
            disabled={!canFindSimilar}
            title={findSimilarDisabledReason ?? 'Find similar'}
          >
            Find similar
          </button>
        )}
      >
        {multi ? (
          <div className="grid grid-cols-2 gap-2">
            <div className="inspector-field">
              <div className="inspector-field-label">Selected</div>
              <div className="inspector-field-value">{selectedPaths.length} files</div>
            </div>
            <div className="inspector-field">
              <div className="inspector-field-label">Total size</div>
              <div className="inspector-field-value">{fmtBytes(totalSize)}</div>
            </div>
          </div>
        ) : (
          <div className="inspector-field">
            <div className="inspector-field-label">Filename</div>
            <div className="inspector-field-value break-all" title={filename}>{filename}</div>
          </div>
        )}
        {findSimilarDisabledReason && (
          <div className="text-[11px] text-muted">{findSimilarDisabledReason}</div>
        )}
      </InspectorSection>

      <InspectorSection
        title="Basics"
        open={openSections.basics}
        onToggle={() => toggleSection('basics')}
      >
        <div className="flex items-center gap-2 text-xs mb-1" role="radiogroup" aria-label="Star rating">
          <span className="ui-kv-label w-16 shrink-0">{multi ? 'Rating (all)' : 'Rating'}</span>
          <div className="flex items-center gap-1">
            {[1, 2, 3, 4, 5].map((v) => {
              const filled = (star ?? 0) >= v
              return (
                <button
                  key={v}
                  className={`w-6 h-6 flex items-center justify-center rounded-lg border border-border/60 bg-transparent text-[13px] ${filled ? 'text-star-active' : 'text-star-inactive'} hover:border-border hover:text-star-hover transition-colors`}
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
        {!multi && conflict && conflictFields.star && (
          <div className="ui-banner ui-banner-danger mt-2 text-[11px] flex items-center justify-between gap-2">
            <span>Rating conflict.</span>
            <div className="flex items-center gap-2">
              <button className="btn btn-sm" onClick={applyConflict}>
                Apply again
              </button>
              <button className="btn btn-sm btn-ghost" onClick={keepTheirs}>
                Keep theirs
              </button>
            </div>
          </div>
        )}
        {!multi && currentItem && (
          <div className="text-[12px] space-y-1.5 leading-relaxed">
            <div className="ui-kv-row">
              <span
                className="ui-kv-label ui-kv-label-action w-20 shrink-0"
                onClick={() => copyInfo('dimensions', `${currentItem.w}×${currentItem.h}`)}
              >
                Dimensions
              </span>
              <span
                className="ui-kv-value inline-block text-right min-w-[80px]"
                ref={(el) => rememberHeight('dimensions', el)}
                style={valueHeights.dimensions ? { minHeight: valueHeights.dimensions } : undefined}
              >
                {copiedField === 'dimensions' ? 'Copied' : `${currentItem.w}×${currentItem.h}`}
              </span>
            </div>
            <div className="ui-kv-row">
              <span
                className="ui-kv-label ui-kv-label-action w-20 shrink-0"
                onClick={() => copyInfo('size', fmtBytes(currentItem.size))}
              >
                Size
              </span>
              <span
                className="ui-kv-value inline-block text-right min-w-[80px]"
                ref={(el) => rememberHeight('size', el)}
                style={valueHeights.size ? { minHeight: valueHeights.size } : undefined}
              >
                {copiedField === 'size' ? 'Copied' : fmtBytes(currentItem.size)}
              </span>
            </div>
            <div className="ui-kv-row">
              <span
                className="ui-kv-label ui-kv-label-action w-20 shrink-0"
                onClick={() => copyInfo('type', currentItem.type)}
              >
                Type
              </span>
              <span
                className="ui-kv-value break-all text-right inline-block min-w-[80px]"
                ref={(el) => rememberHeight('type', el)}
                style={valueHeights.type ? { minHeight: valueHeights.type } : undefined}
              >
                {copiedField === 'type' ? 'Copied' : currentItem.type}
              </span>
            </div>
            <div className="ui-kv-row">
              <span
                className="ui-kv-label ui-kv-label-action w-20 shrink-0"
                onClick={() => sourceValue && copyInfo('source', sourceValue)}
              >
                Source
              </span>
              <span
                className="ui-kv-value inspector-value-clamp break-words text-right max-w-[70%] inline-block min-w-[80px]"
                ref={(el) => rememberHeight('source', el)}
                style={valueHeights.source ? { minHeight: valueHeights.source } : undefined}
                title={sourceValue}
              >
                {copiedField === 'source' ? 'Copied' : sourceValue}
              </span>
            </div>
            {(() => {
              const metrics = currentItem.metrics || null
              if (!metrics) return null
              const entries = Object.entries(metrics).filter(([, v]) => v != null)
              if (!entries.length) return null
              const highlightKey = sortSpec?.kind === 'metric' ? sortSpec.key : null
              const sorted = [...entries].sort(([a], [b]) => a.localeCompare(b))
              let ordered = sorted
              if (highlightKey) {
                const idx = sorted.findIndex(([key]) => key === highlightKey)
                if (idx > 0) {
                  ordered = [sorted[idx], ...sorted.slice(0, idx), ...sorted.slice(idx + 1)]
                }
              }
              const canToggle = ordered.length > METRICS_PREVIEW_LIMIT
              const showAll = metricsExpanded || !canToggle
              const show = showAll ? ordered : ordered.slice(0, METRICS_PREVIEW_LIMIT)
              const remaining = ordered.length - METRICS_PREVIEW_LIMIT
              return (
                <div className="mt-3">
                  <div className="ui-subsection-title mb-1">Metrics</div>
                  <div className="space-y-1">
                    {show.map(([key, val]) => {
                      const isHighlighted = highlightKey === key
                      return (
                        <div key={key} className="ui-kv-row">
                          <span className={`w-24 shrink-0 ${isHighlighted ? 'text-accent font-medium' : 'ui-kv-label'}`}>
                            {key}
                          </span>
                          <span className={`ui-kv-value text-right ${isHighlighted ? 'text-accent font-medium' : ''}`}>
                            {formatMetricValue(val)}
                          </span>
                        </div>
                      )
                    })}
                    {canToggle && (
                      <button
                        type="button"
                        className="text-[11px] text-muted underline underline-offset-2 hover:text-text"
                        onClick={() => setMetricsExpanded((prev) => !prev)}
                        aria-expanded={metricsExpanded}
                      >
                        {metricsExpanded ? 'Show less' : `+${remaining} more`}
                      </button>
                    )}
                  </div>
                </div>
              )
            })()}
          </div>
        )}
      </InspectorSection>

      {!multi && (
        <InspectorSection
          title="Metadata"
          open={openSections.metadata}
          onToggle={() => toggleSection('metadata')}
          actions={metadataActions}
        >
          <pre className={`ui-code-block ${metaHeightClass} overflow-auto whitespace-pre-wrap`}>
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
        title="Notes & Tags"
        open={openSections.notes}
        onToggle={() => toggleSection('notes')}
        contentClassName="px-3 pb-3 space-y-2"
      >
        {!multi && conflict && (conflictFields.tags || conflictFields.notes) && (
          <div className="ui-banner ui-banner-danger text-xs">
            <div className="font-semibold">Conflicting edits detected.</div>
            <div className="text-[11px] text-muted mt-0.5">
              Your changes were not saved because this item was updated elsewhere.
            </div>
            <div className="flex items-center gap-2 mt-2">
              <button className="btn btn-sm" onClick={applyConflict}>
                Apply my changes again
              </button>
              <button className="btn btn-sm btn-ghost" onClick={keepTheirs}>
                Keep theirs
              </button>
            </div>
          </div>
        )}
        <textarea
          className="ui-textarea inspector-input w-full scrollbar-thin"
          placeholder="Add notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          onBlur={() => {
            commitSidecar({ notes })
          }}
          aria-label={multi ? 'Notes for selected items' : 'Notes'}
        />
        <div>
          <div className="ui-label">{multi ? 'Tags (apply to all, comma-separated)' : 'Tags (comma-separated)'}</div>
          <input
            className="ui-input inspector-input w-full"
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
      <div className={resizeHandleClass} onMouseDown={onResize} />
    </div>
  )
}

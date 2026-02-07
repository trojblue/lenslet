import React, { useEffect, useMemo, useState, useCallback, useRef } from 'react'
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
    let jsonKey: string | null = null
    if (token.startsWith('"') && token.trimEnd().endsWith(':')) {
      color = 'var(--json-key)'
      const literal = token.trim().replace(/:\s*$/, '')
      try {
        jsonKey = JSON.parse(literal)
      } catch {
        jsonKey = null
      }
    } else if (token.startsWith('"')) {
      color = 'var(--json-string)'
    } else if (/true|false|null/.test(token)) {
      color = 'var(--json-literal)'
    } else {
      color = 'var(--json-number)'
    }

    if (jsonKey) {
      result += `<span class="ui-json-key" data-json-key="${escapeHtml(jsonKey)}" style="color:${color}">${escapeHtml(token)}</span>`
    } else {
      result += `<span style="color:${color}">${escapeHtml(token)}</span>`
    }
    lastIndex = start + token.length
  }

  result += escapeHtml(json.slice(lastIndex))
  return result
}

function toComparableString(value: unknown): string {
  if (value == null) return String(value)
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) {
    return `[${value.map(toComparableString).join(',')}]`
  }
  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, val]) => `${key}:${toComparableString(val)}`)
    return `{${entries.join(',')}}`
  }
  return String(value)
}

function formatMetaValue(value: unknown): string {
  if (value == null) return '—'
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  try {
    return JSON.stringify(value, null, 1)
  } catch {
    return String(value)
  }
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

function appendPath(base: string, key: string | number): string {
  if (typeof key === 'number') {
    return base ? `${base}[${key}]` : `[${key}]`
  }
  const safe = /^[A-Za-z0-9_$-]+$/.test(key)
  if (!base) return safe ? key : `["${key}"]`
  return safe ? `${base}.${key}` : `${base}["${key}"]`
}

function flattenMeta(
  value: unknown,
  basePath: string,
  out: Map<string, unknown>,
  depth: number,
  opts: { maxDepth: number; maxArray: number; skipPilInfo: boolean }
): void {
  if (opts.skipPilInfo) {
    if (basePath === 'pil_info') return
    if (basePath.startsWith('pil_info.')) return
    if (basePath.startsWith('pil_info[')) return
  }

  if (depth >= opts.maxDepth) {
    out.set(basePath || '(root)', value)
    return
  }

  if (Array.isArray(value)) {
    if (!value.length) {
      out.set(basePath || '(root)', [])
      return
    }
    if (value.length > opts.maxArray) {
      out.set(basePath || '(root)', value)
      return
    }
    value.forEach((item, idx) => flattenMeta(item, appendPath(basePath, idx), out, depth + 1, opts))
    return
  }

  if (isPlainObject(value)) {
    const keys = Object.keys(value).sort((a, b) => a.localeCompare(b))
    if (!keys.length) {
      out.set(basePath || '(root)', {})
      return
    }
    for (const key of keys) {
      if (opts.skipPilInfo && !basePath && key === 'pil_info') continue
      flattenMeta(value[key], appendPath(basePath, key), out, depth + 1, opts)
    }
    return
  }

  out.set(basePath || '(root)', value)
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
  compareActive?: boolean
  compareA?: Item | null
  compareB?: Item | null
  onResize?: (e: React.MouseEvent) => void
  onStarChanged?: (paths: string[], val: StarRating) => void
  sortSpec?: SortSpec
  onFindSimilar?: () => void
  embeddingsAvailable?: boolean
  embeddingsLoading?: boolean
  onLocalTypingChange?: (active: boolean) => void
}

type InspectorSectionKey = 'overview' | 'compare' | 'basics' | 'metadata' | 'notes'

const INSPECTOR_SECTION_KEYS: InspectorSectionKey[] = ['overview', 'compare', 'basics', 'metadata', 'notes']
const INSPECTOR_SECTION_STORAGE_KEY = 'lenslet.inspector.sections'
const INSPECTOR_METRICS_EXPANDED_KEY = 'lenslet.inspector.metricsExpanded'
const METRICS_PREVIEW_LIMIT = 12
const COMPARE_DIFF_LIMIT = 120
const COMPARE_DIFF_MAX_DEPTH = 8
const COMPARE_DIFF_MAX_ARRAY = 80
const DEFAULT_SECTION_STATE: Record<InspectorSectionKey, boolean> = {
  overview: true,
  compare: true,
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
  compareActive = false,
  compareA = null,
  compareB = null,
  onResize,
  onStarChanged,
  sortSpec,
  onFindSimilar,
  embeddingsAvailable = false,
  embeddingsLoading = false,
  onLocalTypingChange,
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
  const [metaRaw, setMetaRaw] = useState<Record<string, unknown> | null>(null)
  const [metaError, setMetaError] = useState<string | null>(null)
  const [metaState, setMetaState] = useState<'idle' | 'loading' | 'loaded' | 'error'>('idle')
  const [metaCopied, setMetaCopied] = useState(false)
  const [metaKeyCopied, setMetaKeyCopied] = useState<string | null>(null)
  const metaKeyCopyTimeoutRef = useRef<number | null>(null)
  const [showPilInfo, setShowPilInfo] = useState(false)
  const [compareMetaState, setCompareMetaState] = useState<'idle' | 'loading' | 'loaded' | 'error'>('idle')
  const [compareMetaError, setCompareMetaError] = useState<string | null>(null)
  const [compareMetaA, setCompareMetaA] = useState<Record<string, unknown> | null>(null)
  const [compareMetaB, setCompareMetaB] = useState<Record<string, unknown> | null>(null)
  const [compareIncludePilInfo, setCompareIncludePilInfo] = useState(false)
  const compareMetaRequestIdRef = useRef(0)
  const [copiedField, setCopiedField] = useState<string | null>(null)
  const [valueHeights, setValueHeights] = useState<Record<string, number>>({})
  const localTypingActiveRef = useRef(false)

  const notifyLocalTyping = useCallback((active: boolean) => {
    if (localTypingActiveRef.current === active) return
    localTypingActiveRef.current = active
    onLocalTypingChange?.(active)
  }, [onLocalTypingChange])
  
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
    setMetaRaw(null)
    setMetaError(null)
    setMetaState('idle')
    setMetaCopied(false)
    setMetaKeyCopied(null)
    if (metaKeyCopyTimeoutRef.current) {
      window.clearTimeout(metaKeyCopyTimeoutRef.current)
      metaKeyCopyTimeoutRef.current = null
    }
    setShowPilInfo(false)
    notifyLocalTyping(false)
  }, [data?.updated_at, notifyLocalTyping, path])

  useEffect(() => {
    return () => {
      if (metaKeyCopyTimeoutRef.current) {
        window.clearTimeout(metaKeyCopyTimeoutRef.current)
        metaKeyCopyTimeoutRef.current = null
      }
      notifyLocalTyping(false)
    }
  }, [notifyLocalTyping])

  const commitSidecar = useCallback((patch: { notes?: string; tags?: string[]; star?: StarRating | null }) => {
    if (multi && selectedPaths.length) {
      bulkUpdateSidecars(selectedPaths, patch)
      return
    }
    if (!path) return
    const baseVersion = data?.version ?? 1
    mut.mutate({ patch, baseVersion, idempotencyKey: makeIdempotencyKey('patch') })
  }, [multi, selectedPaths, path, data?.version, mut])

  const handleNotesChange = useCallback((value: string) => {
    setNotes(value)
    notifyLocalTyping(true)
  }, [notifyLocalTyping])

  const handleNotesBlur = useCallback(() => {
    commitSidecar({ notes })
    notifyLocalTyping(false)
  }, [commitSidecar, notes, notifyLocalTyping])

  const handleTagsChange = useCallback((value: string) => {
    setTags(value)
    notifyLocalTyping(true)
  }, [notifyLocalTyping])

  const handleTagsBlur = useCallback(() => {
    commitSidecar({ tags: parseTags(tags) })
    notifyLocalTyping(false)
  }, [commitSidecar, notifyLocalTyping, tags])

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

  const comparePathA = compareA?.path ?? null
  const comparePathB = compareB?.path ?? null
  const compareReady = compareActive && !!comparePathA && !!comparePathB
  const compareLabelA = compareA?.name ?? comparePathA ?? 'A'
  const compareLabelB = compareB?.name ?? comparePathB ?? 'B'

  const fetchMetadata = useCallback(async () => {
    if (!path) return
    setMetaState('loading')
    setMetaError(null)
    try {
      const res = await api.getMetadata(path)
      setMetaRaw(res.meta)
      setMetaState('loaded')
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to load metadata'
      setMetaRaw(null)
      setMetaError(msg)
      setMetaState('error')
    }
  }, [path])

  const fetchCompareMetadata = useCallback(async (aPath: string, bPath: string) => {
    const requestId = compareMetaRequestIdRef.current + 1
    compareMetaRequestIdRef.current = requestId
    setCompareMetaState('loading')
    setCompareMetaError(null)
    try {
      const [aRes, bRes] = await Promise.all([api.getMetadata(aPath), api.getMetadata(bPath)])
      if (compareMetaRequestIdRef.current !== requestId) return
      setCompareMetaA(aRes.meta)
      setCompareMetaB(bRes.meta)
      setCompareMetaState('loaded')
    } catch (err) {
      if (compareMetaRequestIdRef.current !== requestId) return
      const msg = err instanceof Error ? err.message : 'Failed to load metadata'
      setCompareMetaA(null)
      setCompareMetaB(null)
      setCompareMetaError(msg)
      setCompareMetaState('error')
    }
  }, [])

  useEffect(() => {
    if (!compareReady || !comparePathA || !comparePathB) {
      compareMetaRequestIdRef.current += 1
      setCompareMetaState('idle')
      setCompareMetaError(null)
      setCompareMetaA(null)
      setCompareMetaB(null)
      return
    }
    setCompareIncludePilInfo(false)
    fetchCompareMetadata(comparePathA, comparePathB)
  }, [compareReady, comparePathA, comparePathB, fetchCompareMetadata])

  const metaRawText = useMemo(() => {
    if (!metaRaw) return ''
    try {
      return JSON.stringify(metaRaw, null, 1)
    } catch {
      return ''
    }
  }, [metaRaw])

  const metaDisplayText = useMemo(() => {
    if (!metaRaw) return ''
    const normalized = normalizeMetadata(metaRaw)
    if (
      !showPilInfo &&
      normalized &&
      typeof normalized === 'object' &&
      !Array.isArray(normalized) &&
      'pil_info' in normalized
    ) {
      const ordered: Record<string, unknown> = {}
      for (const [key, value] of Object.entries(normalized as Record<string, unknown>)) {
        ordered[key] = key === 'pil_info'
          ? 'Hidden (toggle Show PIL info to expand)'
          : value
      }
      return JSON.stringify(ordered, null, 1)
    }
    return JSON.stringify(normalized, null, 1)
  }, [metaRaw, showPilInfo])

  const copyMetadata = useCallback(() => {
    if (!metaRawText) return
    navigator.clipboard?.writeText(metaRawText).then(() => {
      setMetaCopied(true)
      setTimeout(() => setMetaCopied(false), 1200)
    }).catch((err) => {
      const msg = err instanceof Error ? err.message : 'Copy failed'
      setMetaError(msg)
    })
  }, [metaRawText])

  const copyMetadataKey = useCallback((key: string) => {
    if (!key) return
    navigator.clipboard?.writeText(key).then(() => {
      setMetaKeyCopied(key)
      if (metaKeyCopyTimeoutRef.current) {
        window.clearTimeout(metaKeyCopyTimeoutRef.current)
      }
      metaKeyCopyTimeoutRef.current = window.setTimeout(() => {
        setMetaKeyCopied(null)
        metaKeyCopyTimeoutRef.current = null
      }, 900)
    }).catch(() => {})
  }, [])

  const handleMetaClick = useCallback((e: React.MouseEvent) => {
    const target = e.target as HTMLElement | null
    if (!target) return
    const keyEl = target.closest('[data-json-key]') as HTMLElement | null
    if (!keyEl) return
    const key = keyEl.getAttribute('data-json-key')
    if (!key) return
    e.preventDefault()
    copyMetadataKey(key)
  }, [copyMetadataKey])

  const highlightedMeta = useMemo(() => (metaDisplayText ? highlightJson(metaDisplayText) : ''), [metaDisplayText])
  const metaContent = metaState === 'loading'
    ? 'Loading metadata…'
    : metaState === 'error' && metaError
      ? metaError
      : (metaDisplayText || 'PNG metadata not loaded yet.')
  const metadataLoading = metaState === 'loading'
  const metaLoaded = metaState === 'loaded' && !!metaRawText
  const metaHeightClass = metaLoaded ? 'h-48' : 'h-24'
  const metadataActionLabel = metadataLoading
    ? 'Loading…'
    : metaLoaded
      ? (metaCopied ? 'Copied' : 'Copy')
      : 'Load meta'
  const handleMetadataAction = metaLoaded ? copyMetadata : fetchMetadata

  const hasPilInfo = !!metaRaw && typeof metaRaw === 'object' && !Array.isArray(metaRaw) && 'pil_info' in metaRaw

  const metadataActions = !multi ? (
    <div className="flex items-center gap-2 text-xs">
      {metaLoaded && hasPilInfo && (
        <button
          className="px-2 py-1 bg-transparent text-muted border border-border/60 rounded-md disabled:opacity-60 hover:border-border hover:text-text transition-colors"
          onClick={() => setShowPilInfo((prev) => !prev)}
          disabled={!metaLoaded}
        >
          {showPilInfo ? 'Hide PIL info' : 'Show PIL info'}
        </button>
      )}
      <button
        className="px-2 py-1 bg-transparent text-muted border border-border/60 rounded-md disabled:opacity-60 hover:border-border hover:text-text transition-colors min-w-[78px]"
        onClick={handleMetadataAction}
        disabled={!path || metadataLoading}
      >
        {metadataActionLabel}
      </button>
    </div>
  ) : null

  const handleCompareReload = useCallback(() => {
    if (!comparePathA || !comparePathB) return
    fetchCompareMetadata(comparePathA, comparePathB)
  }, [comparePathA, comparePathB, fetchCompareMetadata])

  const compareDiff = useMemo(() => {
    if (!compareMetaA || !compareMetaB) return null
    const normalizedA = normalizeMetadata(compareMetaA)
    const normalizedB = normalizeMetadata(compareMetaB)
    const mapA = new Map<string, unknown>()
    const mapB = new Map<string, unknown>()
    const opts = { maxDepth: COMPARE_DIFF_MAX_DEPTH, maxArray: COMPARE_DIFF_MAX_ARRAY, skipPilInfo: !compareIncludePilInfo }
    flattenMeta(normalizedA, '', mapA, 0, opts)
    flattenMeta(normalizedB, '', mapB, 0, opts)
    const keys = new Set([...mapA.keys(), ...mapB.keys()])
    const entries: Array<{ key: string; kind: 'different' | 'onlyA' | 'onlyB'; aText: string; bText: string }> = []
    let onlyA = 0
    let onlyB = 0
    let different = 0
    const sortedKeys = Array.from(keys).sort((a, b) => a.localeCompare(b))
    for (const key of sortedKeys) {
      if (!compareIncludePilInfo && (key === 'pil_info' || key.startsWith('pil_info.') || key.startsWith('pil_info['))) {
        continue
      }
      const hasA = mapA.has(key)
      const hasB = mapB.has(key)
      if (!hasA && hasB) {
        onlyB += 1
        entries.push({ key, kind: 'onlyB', aText: '—', bText: formatMetaValue(mapB.get(key)) })
        continue
      }
      if (hasA && !hasB) {
        onlyA += 1
        entries.push({ key, kind: 'onlyA', aText: formatMetaValue(mapA.get(key)), bText: '—' })
        continue
      }
      const aVal = mapA.get(key)
      const bVal = mapB.get(key)
      const aCmp = toComparableString(aVal)
      const bCmp = toComparableString(bVal)
      if (aCmp !== bCmp) {
        different += 1
        entries.push({ key, kind: 'different', aText: formatMetaValue(aVal), bText: formatMetaValue(bVal) })
      }
    }
    const truncated = entries.length > COMPARE_DIFF_LIMIT
    return {
      entries: truncated ? entries.slice(0, COMPARE_DIFF_LIMIT) : entries,
      onlyA,
      onlyB,
      different,
      truncatedCount: truncated ? entries.length - COMPARE_DIFF_LIMIT : 0,
    }
  }, [compareMetaA, compareMetaB, compareIncludePilInfo])

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

      {compareActive && compareReady && (
        <InspectorSection
          title="Compare Metadata"
          open={openSections.compare}
          onToggle={() => toggleSection('compare')}
          actions={(
            <div className="flex items-center gap-2 text-xs">
              <button
                className="px-2 py-1 bg-transparent text-muted border border-border/60 rounded-md disabled:opacity-60 hover:border-border hover:text-text transition-colors"
                onClick={handleCompareReload}
                disabled={compareMetaState === 'loading'}
              >
                {compareMetaState === 'loading' ? 'Loading…' : 'Reload'}
              </button>
              <button
                className="px-2 py-1 bg-transparent text-muted border border-border/60 rounded-md disabled:opacity-60 hover:border-border hover:text-text transition-colors"
                onClick={() => setCompareIncludePilInfo((prev) => !prev)}
                disabled={compareMetaState !== 'loaded'}
              >
                {compareIncludePilInfo ? 'Hide PIL info' : 'Include PIL info'}
              </button>
            </div>
          )}
        >
          <div className="space-y-2 text-[11px]">
            <div className="grid grid-cols-2 gap-2 text-[11px] text-muted">
              <div>
                <div className="uppercase tracking-wide text-[10px]">A</div>
                <div className="text-text break-all" title={compareLabelA}>{compareLabelA}</div>
              </div>
              <div>
                <div className="uppercase tracking-wide text-[10px]">B</div>
                <div className="text-text break-all" title={compareLabelB}>{compareLabelB}</div>
              </div>
            </div>

            {compareMetaState === 'loading' && (
              <div className="text-muted">Loading metadata…</div>
            )}
            {compareMetaState === 'error' && compareMetaError && (
              <div className="text-danger break-words">{compareMetaError}</div>
            )}

            {compareMetaState === 'loaded' && compareDiff && (
              <div className="space-y-2">
                <div className="flex items-center justify-between text-muted">
                  <span>{compareDiff.different} different · {compareDiff.onlyA} only A · {compareDiff.onlyB} only B</span>
                  <span className="text-[10px] uppercase tracking-wide">Deep paths</span>
                </div>
                {compareDiff.entries.length === 0 ? (
                  <div className="text-muted">No differences found.</div>
                ) : (
                  <div className="space-y-2">
                    <div className="grid grid-cols-[minmax(80px,_1fr)_minmax(0,_1fr)_minmax(0,_1fr)] gap-2 text-[10px] uppercase tracking-wide text-muted">
                      <div>Path</div>
                      <div>A</div>
                      <div>B</div>
                    </div>
                    {compareDiff.entries.map((entry) => (
                      <div
                        key={entry.key}
                        className="grid grid-cols-[minmax(80px,_1fr)_minmax(0,_1fr)_minmax(0,_1fr)] gap-2"
                      >
                        <div className="text-[11px] text-muted font-mono break-all">{entry.key}</div>
                        <div className="text-[11px] font-mono bg-surface-inset border border-border/60 rounded px-2 py-1 whitespace-pre-wrap break-words max-h-32 overflow-auto">
                          {entry.aText}
                        </div>
                        <div className="text-[11px] font-mono bg-surface-inset border border-border/60 rounded px-2 py-1 whitespace-pre-wrap break-words max-h-32 overflow-auto">
                          {entry.bText}
                        </div>
                      </div>
                    ))}
                    {compareDiff.truncatedCount > 0 && (
                      <div className="text-muted text-[11px]">
                        +{compareDiff.truncatedCount} more differences not shown.
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </InspectorSection>
      )}

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
          <div className="relative">
            {metaKeyCopied && (
              <div className="ui-json-key-toast">
                Copied key: {metaKeyCopied}
              </div>
            )}
            <pre
              className={`ui-code-block ui-code-block-resizable ${metaHeightClass} overflow-auto whitespace-pre-wrap`}
              onClick={handleMetaClick}
            >
            {metaLoaded ? (
              <code
                className="block whitespace-pre-wrap"
                dangerouslySetInnerHTML={{ __html: highlightedMeta }}
              />
            ) : metaContent}
            </pre>
          </div>
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
          onChange={(e) => handleNotesChange(e.target.value)}
          onBlur={handleNotesBlur}
          aria-label={multi ? 'Notes for selected items' : 'Notes'}
        />
        <div>
          <div className="ui-label">{multi ? 'Tags (apply to all, comma-separated)' : 'Tags (comma-separated)'}</div>
          <input
            className="ui-input inspector-input w-full"
            placeholder="tag1, tag2"
            value={tags}
            onChange={(e) => handleTagsChange(e.target.value)}
            onBlur={handleTagsBlur}
            aria-label={multi ? 'Tags for selected items' : 'Tags'}
          />
        </div>
      </InspectorSection>
      <div className={resizeHandleClass} onMouseDown={onResize} />
    </div>
  )
}

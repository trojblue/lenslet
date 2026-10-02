import React, { useCallback, useEffect, useLayoutEffect, useId, useMemo, useRef, useState } from 'react'
import Dropdown from '../../shared/ui/Dropdown'
import { useModalFocusTrap } from '../../shared/hooks/useModalFocusTrap'
import type { EmbeddingSpec, EmbeddingRejected, EmbeddingSearchRequest } from '../../lib/types'
import { FetchError } from '../../lib/fetcher'

interface SimilarityModalProps {
  embeddings: EmbeddingSpec[]
  rejected?: EmbeddingRejected[]
  selectedPath: string | null
  embeddingsLoading?: boolean
  embeddingsError?: string | null
  onClose: () => void
  onSearch: (req: EmbeddingSearchRequest) => Promise<boolean>
}

type QueryMode = 'path' | 'vector'

export default function SimilarityModal({
  embeddings,
  rejected = [],
  selectedPath,
  embeddingsLoading = false,
  embeddingsError,
  onClose,
  onSearch,
}: SimilarityModalProps) {
  const [embeddingName, setEmbeddingName] = useState(() => embeddings[0]?.name ?? '')
  const [mode, setMode] = useState<QueryMode>(() => selectedPath ? 'path' : 'vector')
  const [queryPath, setQueryPath] = useState(() => selectedPath ?? '')
  const [queryVector, setQueryVector] = useState('')
  const [topK, setTopK] = useState('50')
  const [minScore, setMinScore] = useState('')
  const fieldId = useId()
  const dialogRef = useRef<HTMLDivElement>(null)
  const handleDialogKeyDown = useModalFocusTrap(dialogRef, { onEscape: onClose })
  const [invalidField, setInvalidField] = useState<'path' | 'vector' | 'top-k' | 'min-score' | null>(null)
  const [validationAttempt, setValidationAttempt] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useLayoutEffect(() => {
    if (invalidField) document.getElementById(`${fieldId}-${invalidField}`)?.focus()
  }, [fieldId, invalidField, error, validationAttempt])

  const pathInputRef = useRef<HTMLInputElement | null>(null)
  const vectorInputRef = useRef<HTMLTextAreaElement | null>(null)
  const activeLifetimeRef = useRef(true)

  useLayoutEffect(() => {
    activeLifetimeRef.current = true
    return () => {
      activeLifetimeRef.current = false
    }
  }, [])

  const selectedEmbedding = useMemo(
    () => embeddings.find((e) => e.name === embeddingName) ?? embeddings[0] ?? null,
    [embeddings, embeddingName]
  )

  useEffect(() => {
    if (embeddings.length > 0 && !embeddings.some((e) => e.name === embeddingName)) {
      setEmbeddingName(embeddings[0].name)
    }
  }, [embeddings, embeddingName])

  useEffect(() => {
    const target = mode === 'vector' ? vectorInputRef.current : pathInputRef.current
    const handle = window.requestAnimationFrame(() => target?.focus())
    return () => window.cancelAnimationFrame(handle)
  }, [mode])

  const handleSubmit = useCallback(async () => {
    if (busy) return
    setValidationAttempt((attempt) => attempt + 1)
    setError(null)
    setInvalidField(null)
    if (!embeddings.length) {
      setError('No embeddings available for similarity search.')
      return
    }
    if (!selectedEmbedding) {
      setError('Select an embedding to search.')
      return
    }

    const trimmedPath = queryPath.trim()
    const trimmedVector = queryVector.trim()
    const topKNum = Number(topK)
    if (!Number.isFinite(topKNum) || topKNum <= 0) {
      setError('Top K must be a positive number.')
      setInvalidField('top-k')
      return
    }

    const safeTopK = Math.min(1000, Math.max(1, Math.floor(topKNum)))
    const minScoreValue = minScore.trim() === '' ? null : Number(minScore)
    if (minScoreValue != null && !Number.isFinite(minScoreValue)) {
      setError('Min score must be a valid number.')
      setInvalidField('min-score')
      return
    }

    if (mode === 'path' && !trimmedPath) {
      setError('Select an image path for the query.')
      setInvalidField('path')
      return
    }
    if (mode === 'vector' && !trimmedVector) {
      setError('Paste a base64 vector for the query.')
      setInvalidField('vector')
      return
    }

    const payload: EmbeddingSearchRequest = {
      embedding: selectedEmbedding.name,
      query: mode === 'path'
        ? { kind: 'path', path: trimmedPath }
        : { kind: 'vector', vector_b64: trimmedVector },
      top_k: safeTopK,
      min_score: minScoreValue,
    }

    setBusy(true)
    try {
      const applied = await onSearch(payload)
      if (applied && activeLifetimeRef.current) onClose()
    } catch (err) {
      if (!activeLifetimeRef.current) return
      if (err instanceof FetchError) {
        setError(err.message)
      } else if (err instanceof Error) {
        setError(err.message)
      } else {
        setError('Failed to run similarity search.')
      }
    } finally {
      if (activeLifetimeRef.current) setBusy(false)
    }
  }, [embeddings.length, selectedEmbedding, queryPath, queryVector, topK, minScore, mode, onSearch, onClose, busy])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented) return
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault()
        void handleSubmit()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, handleSubmit])

  const handleUseSelected = useCallback(() => {
    if (!selectedPath) return
    setMode('path')
    setQueryPath(selectedPath)
    pathInputRef.current?.focus()
  }, [selectedPath])

  const embeddingOptions = embeddings.map((e) => ({
    value: e.name,
    label: e.name,
    keywords: [e.name],
  }))

  const showRejected = rejected.length > 0
  const rejectedPreview = rejected.slice(0, 3)

  return (
    <div
      ref={dialogRef}
      tabIndex={-1}
      onKeyDown={handleDialogKeyDown}
      className="similarity-modal-overlay fixed inset-0 z-[var(--z-overlay)] flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <form
        noValidate
        onSubmit={(event) => { event.preventDefault(); void handleSubmit() }}
        className="similarity-modal-shell w-full max-w-2xl rounded-lg border border-border bg-panel shadow-[0_20px_50px_rgba(0,0,0,0.55)]"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Find similar"
      >
        <div className="similarity-modal-header flex items-center justify-between px-4 py-3 border-b border-border">
          <div>
            <div className="text-sm font-semibold text-text">Find similar</div>
            <div className="text-xs text-muted">Search with embeddings</div>
          </div>
          <button type="button" className="btn btn-sm" onClick={onClose} aria-label="Close">
            Close
          </button>
        </div>
        <div className="similarity-modal-body scrollbar-thin px-4 py-4 space-y-4">
          <div className="space-y-2">
            <label className="ui-label">Embedding</label>
            <div className="flex items-center gap-2">
              <Dropdown
                aria-label="Embedding"
                value={selectedEmbedding?.name ?? ''}
                onChange={setEmbeddingName}
                options={embeddingOptions}
                placeholder={embeddingsLoading ? 'Loading embeddings...' : 'Select embedding'}
                disabled={!embeddings.length}
                triggerClassName="min-w-[180px]"
                searchable="auto"
                searchPlaceholder="Search embeddings..."
                emptyMessage="No matching embeddings"
              />
              {selectedEmbedding && (
                <span className="text-xs text-muted">
                  {selectedEmbedding.dimension} dims, {selectedEmbedding.metric}, {selectedEmbedding.dtype}
                </span>
              )}
            </div>
          </div>

          <div className="space-y-2">
            <label className="ui-label">Query mode</label>
            <div className="flex items-center gap-2">
              <button
                type="button"
                className={`btn btn-sm ${mode === 'path' ? 'btn-active' : ''}`}
                onClick={() => setMode('path')}
                aria-pressed={mode === 'path'}
              >
                Selected image
              </button>
              <button
                type="button"
                className={`btn btn-sm ${mode === 'vector' ? 'btn-active' : ''}`}
                onClick={() => setMode('vector')}
                aria-pressed={mode === 'vector'}
              >
                Vector input
              </button>
            </div>
          </div>

          <div className="similarity-modal-query">
            {mode === 'path' ? (
              <div className="space-y-2">
                <label className="ui-label" htmlFor={`${fieldId}-path`}>Image path</label>
                <div className="flex items-center gap-2">
                  <input
                    ref={pathInputRef}
                    id={`${fieldId}-path`}
                    aria-invalid={invalidField === 'path' || undefined}
                    aria-describedby={invalidField === 'path' ? `${fieldId}-error` : undefined}
                    type="text"
                    className="input w-full"
                    value={queryPath}
                    onChange={(e) => setQueryPath(e.target.value)}
                    placeholder={selectedPath ? 'Selected image path' : 'Select an image first'}
                  />
                  <button
                    type="button"
                    className="btn btn-sm"
                    onClick={handleUseSelected}
                    disabled={!selectedPath}
                    title={selectedPath ? 'Use selected image' : 'Select an image first'}
                  >
                    Use selected
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                <label className="ui-label" htmlFor={`${fieldId}-vector`}>Vector (base64 float32)</label>
                <textarea
                  ref={vectorInputRef}
                  id={`${fieldId}-vector`}
                  aria-invalid={invalidField === 'vector' || undefined}
                  aria-describedby={invalidField === 'vector' ? `${fieldId}-error` : undefined}
                  className="ui-textarea w-full text-[11px]"
                  rows={5}
                  value={queryVector}
                  onChange={(e) => setQueryVector(e.target.value)}
                  placeholder="Paste base64-encoded float32 vector"
                />
                <div className="text-[11px] text-muted">
                  Base64 of little-endian float32. Length must match embedding dimension.
                </div>
              </div>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <label className="ui-label" htmlFor={`${fieldId}-top-k`}>Top K</label>
              <input
                type="number"
                min={1}
                id={`${fieldId}-top-k`}
                aria-invalid={invalidField === 'top-k' || undefined}
                aria-describedby={invalidField === 'top-k' ? `${fieldId}-error` : undefined}
                max={1000}
                step={1}
                className="input ui-number w-full"
                value={topK}
                onChange={(e) => setTopK(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <label className="ui-label" htmlFor={`${fieldId}-min-score`}>Min score</label>
              <input
                type="number"
                step={0.01}
                id={`${fieldId}-min-score`}
                aria-invalid={invalidField === 'min-score' || undefined}
                aria-describedby={invalidField === 'min-score' ? `${fieldId}-error` : undefined}
                className="input ui-number w-full"
                value={minScore}
                onChange={(e) => setMinScore(e.target.value)}
                placeholder="Optional"
              />
            </div>
          </div>

          <div className="similarity-modal-status space-y-2">
            {embeddingsError && (
              <div className="ui-banner ui-banner-danger text-xs" role="alert">
                {embeddingsError}
              </div>
            )}
            {showRejected && (
              <div className="ui-banner text-xs">
                <div className="font-semibold">Skipped columns</div>
                <div className="mt-1 space-y-1 text-muted">
                  {rejectedPreview.map((item) => (
                    <div key={item.name}>{item.name}: {item.reason}</div>
                  ))}
                  {rejected.length > rejectedPreview.length && (
                    <div>+{rejected.length - rejectedPreview.length} more</div>
                  )}
                </div>
              </div>
            )}
            {error && (
              <div id={`${fieldId}-error`} className="ui-banner ui-banner-danger text-xs" role={invalidField ? undefined : 'alert'}>
                {error}
              </div>
            )}
          </div>
        </div>
        <div className="similarity-modal-footer flex items-center justify-between px-4 py-3 border-t border-border">
          <div className="text-xs text-muted">
            {selectedEmbedding ? `Metric: ${selectedEmbedding.metric}` : 'Metric: cosine'}
          </div>
          <div className="flex items-center gap-2">
            <button type="button" className="btn btn-sm btn-ghost" onClick={onClose} disabled={busy}>
              Cancel
            </button>
            <button
              className="btn btn-sm btn-active"
              type="submit"
              disabled={busy || !embeddings.length}
            >
              {busy ? 'Searching...' : 'Find similar'}
            </button>
          </div>
        </div>
      </form>
    </div>
  )
}

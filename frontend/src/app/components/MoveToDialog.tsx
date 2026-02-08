import React, { useEffect, useState } from 'react'
import { getPathName, sanitizePath } from '../routing/hash'

export interface MoveToDialogProps {
  paths: string[]
  defaultDestination: string
  destinations: string[]
  loadingDestinations: boolean
  onClose: () => void
  onSubmit: (paths: string[], destination: string) => Promise<boolean>
}

export default function MoveToDialog({
  paths,
  defaultDestination,
  destinations,
  loadingDestinations,
  onClose,
  onSubmit,
}: MoveToDialogProps): JSX.Element {
  const [destination, setDestination] = useState(() => sanitizePath(defaultDestination || '/'))
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    setDestination(sanitizePath(defaultDestination || '/'))
  }, [defaultDestination, paths])

  const normalizedDestination = sanitizePath(destination || '/')
  const canSubmit = paths.length > 0 && !submitting
  const previewNames = paths.slice(0, 3).map((path) => getPathName(path) || path)
  const remainingCount = Math.max(0, paths.length - previewNames.length)
  const quickDestinations = destinations
    .filter((path) => path !== normalizedDestination)
    .slice(0, 8)

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!canSubmit) return

    setSubmitting(true)
    try {
      await onSubmit(paths, normalizedDestination)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="toolbar-offset fixed inset-0 z-overlay bg-black/45 backdrop-blur-[1px] flex items-center justify-center p-3">
      <div className="w-full max-w-[560px] rounded-xl border border-border bg-panel shadow-[0_20px_60px_rgba(0,0,0,0.55)]">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-text">Move to folder</div>
            <div className="text-xs text-muted">{paths.length} item(s) selected</div>
          </div>
          <button
            type="button"
            className="btn btn-icon"
            onClick={onClose}
            aria-label="Close move dialog"
            disabled={submitting}
          >
            ×
          </button>
        </div>

        <form className="px-4 py-3 flex flex-col gap-3" onSubmit={handleSubmit}>
          <div className="text-xs text-muted">
            {previewNames.join(', ')}
            {remainingCount > 0 ? ` and ${remainingCount} more` : ''}
          </div>

          <label className="text-xs text-muted flex flex-col gap-1.5">
            Destination folder
            <input
              value={destination}
              onChange={(event) => setDestination(event.target.value)}
              className="input w-full"
              list="move-destination-list"
              placeholder="/"
              autoFocus
              disabled={submitting}
            />
          </label>
          <datalist id="move-destination-list">
            {destinations.map((path) => (
              <option key={path} value={path} />
            ))}
          </datalist>

          <div className="text-[11px] text-muted">
            {loadingDestinations ? 'Loading folder list…' : `${destinations.length.toLocaleString()} destination(s) loaded`}
          </div>

          {quickDestinations.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {quickDestinations.map((path) => (
                <button
                  key={path}
                  type="button"
                  className="btn btn-sm"
                  onClick={() => setDestination(path)}
                  disabled={submitting}
                >
                  {path}
                </button>
              ))}
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2 border-t border-border">
            <button type="button" className="btn" onClick={onClose} disabled={submitting}>Cancel</button>
            <button type="submit" className="btn btn-active" disabled={!canSubmit}>
              {submitting ? 'Moving…' : 'Move'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { PresenceEvent } from '../../lib/types'

export type SyncIndicatorState = 'offline' | 'unstable' | 'recent' | 'editing' | 'live'

export type SyncIndicatorData = {
  state: SyncIndicatorState
  presence?: PresenceEvent
  syncLabel: string
  connectionLabel: string
  lastEditedLabel: string
  hasEdits: boolean
}

type SyncIndicatorProps = SyncIndicatorData & {
  isNarrow: boolean
}

const DOT_CLASS: Record<SyncIndicatorState, string> = {
  offline: 'sync-dot-offline',
  unstable: 'sync-dot-unstable',
  recent: 'sync-dot-recent',
  editing: 'sync-dot-editing',
  live: 'sync-dot-live',
}

export default function SyncIndicator({
  state,
  presence,
  syncLabel,
  connectionLabel,
  lastEditedLabel,
  hasEdits,
  isNarrow,
}: SyncIndicatorProps): JSX.Element {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)

  const presenceText = useMemo(() => {
    if (!presence) return '- viewing · - editing'
    return `${presence.viewing} viewing · ${presence.editing} editing`
  }, [presence])

  const viewingLabel = presence ? String(presence.viewing) : '-'

  const closeCard = useCallback(() => {
    setOpen(false)
    window.requestAnimationFrame(() => buttonRef.current?.focus())
  }, [])

  useEffect(() => {
    if (!open) return
    const handleClick = (e: MouseEvent) => {
      if (!rootRef.current || rootRef.current.contains(e.target as Node)) return
      closeCard()
    }
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeCard()
    }
    window.addEventListener('mousedown', handleClick)
    window.addEventListener('keydown', handleKey)
    return () => {
      window.removeEventListener('mousedown', handleClick)
      window.removeEventListener('keydown', handleKey)
    }
  }, [open, closeCard])

  return (
    <div ref={rootRef} className="sync-indicator">
      <button
        ref={buttonRef}
        type="button"
        className="sync-indicator-button"
        onClick={() => (open ? closeCard() : setOpen(true))}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label="Sync status"
        title={presenceText}
      >
        <span className={`sync-indicator-dot ${DOT_CLASS[state]}`} aria-hidden="true" />
        {!isNarrow && (
          <span className="sync-indicator-count tabular-nums">{viewingLabel}</span>
        )}
      </button>
      {open && (
        <div role="dialog" aria-label="Sync status" className="sync-indicator-card">
          <div className="sync-indicator-line sync-indicator-primary">{syncLabel}</div>
          <div className="sync-indicator-line">{connectionLabel}</div>
          <div className="sync-indicator-line sync-indicator-muted">{presenceText}</div>
          <div className="sync-indicator-line sync-indicator-muted">
            {hasEdits ? `Last edited: ${lastEditedLabel}` : 'No edits yet.'}
          </div>
        </div>
      )}
    </div>
  )
}

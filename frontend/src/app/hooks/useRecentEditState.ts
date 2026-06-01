import { useCallback, useEffect, useMemo, useState } from 'react'
import { LAST_EDIT_RELATIVE_MS, RECENT_EDIT_FLASH_MS } from '../../lib/constants'
import { formatAbsoluteTime, formatRelativeTime, parseTimestampMs } from '../../lib/util'

function formatTimestampLabel(timestampMs: number, nowMs: number): string {
  if (nowMs - timestampMs < LAST_EDIT_RELATIVE_MS) {
    return formatRelativeTime(timestampMs, nowMs)
  }
  return formatAbsoluteTime(timestampMs)
}

export type RecentEditState = {
  recentEditActive: boolean
  hasEdits: boolean
  lastEditedNow: number
  lastEditedLabel: string
  updateLastEdited: (updatedAt?: string | null) => void
  formatTimestampLabel: (timestampMs: number, nowMs: number) => string
}

export function useRecentEditState(): RecentEditState {
  const [lastEditedAt, setLastEditedAt] = useState<number | null>(null)
  const [recentEditAt, setRecentEditAt] = useState<number | null>(null)
  const [recentEditActive, setRecentEditActive] = useState(false)
  const [lastEditedNow, setLastEditedNow] = useState(() => Date.now())

  useEffect(() => {
    if (recentEditAt == null) {
      setRecentEditActive(false)
      return
    }
    setRecentEditActive(true)
    const id = window.setTimeout(() => setRecentEditActive(false), RECENT_EDIT_FLASH_MS)
    return () => window.clearTimeout(id)
  }, [recentEditAt])

  useEffect(() => {
    if (lastEditedAt == null) return
    setLastEditedNow(Date.now())
    const id = window.setInterval(() => setLastEditedNow(Date.now()), 10_000)
    return () => window.clearInterval(id)
  }, [lastEditedAt])

  const updateLastEdited = useCallback((updatedAt?: string | null) => {
    const now = Date.now()
    const parsed = parseTimestampMs(updatedAt)
    const candidate = parsed ?? now
    const safeCandidate = candidate > now ? now : candidate
    setLastEditedAt((prev) => {
      if (prev == null) return safeCandidate
      return prev > safeCandidate ? prev : safeCandidate
    })
    setRecentEditAt(now)
    setLastEditedNow(now)
  }, [])

  const hasEdits = lastEditedAt != null
  const lastEditedLabel = useMemo(() => {
    if (!hasEdits || lastEditedAt == null) return 'No edits yet.'
    return formatTimestampLabel(lastEditedAt, lastEditedNow)
  }, [hasEdits, lastEditedAt, lastEditedNow])

  return {
    recentEditActive,
    hasEdits,
    lastEditedNow,
    lastEditedLabel,
    updateLastEdited,
    formatTimestampLabel,
  }
}

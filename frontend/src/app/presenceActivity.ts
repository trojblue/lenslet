import { useCallback, useEffect, useRef, useState } from 'react'
import { ITEM_HIGHLIGHT_MIN_VISIBLE_MS } from '../lib/constants'
import type { Item } from '../lib/types'
import { parseTimestampMs } from '../lib/util'

const MAX_HIGHLIGHT_EVENT_IDS = 2048
const MAX_OFF_VIEW_ACTIVITY = 6
const MAX_RECENT_TOUCHES = 10

export type RecentActivityKind = 'item-updated' | 'metrics-updated'

export type RecentActivity = {
  path: string
  ts: number
  kind: RecentActivityKind
}

export type RecentSummary = {
  count: number
  names: string[]
  extra: number
}

export type RecentTouchDisplay = {
  path: string
  label: string
  timeLabel: string
}

type TimestampFormatter = (timestampMs: number, nowMs: number) => string

type UsePresenceActivityResult = {
  offViewActivity: RecentActivity[]
  recentTouches: RecentActivity[]
  highlightedPaths: Map<string, string>
  onVisiblePathsChange: (paths: Set<string>) => void
  markRecentActivity: (path: string, kind: RecentActivityKind, eventId: number | null) => void
  markRecentTouch: (path: string, kind: RecentActivityKind, updatedAt?: string | null) => void
  clearOffViewActivity: () => void
}

function buildItemNameLookup(items: Item[]): Map<string, string> {
  const namesByPath = new Map<string, string>()
  for (const item of items) {
    namesByPath.set(item.path, item.name)
  }
  return namesByPath
}

function getItemLabel(path: string, namesByPath: Map<string, string>): string {
  return namesByPath.get(path) ?? path.split('/').pop() ?? path
}

function pruneVisibleEntries(activity: RecentActivity[], visiblePaths: Set<string>): RecentActivity[] {
  const next = activity.filter((entry) => !visiblePaths.has(entry.path))
  return next.length === activity.length ? activity : next
}

function trimAndUpsert(
  entries: RecentActivity[],
  path: string,
  ts: number,
  kind: RecentActivityKind,
  limit: number,
): RecentActivity[] {
  const filtered = entries.filter((entry) => entry.path !== path)
  const next = [{ path, ts, kind }, ...filtered]
  return next.slice(0, limit)
}

export function buildRecentSummary(recentActivity: RecentActivity[], items: Item[]): RecentSummary | null {
  if (!recentActivity.length) return null

  const namesByPath = buildItemNameLookup(items)
  const seen = new Set<string>()
  const paths: string[] = []
  for (const entry of recentActivity) {
    if (seen.has(entry.path)) continue
    seen.add(entry.path)
    paths.push(entry.path)
  }

  const names = paths.slice(0, 2).map((path) => getItemLabel(path, namesByPath))
  return {
    count: paths.length,
    names,
    extra: Math.max(0, paths.length - names.length),
  }
}

export function buildRecentTouchesDisplay(
  recentTouches: RecentActivity[],
  items: Item[],
  nowMs: number,
  formatTimestamp: TimestampFormatter,
): RecentTouchDisplay[] {
  if (!recentTouches.length) return []

  const namesByPath = buildItemNameLookup(items)
  return recentTouches.map((entry) => ({
    path: entry.path,
    label: getItemLabel(entry.path, namesByPath),
    timeLabel: formatTimestamp(entry.ts, nowMs),
  }))
}

export function usePresenceActivity(visibleItemPaths: string[]): UsePresenceActivityResult {
  const [offViewActivity, setOffViewActivity] = useState<RecentActivity[]>([])
  const [recentTouches, setRecentTouches] = useState<RecentActivity[]>([])
  const [highlightedPaths, setHighlightedPaths] = useState<Map<string, string>>(new Map())
  const highlightTimersRef = useRef<Map<string, number>>(new Map())
  const seenHighlightEventIdsRef = useRef<Set<number>>(new Set())
  const visibleFilteredPathsRef = useRef<Set<string>>(new Set())
  const visibleViewportPathsRef = useRef<Set<string>>(new Set())

  useEffect(() => {
    return () => {
      for (const timeoutId of highlightTimersRef.current.values()) {
        window.clearTimeout(timeoutId)
      }
      highlightTimersRef.current.clear()
      seenHighlightEventIdsRef.current.clear()
    }
  }, [])

  useEffect(() => {
    visibleFilteredPathsRef.current = new Set(visibleItemPaths)
    setOffViewActivity((previous) =>
      pruneVisibleEntries(previous, visibleViewportPathsRef.current),
    )
  }, [visibleItemPaths])

  const markHighlight = useCallback((path: string, eventId: number | null) => {
    if (eventId != null) {
      if (seenHighlightEventIdsRef.current.has(eventId)) return
      seenHighlightEventIdsRef.current.add(eventId)
      if (seenHighlightEventIdsRef.current.size > MAX_HIGHLIGHT_EVENT_IDS) {
        const oldestId = seenHighlightEventIdsRef.current.values().next().value
        if (oldestId != null) {
          seenHighlightEventIdsRef.current.delete(oldestId)
        }
      }
    }

    const highlightKey = eventId != null
      ? `event:${eventId}`
      : `event:${path}:${Date.now()}`

    setHighlightedPaths((previous) => {
      if (previous.get(path) === highlightKey) return previous
      const next = new Map(previous)
      next.set(path, highlightKey)
      return next
    })

    const timers = highlightTimersRef.current
    const existing = timers.get(path)
    if (existing != null) window.clearTimeout(existing)
    const timeoutId = window.setTimeout(() => {
      setHighlightedPaths((previous) => {
        if (previous.get(path) !== highlightKey) return previous
        const next = new Map(previous)
        next.delete(path)
        return next
      })
      timers.delete(path)
    }, ITEM_HIGHLIGHT_MIN_VISIBLE_MS)
    timers.set(path, timeoutId)
  }, [])

  const onVisiblePathsChange = useCallback((paths: Set<string>) => {
    visibleViewportPathsRef.current = paths
    setOffViewActivity((previous) => pruneVisibleEntries(previous, paths))
  }, [])

  const markRecentActivity = useCallback((path: string, kind: RecentActivityKind, eventId: number | null) => {
    const now = Date.now()
    const inVisibleViewport =
      visibleFilteredPathsRef.current.has(path) &&
      visibleViewportPathsRef.current.has(path)
    if (!inVisibleViewport) {
      setOffViewActivity((previous) =>
        trimAndUpsert(previous, path, now, kind, MAX_OFF_VIEW_ACTIVITY),
      )
    }
    markHighlight(path, eventId)
  }, [markHighlight])

  const markRecentTouch = useCallback((path: string, kind: RecentActivityKind, updatedAt?: string | null) => {
    const now = Date.now()
    const ts = parseTimestampMs(updatedAt) ?? now
    setRecentTouches((previous) => trimAndUpsert(previous, path, ts, kind, MAX_RECENT_TOUCHES))
  }, [])

  const clearOffViewActivity = useCallback(() => {
    setOffViewActivity([])
  }, [])

  return {
    offViewActivity,
    recentTouches,
    highlightedPaths,
    onVisiblePathsChange,
    markRecentActivity,
    markRecentTouch,
    clearOffViewActivity,
  }
}

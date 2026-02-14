import { useCallback, useMemo, useRef } from 'react'
import type { FolderIndex } from '../../lib/types'

const MAX_HYDRATED_SNAPSHOT_ITEMS = 10_000

export type FolderSessionEntry = {
  path: string
  hydratedSnapshot: FolderIndex | null
  hydratedGeneratedAt: string | null
  hydratedItemCount: number
  hydratedAtMs: number | null
  topAnchorPath: string | null
}

export type FolderSessionState = Record<string, FolderSessionEntry>

function normalizePath(path: string): string {
  const trimmed = path.trim()
  if (!trimmed || trimmed === '/') return '/'
  return trimmed.startsWith('/') ? trimmed : `/${trimmed}`
}

function getOrCreateSession(state: FolderSessionState, path: string): FolderSessionEntry {
  const normalizedPath = normalizePath(path)
  const existing = state[normalizedPath]
  if (existing) return existing
  return {
    path: normalizedPath,
    hydratedSnapshot: null,
    hydratedGeneratedAt: null,
    hydratedItemCount: 0,
    hydratedAtMs: null,
    topAnchorPath: null,
  }
}

function isSubtreePath(path: string, rootPath: string): boolean {
  if (rootPath === '/') return true
  return path === rootPath || path.startsWith(`${rootPath}/`)
}

export function extractTopAnchorPath(visiblePaths: ReadonlySet<string>): string | null {
  for (const path of visiblePaths) {
    return path
  }
  return null
}

export function upsertFolderSessionSnapshot(
  state: FolderSessionState,
  path: string,
  snapshot: FolderIndex,
  nowMs: number,
): FolderSessionState {
  const existing = getOrCreateSession(state, path)
  const hydratedSnapshot = snapshot.items.length <= MAX_HYDRATED_SNAPSHOT_ITEMS ? snapshot : null
  const next: FolderSessionEntry = {
    ...existing,
    path: normalizePath(path),
    hydratedSnapshot,
    hydratedGeneratedAt: snapshot.generatedAt ?? null,
    hydratedItemCount: snapshot.totalItems ?? snapshot.items.length,
    hydratedAtMs: nowMs,
  }
  if (
    existing.hydratedSnapshot === next.hydratedSnapshot &&
    existing.hydratedGeneratedAt === next.hydratedGeneratedAt &&
    existing.hydratedItemCount === next.hydratedItemCount &&
    existing.hydratedAtMs === next.hydratedAtMs
  ) {
    return state
  }
  return {
    ...state,
    [next.path]: next,
  }
}

export function upsertFolderSessionTopAnchor(
  state: FolderSessionState,
  path: string,
  topAnchorPath: string | null,
): FolderSessionState {
  const existing = getOrCreateSession(state, path)
  const normalizedPath = normalizePath(path)
  const normalizedAnchor = topAnchorPath ? normalizePath(topAnchorPath) : null
  if (existing.topAnchorPath === normalizedAnchor && existing.path === normalizedPath) {
    return state
  }
  return {
    ...state,
    [normalizedPath]: {
      ...existing,
      path: normalizedPath,
      topAnchorPath: normalizedAnchor,
    },
  }
}

export function invalidateFolderSession(
  state: FolderSessionState,
  path: string,
): FolderSessionState {
  const normalizedPath = normalizePath(path)
  if (!state[normalizedPath]) return state
  const next = { ...state }
  delete next[normalizedPath]
  return next
}

export function invalidateFolderSessionSubtree(
  state: FolderSessionState,
  rootPath: string,
): FolderSessionState {
  const normalizedRoot = normalizePath(rootPath)
  let changed = false
  const next = { ...state }
  for (const path of Object.keys(next)) {
    if (!isSubtreePath(path, normalizedRoot)) continue
    changed = true
    delete next[path]
  }
  return changed ? next : state
}

export function isScopeTransitionCompatible(previousPath: string, nextPath: string): boolean {
  const normalizedPrevious = normalizePath(previousPath)
  const normalizedNext = normalizePath(nextPath)
  if (normalizedPrevious === normalizedNext) return true
  if (isSubtreePath(normalizedPrevious, normalizedNext)) return true
  if (isSubtreePath(normalizedNext, normalizedPrevious)) return true
  return false
}

export function invalidateIncompatibleScopeTransition(
  state: FolderSessionState,
  previousPath: string,
  nextPath: string,
): FolderSessionState {
  if (isScopeTransitionCompatible(previousPath, nextPath)) {
    return state
  }
  return invalidateFolderSession(state, nextPath)
}

export type UseFolderSessionStateResult = {
  getSession: (path: string) => FolderSessionEntry | null
  getHydratedSnapshot: (path: string) => FolderIndex | null
  getTopAnchorPath: (path: string) => string | null
  saveHydratedSnapshot: (path: string, snapshot: FolderIndex) => void
  saveTopAnchorPath: (path: string, topAnchorPath: string | null) => void
  saveTopAnchorFromVisiblePaths: (path: string, visiblePaths: ReadonlySet<string>) => void
  invalidatePath: (path: string) => void
  invalidateSubtree: (path: string) => void
  invalidateForScopeTransition: (previousPath: string, nextPath: string) => void
  clearAllSessions: () => void
}

export function useFolderSessionState(): UseFolderSessionStateResult {
  const stateRef = useRef<FolderSessionState>({})

  const getSession = useCallback((path: string): FolderSessionEntry | null => {
    return stateRef.current[normalizePath(path)] ?? null
  }, [])

  const getHydratedSnapshot = useCallback((path: string): FolderIndex | null => {
    return stateRef.current[normalizePath(path)]?.hydratedSnapshot ?? null
  }, [])

  const getTopAnchorPath = useCallback((path: string): string | null => {
    return stateRef.current[normalizePath(path)]?.topAnchorPath ?? null
  }, [])

  const saveHydratedSnapshot = useCallback((path: string, snapshot: FolderIndex): void => {
    stateRef.current = upsertFolderSessionSnapshot(stateRef.current, path, snapshot, Date.now())
  }, [])

  const saveTopAnchorPath = useCallback((path: string, topAnchorPath: string | null): void => {
    stateRef.current = upsertFolderSessionTopAnchor(stateRef.current, path, topAnchorPath)
  }, [])

  const saveTopAnchorFromVisiblePaths = useCallback((path: string, visiblePaths: ReadonlySet<string>): void => {
    const topAnchorPath = extractTopAnchorPath(visiblePaths)
    if (!topAnchorPath) return
    stateRef.current = upsertFolderSessionTopAnchor(stateRef.current, path, topAnchorPath)
  }, [])

  const invalidatePath = useCallback((path: string): void => {
    stateRef.current = invalidateFolderSession(stateRef.current, path)
  }, [])

  const invalidateSubtree = useCallback((path: string): void => {
    stateRef.current = invalidateFolderSessionSubtree(stateRef.current, path)
  }, [])

  const invalidateForScopeTransition = useCallback((previousPath: string, nextPath: string): void => {
    stateRef.current = invalidateIncompatibleScopeTransition(stateRef.current, previousPath, nextPath)
  }, [])

  const clearAllSessions = useCallback((): void => {
    stateRef.current = {}
  }, [])

  return useMemo(() => ({
    getSession,
    getHydratedSnapshot,
    getTopAnchorPath,
    saveHydratedSnapshot,
    saveTopAnchorPath,
    saveTopAnchorFromVisiblePaths,
    invalidatePath,
    invalidateSubtree,
    invalidateForScopeTransition,
    clearAllSessions,
  }), [
    getSession,
    getHydratedSnapshot,
    getTopAnchorPath,
    saveHydratedSnapshot,
    saveTopAnchorPath,
    saveTopAnchorFromVisiblePaths,
    invalidatePath,
    invalidateSubtree,
    invalidateForScopeTransition,
    clearAllSessions,
  ])
}

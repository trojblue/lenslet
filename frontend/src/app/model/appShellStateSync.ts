import type { QueryClient, QueryKey } from '@tanstack/react-query'
import type {
  CompareOrderMode,
  FilterAST,
  BrowseFolderPayload,
  BrowseItemPayload,
  BrowseSearchResultsPayload,
  SortSpec,
  StarRating,
  ViewMode,
} from '../../lib/types'

type QueryLike = {
  queryHash?: string
  queryKey: QueryKey
  state?: {
    data?: unknown
  }
}

export type ItemCacheUpdatePayload = {
  path: string
  star?: StarRating | null
  metrics?: Record<string, number | null> | null
  notes?: string | null
}

export type PersistedAppShellSettings = {
  sortSpec: SortSpec
  starFilters: number[]
  filterAst: FilterAST
  selectedMetric?: string
  viewMode: ViewMode
  gridItemSize: number
  leftOpen: boolean
  rightOpen: boolean
  autoloadImageMetadata: boolean
  compareOrderMode: CompareOrderMode
}

export type DeferredWriteScheduler<T> = {
  schedule: (snapshot: T) => void
  flush: () => void
  cancel: () => void
}

type TimeoutHandle = ReturnType<typeof globalThis.setTimeout>
type IdleCommitHandle = number | TimeoutHandle

function isIndexedQueryKey(queryKey: QueryKey): boolean {
  return Array.isArray(queryKey) && (queryKey[0] === 'folder' || queryKey[0] === 'search')
}

function extractIndexedPaths(data: unknown): string[] {
  if (!data || typeof data !== 'object') return []
  const items = (data as { items?: unknown }).items
  if (!Array.isArray(items)) return []
  const paths = new Set<string>()
  for (const item of items) {
    const path = (item as { path?: unknown }).path
    if (typeof path === 'string' && path) {
      paths.add(path)
    }
  }
  return Array.from(paths)
}

function queryId(query: QueryLike): string {
  return query.queryHash ?? JSON.stringify(query.queryKey)
}

function updateIndexedItem(item: BrowseItemPayload, payload: ItemCacheUpdatePayload): BrowseItemPayload {
  if (item.path !== payload.path) return item

  const hasStar = Object.prototype.hasOwnProperty.call(payload, 'star')
  const hasMetrics = payload.metrics !== undefined
  const hasNotes = payload.notes !== undefined
  let next = item

  if (hasStar && item.star !== payload.star) {
    next = { ...next, star: payload.star ?? null }
  }
  if (hasMetrics) {
    next = { ...next, metrics: payload.metrics ?? undefined }
  }
  if (hasNotes && item.notes !== payload.notes) {
    next = { ...next, notes: payload.notes ?? '' }
  }
  return next
}

export function patchItemCollection<T extends { items: BrowseItemPayload[] }>(
  oldData: T | undefined,
  payload: ItemCacheUpdatePayload,
): T | undefined {
  if (!oldData) return oldData

  let changed = false
  const items = oldData.items.map((item) => {
    const next = updateIndexedItem(item, payload)
    if (next !== item) changed = true
    return next
  })

  return changed ? { ...oldData, items } : oldData
}

export class ItemQueryPathIndex {
  private readonly hashesByPath = new Map<string, Set<string>>()
  private readonly pathsByHash = new Map<string, Set<string>>()
  private readonly queryKeyByHash = new Map<string, QueryKey>()

  seed(queries: readonly QueryLike[]): void {
    this.hashesByPath.clear()
    this.pathsByHash.clear()
    this.queryKeyByHash.clear()
    for (const query of queries) {
      this.syncQuery(query)
    }
  }

  syncQuery(query: QueryLike): void {
    const hash = queryId(query)
    this.deleteHash(hash)

    if (!isIndexedQueryKey(query.queryKey)) {
      return
    }

    const paths = extractIndexedPaths(query.state?.data)
    if (!paths.length) {
      return
    }

    const uniquePaths = new Set(paths)
    this.pathsByHash.set(hash, uniquePaths)
    this.queryKeyByHash.set(hash, query.queryKey)
    for (const path of uniquePaths) {
      const existing = this.hashesByPath.get(path) ?? new Set<string>()
      existing.add(hash)
      this.hashesByPath.set(path, existing)
    }
  }

  removeQuery(query: QueryLike): void {
    this.deleteHash(queryId(query))
  }

  getQueryKeys(path: string): QueryKey[] {
    const hashes = this.hashesByPath.get(path)
    if (!hashes || !hashes.size) {
      return []
    }
    const keys: QueryKey[] = []
    for (const hash of hashes) {
      const key = this.queryKeyByHash.get(hash)
      if (key) {
        keys.push(key)
      }
    }
    return keys
  }

  private deleteHash(hash: string): void {
    const previousPaths = this.pathsByHash.get(hash)
    if (previousPaths) {
      for (const path of previousPaths) {
        const hashes = this.hashesByPath.get(path)
        if (!hashes) continue
        hashes.delete(hash)
        if (!hashes.size) {
          this.hashesByPath.delete(path)
        }
      }
      this.pathsByHash.delete(hash)
    }
    this.queryKeyByHash.delete(hash)
  }
}

export function syncItemQueryIndexFromEvent(
  index: ItemQueryPathIndex,
  event: { type?: string; query?: QueryLike } | undefined,
): void {
  const query = event?.query
  if (!query) return
  if (event?.type === 'removed') {
    index.removeQuery(query)
    return
  }
  index.syncQuery(query)
}

export function patchIndexedItemQueries(
  queryClient: QueryClient,
  index: ItemQueryPathIndex,
  payload: ItemCacheUpdatePayload,
): void {
  const hasStar = Object.prototype.hasOwnProperty.call(payload, 'star')
  const hasMetrics = payload.metrics !== undefined
  const hasNotes = payload.notes !== undefined
  if (!hasStar && !hasMetrics && !hasNotes) return

  for (const queryKey of index.getQueryKeys(payload.path)) {
    if (!queryClient.getQueryState(queryKey)) continue
    queryClient.setQueryData<BrowseFolderPayload | BrowseSearchResultsPayload | undefined>(
      queryKey,
      (oldData) => patchItemCollection(oldData, payload),
    )
  }
}

function scheduleIdleCommit(callback: () => void): IdleCommitHandle {
  const requestIdle = (globalThis as {
    requestIdleCallback?: (cb: () => void) => number
  }).requestIdleCallback
  if (typeof requestIdle === 'function') {
    return requestIdle(callback)
  }
  return globalThis.setTimeout(callback, 0)
}

function cancelIdleCommit(handle: IdleCommitHandle): void {
  const cancelIdle = (globalThis as {
    cancelIdleCallback?: (id: number) => void
  }).cancelIdleCallback
  if (typeof cancelIdle === 'function' && typeof handle === 'number') {
    cancelIdle(handle)
    return
  }
  globalThis.clearTimeout(handle as TimeoutHandle)
}

export function createDeferredWriteScheduler<T>(
  write: (snapshot: T) => void,
  delayMs = 200,
): DeferredWriteScheduler<T> {
  let timeoutId: TimeoutHandle | null = null
  let idleId: IdleCommitHandle | null = null
  let pending: T | null = null

  const clearScheduled = () => {
    if (timeoutId != null) {
      globalThis.clearTimeout(timeoutId)
      timeoutId = null
    }
    if (idleId != null) {
      cancelIdleCommit(idleId)
      idleId = null
    }
  }

  const commit = () => {
    if (pending == null) return
    const snapshot = pending
    pending = null
    write(snapshot)
  }

  return {
    schedule(snapshot) {
      pending = snapshot
      clearScheduled()
      timeoutId = globalThis.setTimeout(() => {
        timeoutId = null
        idleId = scheduleIdleCommit(() => {
          idleId = null
          commit()
        })
      }, delayMs)
    },
    flush() {
      clearScheduled()
      commit()
    },
    cancel() {
      clearScheduled()
      pending = null
    },
  }
}

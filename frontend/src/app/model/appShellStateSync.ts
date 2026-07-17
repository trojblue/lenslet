import type { QueryClient, QueryKey } from '@tanstack/react-query'
import type {
  CompareOrderMode,
  BrowseFolderPayload,
  BrowseItemPayload,
  BrowseSearchResultsPayload,
  FilterAST,
  QueryDependencyManifest,
  StarRating,
  ViewMode,
  ViewState,
} from '../../lib/types'
import { applyFilterAst } from '../../features/browse/model/filters'

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

export type ItemCacheUpdateOptions = {
  removeConclusiveFilterMismatch?: boolean
  replaceMutableMetrics?: boolean
}

export type AnnotationProjection = {
  mutationId: string
  changedFields: readonly string[]
  item: ItemCacheUpdatePayload
  replaceMutableMetrics?: boolean
}

export type PersistedAppShellSettings = {
  viewState: ViewState
  viewMode: ViewMode
  gridItemSize: number
  leftOpen: boolean
  rightOpen: boolean
  autoloadImageMetadata: boolean
  compareOrderMode: CompareOrderMode
  proxyHttpOriginals: boolean
}

export type DeferredWriteScheduler<T> = {
  schedule: (snapshot: T) => void
  flush: () => void
  cancel: () => void
}

type TimeoutHandle = ReturnType<typeof globalThis.setTimeout>
type IdleCommitHandle = number | TimeoutHandle

function isIndexedQueryKey(queryKey: QueryKey): boolean {
  return Array.isArray(queryKey)
    && (queryKey[0] === 'folder' || queryKey[0] === 'search')
}

function collectItemPaths(items: unknown, paths: Set<string>): void {
  if (!Array.isArray(items)) return
  for (const item of items) {
    const path = (item as { path?: unknown }).path
    if (typeof path === 'string' && path) {
      paths.add(path)
    }
  }
}

function extractIndexedPaths(data: unknown): string[] {
  if (!data || typeof data !== 'object') return []
  const paths = new Set<string>()
  collectItemPaths((data as { items?: unknown }).items, paths)
  const pages = (data as { pages?: unknown }).pages
  if (Array.isArray(pages)) {
    for (const page of pages) {
      collectItemPaths((page as { items?: unknown } | null | undefined)?.items, paths)
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
  options: ItemCacheUpdateOptions = {},
): void {
  const hasStar = Object.prototype.hasOwnProperty.call(payload, 'star')
  const hasMetrics = payload.metrics !== undefined
  const hasNotes = payload.notes !== undefined
  if (!hasStar && !hasMetrics && !hasNotes) return

  for (const queryKey of index.getQueryKeys(payload.path)) {
    if (!queryClient.getQueryState(queryKey)) continue
    queryClient.setQueryData<
      BrowseFolderPayload
      | BrowseSearchResultsPayload
      | { pages: BrowseFolderPayload[] }
      | undefined
    >(
      queryKey,
      (oldData) => patchIndexedQueryData(
        oldData,
        payload,
        options.removeConclusiveFilterMismatch ? folderQueryFilters(queryKey) : null,
      ),
    )
  }
}

function folderQueryFilters(queryKey: QueryKey): FilterAST | null {
  if (!Array.isArray(queryKey) || queryKey[0] !== 'folder-query') return null
  const analysisKey = queryKey[1]
  if (!Array.isArray(analysisKey)) return null
  const filters = analysisKey[3]
  if (!filters || typeof filters !== 'object' || !Array.isArray((filters as FilterAST).and)) {
    return null
  }
  return filters as FilterAST
}

function patchIndexedQueryData<
  T extends BrowseFolderPayload | BrowseSearchResultsPayload | { pages: BrowseFolderPayload[] },
>(
  oldData: T | undefined,
  payload: ItemCacheUpdatePayload,
  filters: FilterAST | null,
): T | undefined {
  if (!oldData) return oldData
  const pages = (oldData as { pages?: unknown }).pages
  if (!Array.isArray(pages)) {
    return patchItemCollection(oldData as BrowseFolderPayload | BrowseSearchResultsPayload, payload) as T | undefined
  }
  let changed = false
  let removed = false
  const nextPages = pages.map((page) => {
    const next = patchItemCollection(page as BrowseFolderPayload, payload)
    if (filters && next) {
      const keptItems = next.items.filter((item) => (
        item.path !== payload.path || applyFilterAst([item], filters).length > 0
      ))
      if (keptItems.length !== next.items.length) {
        changed = true
        removed = true
        return { ...next, items: keptItems }
      }
    }
    if (next !== page) changed = true
    return next
  })
  const adjustedPages = removed
    ? nextPages.map((page) => {
      const filteredTotal = (page as { filtered_total?: unknown }).filtered_total
      return typeof filteredTotal === 'number'
        ? { ...page, filtered_total: Math.max(0, filteredTotal - 1) }
        : page
    })
    : nextPages
  return changed ? { ...oldData, pages: adjustedPages } : oldData
}

function dependencyManifestFromData(data: unknown): QueryDependencyManifest | null {
  if (!data || typeof data !== 'object') return null
  const direct = (data as { dependency_manifest?: QueryDependencyManifest }).dependency_manifest
  if (direct) return direct
  const pages = (data as { pages?: unknown }).pages
  if (!Array.isArray(pages)) return null
  for (const page of pages) {
    const manifest = (page as { dependency_manifest?: QueryDependencyManifest } | null)?.dependency_manifest
    if (manifest) return manifest
  }
  return null
}

export function mutationAffectsDependencyManifest(
  changedFields: readonly string[],
  manifest: QueryDependencyManifest | null | undefined,
): boolean {
  if (!changedFields.length) return false
  if (!manifest || manifest.unknown) return true
  const fields = new Set(manifest.fields)
  const metricKeys = new Set(manifest.metric_keys)
  const categoricalKeys = new Set(manifest.categorical_keys)
  for (const changed of changedFields) {
    if (fields.has(changed)) return true
    if (changed === 'metrics' && metricKeys.size > 0) return true
    if (changed === 'categoricals' && categoricalKeys.size > 0) return true
    if (changed.startsWith('metric:') && metricKeys.has(changed.slice('metric:'.length))) {
      return true
    }
    if (
      changed.startsWith('categorical:')
      && categoricalKeys.has(changed.slice('categorical:'.length))
    ) {
      return true
    }
  }
  return false
}

const ANNOTATION_MUTATION_ID_LIMIT = 512
const ANNOTATION_MUTATION_ID_TTL_MS = 10 * 60_000

export class AnnotationReconciler {
  private readonly seenMutationIds = new Map<string, number>()
  private readonly pendingChangedFields = new Set<string>()
  private active: Promise<void> | null = null
  private reconciliationPasses = 0

  constructor(
    private readonly queryClient: QueryClient,
    private readonly project: (
      payload: ItemCacheUpdatePayload,
      options: ItemCacheUpdateOptions,
    ) => void,
    private readonly now: () => number = () => globalThis.performance?.now() ?? Date.now(),
  ) {}

  accept(projection: AnnotationProjection): boolean {
    const now = this.now()
    this.pruneSeen(now)
    if (this.seenMutationIds.has(projection.mutationId)) return false
    this.seenMutationIds.set(projection.mutationId, now)
    this.pruneSeen(now)

    this.project(projection.item, {
      removeConclusiveFilterMismatch: true,
      replaceMutableMetrics: projection.replaceMutableMetrics,
    })
    if (!this.hasRelevantActiveQuery(projection.changedFields)) return true
    for (const field of projection.changedFields) {
      this.pendingChangedFields.add(field)
    }
    this.startReconciliation()
    return true
  }

  diagnostics(): { seenMutationIds: number; active: boolean; reconciliationPasses: number } {
    this.pruneSeen(this.now())
    return {
      seenMutationIds: this.seenMutationIds.size,
      active: this.active !== null,
      reconciliationPasses: this.reconciliationPasses,
    }
  }

  async whenIdle(): Promise<void> {
    while (this.active) {
      await this.active
    }
  }

  private pruneSeen(now: number): void {
    for (const [mutationId, seenAt] of this.seenMutationIds) {
      if (now - seenAt <= ANNOTATION_MUTATION_ID_TTL_MS) break
      this.seenMutationIds.delete(mutationId)
    }
    while (this.seenMutationIds.size > ANNOTATION_MUTATION_ID_LIMIT) {
      const oldest = this.seenMutationIds.keys().next().value as string | undefined
      if (oldest === undefined) break
      this.seenMutationIds.delete(oldest)
    }
  }

  private hasRelevantActiveQuery(changedFields: readonly string[]): boolean {
    return this.queryClient.getQueryCache().findAll({ type: 'active' }).some((query) => (
      isReconciliationQueryKey(query.queryKey)
      && mutationAffectsDependencyManifest(
        changedFields,
        dependencyManifestFromData(query.state.data),
      )
    ))
  }

  private startReconciliation(): void {
    if (this.active) return
    const run = async () => {
      await this.runPass()
      if (this.pendingChangedFields.size > 0) {
        await this.runPass()
      }
    }
    this.active = run().finally(() => {
      this.active = null
      if (this.pendingChangedFields.size > 0) {
        this.startReconciliation()
      }
    })
  }

  private async runPass(): Promise<void> {
    const changedFields = Array.from(this.pendingChangedFields)
    this.pendingChangedFields.clear()
    const activeQueries = this.queryClient.getQueryCache().findAll({ type: 'active' }).filter((query) => (
      isReconciliationQueryKey(query.queryKey)
      && mutationAffectsDependencyManifest(
        changedFields,
        dependencyManifestFromData(query.state.data),
      )
    ))
    if (!activeQueries.length) return
    this.reconciliationPasses += 1
    await Promise.all(activeQueries.map((query) => this.queryClient.invalidateQueries({
      queryKey: query.queryKey,
      exact: true,
      refetchType: 'active',
    })))
  }
}

function isReconciliationQueryKey(queryKey: QueryKey): boolean {
  return Array.isArray(queryKey)
    && (queryKey[0] === 'folder-query' || queryKey[0] === 'folder-facets')
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

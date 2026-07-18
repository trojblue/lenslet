import type { BrowseItemPayload, BrowseWindowProjection, StarRating } from '../../lib/types'

export const BROWSE_ENTITY_MAX_UNREFERENCED = 2_000
export const BROWSE_ENTITY_UNREFERENCED_TTL_MS = 5 * 60_000

export type BrowseEntityPatch = {
  path: string
  star?: StarRating
  notes?: string | null
  metrics?: Record<string, number | null> | null
}

export type BrowseEntityPatchOptions = {
  replaceMutableMetrics?: boolean
}

export function patchBrowseEntity(
  current: BrowseItemPayload,
  patch: BrowseEntityPatch,
  options: BrowseEntityPatchOptions = {},
): BrowseItemPayload {
  let next = current
  if (Object.prototype.hasOwnProperty.call(patch, 'star') && current.star !== patch.star) {
    next = { ...next, star: patch.star ?? null }
  }
  if (patch.notes !== undefined && current.notes !== patch.notes) {
    next = { ...next, notes: patch.notes ?? '' }
  }
  if (patch.metrics === undefined) return next

  const incoming = patch.metrics ?? {}
  const owned = new Set(current.mutable_metric_keys ?? [])
  const metrics = { ...(current.metrics ?? {}) }
  if (options.replaceMutableMetrics) {
    for (const key of owned) delete metrics[key]
    owned.clear()
  }
  for (const [key, value] of Object.entries(incoming)) {
    if (value == null) {
      delete metrics[key]
      owned.delete(key)
    } else {
      metrics[key] = value
      owned.add(key)
    }
  }
  return {
    ...next,
    metrics: Object.keys(metrics).length ? metrics : undefined,
    mutable_metric_keys: Array.from(owned).sort(),
  }
}

type Listener = () => void
type ActiveOwner = object

export type BrowseEntityRequest = {
  sequence: number
  mutationVersion: number
  metricKeys: readonly string[]
  categoricalKeys: readonly string[]
}

type MutableFieldVersions = {
  star?: number
  notes?: number
  metrics?: number
}

export class BrowseEntityStore {
  private readonly entities = new Map<string, BrowseItemPayload>()
  private readonly listeners = new Map<string, Set<Listener>>()
  private readonly activePathsByOwner = new Map<ActiveOwner, Set<string>>()
  private readonly activeRefCounts = new Map<string, number>()
  private readonly unreferencedAt = new Map<string, number>()
  private readonly lastRequestSequence = new Map<string, number>()
  private readonly mutableFieldVersions = new Map<string, MutableFieldVersions>()
  private nextRequestSequence = 0
  private mutationVersion = 0

  constructor(
    private readonly now: () => number = () => Date.now(),
    private readonly maxUnreferenced = BROWSE_ENTITY_MAX_UNREFERENCED,
    private readonly unreferencedTtlMs = BROWSE_ENTITY_UNREFERENCED_TTL_MS,
  ) {}

  get(path: string): BrowseItemPayload | undefined {
    return this.entities.get(path)
  }

  beginRequest(projection?: BrowseWindowProjection): BrowseEntityRequest {
    this.nextRequestSequence += 1
    return {
      sequence: this.nextRequestSequence,
      mutationVersion: this.mutationVersion,
      metricKeys: projection?.metric_keys ?? [],
      categoricalKeys: projection?.categorical_keys ?? [],
    }
  }

  ingest(
    items: readonly BrowseItemPayload[],
    request: BrowseEntityRequest = this.beginRequest(),
  ): string[] {
    const byPath = new Map<string, BrowseItemPayload>()
    for (const item of items) {
      if (item.path) byPath.set(item.path, item)
    }
    const changed: string[] = []
    const now = this.now()
    for (const path of Array.from(byPath.keys()).sort()) {
      if ((this.lastRequestSequence.get(path) ?? 0) > request.sequence) continue
      const current = this.entities.get(path)
      const fieldVersions = this.mutableFieldVersions.get(path)
      const incoming = byPath.get(path)!
      let next = current
        ? mergeProjectedBrowseEntity(current, incoming, request)
        : incoming
      if (current && fieldVersions) {
        const updates: Partial<BrowseItemPayload> = {}
        if ((fieldVersions.star ?? 0) > request.mutationVersion) updates.star = current.star
        if ((fieldVersions.notes ?? 0) > request.mutationVersion) updates.notes = current.notes
        if ((fieldVersions.metrics ?? 0) > request.mutationVersion) {
          Object.assign(updates, preserveCurrentMutableMetrics(next, current))
        }
        if (Object.keys(updates).length) next = { ...next, ...updates }
      }
      this.entities.set(path, next)
      this.lastRequestSequence.set(path, request.sequence)
      if (!this.activeRefCounts.has(path)) this.unreferencedAt.set(path, now)
      changed.push(path)
    }
    this.prune(now)
    this.notify(changed)
    return changed
  }

  seed(items: readonly BrowseItemPayload[]): string[] {
    const byPath = new Map<string, BrowseItemPayload>()
    for (const item of items) {
      if (item.path && !this.entities.has(item.path)) byPath.set(item.path, item)
    }
    const changed = Array.from(byPath.keys()).sort()
    const now = this.now()
    for (const path of changed) {
      this.entities.set(path, byPath.get(path)!)
      if (!this.activeRefCounts.has(path)) this.unreferencedAt.set(path, now)
    }
    this.prune(now)
    this.notify(changed)
    return changed
  }

  patch(patch: BrowseEntityPatch, options: BrowseEntityPatchOptions = {}): boolean {
    const current = this.entities.get(patch.path)
    if (!current) return false
    const next = patchBrowseEntity(current, patch, options)
    const changedFields: MutableFieldVersions = {}
    if (next === current) return false
    if (next.star !== current.star) changedFields.star = 0
    if (next.notes !== current.notes) changedFields.notes = 0
    if (next.metrics !== current.metrics) changedFields.metrics = 0
    this.mutationVersion += 1
    const versions = this.mutableFieldVersions.get(patch.path) ?? {}
    for (const field of Object.keys(changedFields) as (keyof MutableFieldVersions)[]) {
      versions[field] = this.mutationVersion
    }
    this.mutableFieldVersions.set(patch.path, versions)
    this.entities.set(patch.path, next)
    this.notify([patch.path])
    return true
  }

  subscribe(path: string, listener: Listener): () => void {
    const listeners = this.listeners.get(path) ?? new Set<Listener>()
    listeners.add(listener)
    this.listeners.set(path, listeners)
    return () => {
      const current = this.listeners.get(path)
      if (!current) return
      current.delete(listener)
      if (!current.size) this.listeners.delete(path)
    }
  }

  setActivePaths(owner: ActiveOwner, paths: readonly string[]): void {
    const previous = this.activePathsByOwner.get(owner) ?? new Set<string>()
    const next = new Set(paths)
    const now = this.now()
    for (const path of previous) {
      if (next.has(path)) continue
      const count = (this.activeRefCounts.get(path) ?? 1) - 1
      if (count <= 0) {
        this.activeRefCounts.delete(path)
        if (this.entities.has(path)) this.unreferencedAt.set(path, now)
      } else {
        this.activeRefCounts.set(path, count)
      }
    }
    for (const path of next) {
      if (previous.has(path)) continue
      this.activeRefCounts.set(path, (this.activeRefCounts.get(path) ?? 0) + 1)
      this.unreferencedAt.delete(path)
    }
    if (next.size) this.activePathsByOwner.set(owner, next)
    else this.activePathsByOwner.delete(owner)
    this.prune(now)
  }

  release(owner: ActiveOwner): void {
    this.setActivePaths(owner, [])
  }

  evict(path: string): boolean {
    if (this.activeRefCounts.has(path) || !this.entities.delete(path)) return false
    this.unreferencedAt.delete(path)
    this.lastRequestSequence.delete(path)
    this.mutableFieldVersions.delete(path)
    return true
  }

  prune(now = this.now()): string[] {
    const removed: string[] = []
    const candidates = Array.from(this.unreferencedAt.entries())
      .filter(([path]) => this.entities.has(path) && !this.activeRefCounts.has(path))
      .sort((a, b) => a[1] - b[1] || a[0].localeCompare(b[0]))
    for (const [path, since] of candidates) {
      if (now - since < this.unreferencedTtlMs) continue
      if (this.entities.delete(path)) removed.push(path)
      this.unreferencedAt.delete(path)
      this.lastRequestSequence.delete(path)
      this.mutableFieldVersions.delete(path)
    }
    const retained = candidates.filter(([path]) => this.entities.has(path))
    const overflow = Math.max(0, retained.length - this.maxUnreferenced)
    for (const [path] of retained.slice(0, overflow)) {
      if (this.entities.delete(path)) removed.push(path)
      this.unreferencedAt.delete(path)
      this.lastRequestSequence.delete(path)
      this.mutableFieldVersions.delete(path)
    }
    return removed
  }

  size(): number {
    return this.entities.size
  }

  private notify(paths: readonly string[]): void {
    for (const path of paths) {
      for (const listener of this.listeners.get(path) ?? []) listener()
    }
  }
}

function mergeProjectedBrowseEntity(
  current: BrowseItemPayload,
  incoming: BrowseItemPayload,
  request: BrowseEntityRequest,
): BrowseItemPayload {
  const metrics = replaceProjectedKeys(current.metrics, incoming.metrics, request.metricKeys)
  const metricLabels = replaceProjectedKeys(
    current.metric_labels ?? undefined,
    incoming.metric_labels ?? undefined,
    request.metricKeys,
  )
  const categoricals = replaceProjectedKeys(
    current.categoricals ?? undefined,
    incoming.categoricals ?? undefined,
    request.categoricalKeys,
  )
  const mutableMetricKeys = new Set(current.mutable_metric_keys ?? [])
  for (const key of request.metricKeys) mutableMetricKeys.delete(key)
  for (const key of incoming.mutable_metric_keys ?? []) mutableMetricKeys.add(key)
  return {
    ...current,
    ...incoming,
    metrics,
    metric_labels: metricLabels,
    categoricals,
    mutable_metric_keys: Array.from(mutableMetricKeys).sort(),
  }
}

function replaceProjectedKeys<T>(
  current: Record<string, T> | undefined,
  incoming: Record<string, T> | undefined,
  projectedKeys: readonly string[],
): Record<string, T> | undefined {
  const next = { ...(current ?? {}) }
  for (const key of projectedKeys) delete next[key]
  Object.assign(next, incoming ?? {})
  return Object.keys(next).length ? next : undefined
}

function preserveCurrentMutableMetrics(
  next: BrowseItemPayload,
  current: BrowseItemPayload,
): Pick<BrowseItemPayload, 'metrics' | 'mutable_metric_keys'> {
  const metrics = { ...(next.metrics ?? {}) }
  for (const key of next.mutable_metric_keys ?? []) delete metrics[key]
  for (const key of current.mutable_metric_keys ?? []) {
    const value = current.metrics?.[key]
    if (value != null) metrics[key] = value
  }
  return {
    metrics: Object.keys(metrics).length ? metrics : undefined,
    mutable_metric_keys: current.mutable_metric_keys,
  }
}

export const browseEntityStore = new BrowseEntityStore()

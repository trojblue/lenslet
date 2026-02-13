import type { FolderIndex, Item } from '../../../lib/types'

export function dedupeItemsByPath(items: Item[]): Item[] {
  if (!items.length) return items
  const seen = new Set<string>()
  const deduped: Item[] = []
  for (const item of items) {
    if (seen.has(item.path)) continue
    seen.add(item.path)
    deduped.push(item)
  }
  return deduped
}

type RemainingPagesPlan = {
  startPage: number
  endPage: number
  pageSize: number
}

export type FolderHydrationProgress = {
  loadedPages: number
  totalPages: number
  loadedItems: number
  totalItems: number
  completed: boolean
}

type HydrateFolderPagesOptions = {
  defaultPageSize: number
  fetchPage: (page: number, pageSize: number) => Promise<FolderIndex>
  onUpdate: (value: FolderIndex) => void
  onProgress?: (progress: FolderHydrationProgress) => void
  shouldContinue?: () => boolean
  progressiveUpdates?: boolean
  interPageDelayMs?: number
  skipInitialUpdateIfPaged?: boolean
}

export function normalizeFolderPage(page: FolderIndex): FolderIndex {
  return {
    ...page,
    items: dedupeItemsByPath(page.items),
  }
}

export function getRemainingPagesPlan(firstPage: FolderIndex, defaultPageSize: number): RemainingPagesPlan | null {
  const endPage = firstPage.pageCount ?? 1
  const pageSize = firstPage.pageSize ?? defaultPageSize
  const startPage = (firstPage.page ?? 1) + 1
  if (endPage <= 1 || startPage > endPage) {
    return null
  }
  return { startPage, endPage, pageSize }
}

export function mergeFolderPages(base: FolderIndex, next: FolderIndex): FolderIndex {
  if (base.path !== next.path) {
    return normalizeFolderPage(next)
  }

  const mergedItems = dedupeItemsByPath([...base.items, ...next.items])
  return {
    ...base,
    generatedAt: next.generatedAt ?? base.generatedAt,
    dirs: base.dirs.length ? base.dirs : next.dirs,
    items: mergedItems,
    page: next.page ?? base.page,
    pageSize: next.pageSize ?? base.pageSize,
    pageCount: next.pageCount ?? base.pageCount,
    totalItems: next.totalItems ?? base.totalItems,
  }
}

export async function hydrateFolderPages(firstPage: FolderIndex, options: HydrateFolderPagesOptions): Promise<void> {
  const shouldContinue = options.shouldContinue ?? (() => true)
  const progressiveUpdates = options.progressiveUpdates ?? true
  const interPageDelayMs = Math.max(0, options.interPageDelayMs ?? 0)
  const plan = getRemainingPagesPlan(firstPage, options.defaultPageSize)
  const skipInitialUpdate = options.skipInitialUpdateIfPaged === true && plan !== null
  let merged = normalizeFolderPage(firstPage)
  const publishProgress = (completed: boolean) => {
    options.onProgress?.({
      loadedPages: merged.page ?? (plan ? plan.startPage - 1 : 1),
      totalPages: merged.pageCount ?? plan?.endPage ?? 1,
      loadedItems: merged.items.length,
      totalItems: merged.totalItems ?? merged.items.length,
      completed,
    })
  }
  if (!skipInitialUpdate) {
    options.onUpdate(merged)
  }
  publishProgress(false)
  if (!plan) {
    if (skipInitialUpdate) {
      options.onUpdate(merged)
    }
    publishProgress(true)
    return
  }

  let hasMergedAdditionalPage = false
  for (let page = plan.startPage; page <= plan.endPage; page += 1) {
    if (!shouldContinue()) return
    let nextPage: FolderIndex
    try {
      nextPage = await options.fetchPage(page, plan.pageSize)
    } catch {
      return
    }
    if (!shouldContinue()) return
    merged = mergeFolderPages(merged, nextPage)
    hasMergedAdditionalPage = true
    if (progressiveUpdates) {
      options.onUpdate(merged)
    }
    publishProgress(false)
    if (page < plan.endPage && interPageDelayMs > 0) {
      await new Promise<void>((resolve) => {
        setTimeout(resolve, interPageDelayMs)
      })
      if (!shouldContinue()) return
    }
  }

  if (!progressiveUpdates && hasMergedAdditionalPage) {
    options.onUpdate(merged)
  }
  publishProgress(true)
}

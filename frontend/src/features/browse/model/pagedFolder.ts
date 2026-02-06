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

export function normalizeFolderPage(page: FolderIndex): FolderIndex {
  return {
    ...page,
    items: dedupeItemsByPath(page.items),
  }
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

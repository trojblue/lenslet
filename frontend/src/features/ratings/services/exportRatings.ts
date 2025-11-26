import type { Item } from '../../../lib/types'

export type RatingRecord = { path: string; name: string; star: number | null; tags?: string[]; notes?: string }

export function toRatingsJson(items: RatingRecord[]): string {
  return JSON.stringify(items, null, 2)
}

export function toRatingsCsv(items: RatingRecord[]): string {
  const esc = (s: string) => '"' + s.replaceAll('"', '""') + '"'
  const header = 'path,name,star,tags,notes'
  const lines = items.map(it => {
    const tags = (it.tags || []).join(' ')
    const notes = it.notes || ''
    return [it.path, it.name, String(it.star ?? ''), tags, notes].map(v => esc(String(v))).join(',')
  })
  return [header, ...lines].join('\n')
}

// Helper to map displayed items (without sidecars) into rating records quickly
export function mapItemsToRatings(items: Item[]): RatingRecord[] {
  return items.map(it => ({ path: it.path, name: it.name, star: (it as any).star ?? null }))
}



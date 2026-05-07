import type { BrowseItemPayload } from '../../../lib/types'

export type RatingRecord = {
  path: string
  folder: string
  name: string
  star: number | null
  type?: string
  size?: number
  width?: number
  height?: number
  tags?: string[]
  notes?: string
}

export function toRatingsJson(items: RatingRecord[]): string {
  return JSON.stringify(items, null, 2)
}

export function toRatingsCsv(items: RatingRecord[]): string {
  const esc = (s: string) => '"' + s.replaceAll('"', '""') + '"'
  const header = 'path,folder,name,star,type,size,width,height,tags,notes'
  const lines = items.map(it => {
    const tags = (it.tags || []).join(' ')
    const notes = it.notes || ''
    return [
      it.path,
      it.folder,
      it.name,
      String(it.star ?? ''),
      it.type ?? '',
      it.size ?? '',
      it.width ?? '',
      it.height ?? '',
      tags,
      notes,
    ]
      .map(v => esc(String(v)))
      .join(',')
  })
  return [header, ...lines].join('\n')
}

// Helper to map displayed items (without sidecars) into rating records quickly
export function mapItemsToRatings(items: BrowseItemPayload[]): RatingRecord[] {
  return items.map(it => {
    const parts = it.path.split('/').filter(Boolean)
    parts.pop() // remove filename
    const folder = parts.length ? `/${parts.join('/')}` : '/'
    return {
      path: it.path,
      folder,
      name: it.name,
      star: (it as any).star ?? null,
      type: it.mime,
      size: it.size,
      width: (it as any).width,
      height: (it as any).height,
      // tags/notes are not available without sidecar fetch; keep empty
    }
  })
}

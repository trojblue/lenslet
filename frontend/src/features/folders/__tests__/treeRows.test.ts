import { describe, expect, it } from 'vitest'
import type { BrowseFolderPayload } from '../../../lib/types'
import { expandedAncestorPaths, flattenFolderRows, folderKeyboardTarget } from '../model/treeRows'

const folder = (path: string, children: string[]): BrowseFolderPayload => ({
  version: 1, path, generated_at: 'test', items: [],
  folders: children.map((name) => ({ name, kind: 'branch' })),
  metric_keys: [], categorical_keys: [],
})
const roots = [{ path: '/', label: 'Root' }]

describe('logical folder rows', () => {
  it('shows indexed counts for unopened children and replaces them on refresh', () => {
    const root = folder('/', ['alpha', 'beta'])
    root.folders[0].total_items = 42
    root.folders[1].total_items = 0
    const rows = () => flattenFolderRows(roots, new Set(['/']), { '/': root }, new Set())
    expect(rows().slice(1).map((row) => row.totalItems)).toEqual([42, 0])
    root.folders[0].total_items = 7
    expect(rows()[1].totalItems).toBe(7)
  })

  it('preserves depth, sibling position and cached expanded descendants regardless of viewport', () => {
    const payloads = { '/': folder('/', ['alpha', 'beta']), '/alpha': folder('/alpha', ['nested']) }
    const expanded = new Set(['/', '/alpha'])
    const rows = flattenFolderRows(roots, expanded, payloads, new Set())
    expect(rows.map((row) => [row.path, row.depth, row.position, row.siblings])).toEqual([
      ['/', 0, 1, 1], ['/alpha', 1, 1, 2], ['/alpha/nested', 2, 1, 1], ['/beta', 1, 2, 2],
    ])
    expanded.delete('/alpha')
    expect(flattenFolderRows(roots, expanded, payloads, new Set()).map((row) => row.path)).toEqual(['/', '/alpha', '/beta'])
    expanded.add('/alpha')
    expect(flattenFolderRows(roots, expanded, payloads, new Set())).toEqual(rows)
  })

  it('navigates the full 10,000-folder model rather than mounted DOM and skips status rows', () => {
    const payloads = { '/': folder('/', Array.from({ length: 10_000 }, (_,index) => `folder_${index}`)) }
    const rows = flattenFolderRows(roots, new Set(['/', '/folder_0']), payloads, new Set(['/folder_0']))
    expect(folderKeyboardTarget(rows, '/', 'End')).toBe(rows.length - 1)
    expect(folderKeyboardTarget(rows, '/folder_9999', 'Home')).toBe(0)
    expect(rows[folderKeyboardTarget(rows, '/folder_0', 'ArrowDown')].path).toBe('/folder_1')
    expect(rows[2].kind).toBe('error')
  })

  it('derives current ancestors before first paint, distinguishes pending from leaf', () => {
    expect(expandedAncestorPaths('/alpha/nested')).toEqual(['/', '/alpha', '/alpha/nested'])
    expect(flattenFolderRows(roots, new Set(['/']), {}, new Set()).map((row) => row.kind)).toEqual(['folder', 'pending'])
    expect(flattenFolderRows(roots, new Set(['/']), { '/': folder('/', []) }, new Set())).toMatchObject([{ leaf: true, expanded: false }])
  })
})

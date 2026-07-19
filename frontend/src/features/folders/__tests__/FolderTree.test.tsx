import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import type { BrowseFolderPayload } from '../../../lib/types'
import FolderTree, { shouldObserveFolderNode } from '../FolderTree'

const ROOT_DATA: BrowseFolderPayload = {
  version: 1,
  path: '/',
  generated_at: 'test',
  items: [],
  folders: [{ name: 'shots', kind: 'branch' }],
  metric_keys: [],
  categorical_keys: [],
}

function renderTree(data?: BrowseFolderPayload): string {
  const queryClient = new QueryClient()
  return renderToStaticMarkup(
    <QueryClientProvider client={queryClient}>
      <FolderTree current="/" roots={[{ label: 'Root', path: '/' }]} data={data} onOpen={() => {}} />
    </QueryClientProvider>,
  )
}

describe('FolderTree stable rows', () => {
  it('does not observe expanded folder queries while its surface is hidden', () => {
    expect(shouldObserveFolderNode(false, '/', true, true)).toBe(false)
    expect(shouldObserveFolderNode(false, '/shots', true, false)).toBe(false)
    expect(shouldObserveFolderNode(true, '/shots', true, false)).toBe(true)
  })

  it('renders one reserved pending child row and stable columns', () => {
    const html = renderTree()

    expect(html).toContain('folder-tree-scroll')
    expect(html).toContain('tree-row-count')
    expect(html).toContain('tree-row-action-placeholder')
    expect(html).toContain('Loading folders…')
  })

  it('replaces the pending row with terminal children', () => {
    const html = renderTree(ROOT_DATA)

    expect(html).toContain('shots')
    expect(html).not.toContain('Loading folders…')
  })
})

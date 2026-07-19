import { describe, expect, it, vi } from 'vitest'
import type { BrowseItemPayload, Sidecar } from '../../../../lib/types'
import {
  buildInspectorTargetCandidate,
  inspectorPresentationIsTransitioning,
  selectInspectorPresentation,
  type InspectorMetadataPresentation,
  type InspectorPreviewPresentation,
  type StoredInspectorPresentation,
} from '../inspectorPresentation'

const item = (path: string): BrowseItemPayload => ({
  path,
  name: path.slice(1),
  mime: 'image/png',
  width: 64,
  height: 48,
  size: 123,
  has_thumbnail: true,
  has_metadata: true,
})

const sidecar = (notes: string): Sidecar => ({
  v: 1,
  tags: [notes],
  notes,
  version: 1,
  updated_at: '',
  updated_by: 'test',
})

const metadata = (prompt: string, state: InspectorMetadataPresentation['state'] = 'loaded') => ({
  raw: state === 'loaded' ? { prompt } : null,
  error: null,
  state,
  showPilInfo: false,
})

const preview = (path: string): InspectorPreviewPresentation => ({
  status: 'ready',
  url: `blob:${path}`,
})

function readyCandidate(path: string, resetKey = 'workspace-a') {
  return buildInspectorTargetCandidate({
    resetKey,
    identity: JSON.stringify([path, [path]]),
    path,
    selectedPaths: [path],
    comparePaths: [path],
    items: [item(path)],
    item: { status: 'ready', value: item(path) },
    sidecar: { status: 'ready', value: sidecar(path) },
    metadata: { status: 'ready', value: metadata(path) },
    preview: { status: 'ready', value: preview(path) },
  })
}

describe('Inspector presentation settlement', () => {
  it('retains complete A until every B dependency is terminal', () => {
    const candidateA = readyCandidate('/a.png')
    expect(candidateA.status).toBe('ready')
    if (candidateA.status !== 'ready') throw new Error('candidate A did not settle')
    const stored: StoredInspectorPresentation = { resetKey: 'workspace-a', snapshot: candidateA.snapshot }
    const candidateB = buildInspectorTargetCandidate({
      resetKey: 'workspace-a',
      identity: JSON.stringify(['/b.png', ['/b.png']]),
      path: '/b.png',
      selectedPaths: ['/b.png'],
      comparePaths: ['/b.png'],
      items: [item('/b.png')],
      item: { status: 'ready', value: item('/b.png') },
      sidecar: { status: 'ready', value: sidecar('/b.png') },
      metadata: { status: 'pending' },
      preview: { status: 'ready', value: preview('/b.png') },
    })

    expect(selectInspectorPresentation(stored, candidateB, 'workspace-a')).toBe(candidateA.snapshot)
    expect(inspectorPresentationIsTransitioning(candidateB, candidateA.snapshot)).toBe(true)
  })

  it('promotes the latest complete target atomically and ignores a superseded result', () => {
    const candidateA = readyCandidate('/a.png')
    const candidateB = readyCandidate('/b.png')
    if (candidateA.status !== 'ready' || candidateB.status !== 'ready') {
      throw new Error('fixtures did not settle')
    }
    const stored = { resetKey: 'workspace-a', snapshot: candidateA.snapshot }
    const pendingC = buildInspectorTargetCandidate({
      resetKey: 'workspace-a',
      identity: JSON.stringify(['/c.png', ['/c.png']]),
      path: '/c.png',
      selectedPaths: ['/c.png'],
      comparePaths: ['/c.png'],
      items: [item('/c.png')],
      item: { status: 'ready', value: item('/c.png') },
      sidecar: { status: 'pending' },
      metadata: { status: 'pending' },
      preview: { status: 'pending' },
    })

    expect(selectInspectorPresentation(stored, candidateB, 'workspace-a')?.path).toBe('/b.png')
    expect(selectInspectorPresentation(stored, pendingC, 'workspace-a')?.path).toBe('/a.png')
  })

  it.each(['item', 'sidecar', 'metadata', 'preview'] as const)(
    'settles a coherent target-owned error when %s fails',
    (failedDependency) => {
      const retry = vi.fn()
      const candidate = buildInspectorTargetCandidate({
        resetKey: 'workspace-a',
        identity: 'b',
        path: '/b.png',
        selectedPaths: ['/b.png'],
        comparePaths: ['/b.png'],
        items: [item('/b.png')],
        item: failedDependency === 'item'
          ? { status: 'error', message: 'detail failed', fallback: item('/b.png') }
          : { status: 'ready', value: item('/b.png') },
        sidecar: failedDependency === 'sidecar'
          ? { status: 'error', message: 'sidecar failed', fallback: null }
          : { status: 'ready', value: sidecar('/b.png') },
        metadata: failedDependency === 'metadata'
          ? {
            status: 'error',
            message: 'metadata failed',
            fallback: { ...metadata('', 'error'), error: 'metadata failed' },
          }
          : { status: 'ready', value: metadata('/b.png') },
        preview: failedDependency === 'preview'
          ? {
            status: 'error',
            message: 'preview failed',
            fallback: { status: 'error', message: 'preview failed', retry },
          }
          : { status: 'ready', value: preview('/b.png') },
      })

      expect(candidate.status).toBe('ready')
      if (candidate.status !== 'ready') throw new Error('error candidate did not settle')
      expect(candidate.snapshot.path).toBe('/b.png')
      expect(candidate.snapshot.preview.status).not.toBe('idle')
    },
  )

  it('treats autoload-off metadata as settled idle', () => {
    const candidate = buildInspectorTargetCandidate({
      resetKey: 'workspace-a',
      identity: 'b',
      path: '/b.png',
      selectedPaths: ['/b.png'],
      comparePaths: ['/b.png'],
      items: [item('/b.png')],
      item: { status: 'ready', value: item('/b.png') },
      sidecar: { status: 'ready', value: sidecar('/b.png') },
      metadata: { status: 'ready', value: metadata('', 'idle') },
      preview: { status: 'ready', value: preview('/b.png') },
    })

    expect(candidate.status).toBe('ready')
    if (candidate.status === 'ready') expect(candidate.snapshot.metadata.state).toBe('idle')
  })

  it('clears retained presentation synchronously at a hard reset', () => {
    const candidateA = readyCandidate('/a.png')
    if (candidateA.status !== 'ready') throw new Error('fixture did not settle')
    const stored = { resetKey: 'workspace-a', snapshot: candidateA.snapshot }
    const pendingB = { status: 'pending', identity: 'b', resetKey: 'workspace-b' } as const

    expect(selectInspectorPresentation(stored, pendingB, 'workspace-b')).toBeNull()
    expect(selectInspectorPresentation(stored, candidateA, 'workspace-b')).toBeNull()

    const freshCandidate = readyCandidate('/a.png', 'workspace-b')
    expect(selectInspectorPresentation(stored, freshCandidate, 'workspace-b')?.resetKey)
      .toBe('workspace-b')
  })

  it('clears retained presentation synchronously when selection becomes idle', () => {
    const candidateA = readyCandidate('/a.png')
    if (candidateA.status !== 'ready') throw new Error('fixture did not settle')
    const stored = { resetKey: 'workspace-a', snapshot: candidateA.snapshot }

    expect(
      selectInspectorPresentation(
        stored,
        { status: 'idle', identity: null, resetKey: 'workspace-a' },
        'workspace-a',
      ),
    ).toBeNull()
  })
})

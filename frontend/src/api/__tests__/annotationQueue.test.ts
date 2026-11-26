import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Sidecar, SidecarMutationResponse, SidecarPatch } from '../../lib/types'
import { FetchError } from '../../lib/fetcher'

type Server = Map<string, Sidecar>

const server: Server = new Map()
const patches: Array<{ path: string; body: SidecarPatch; ifMatch?: number }> = []
let failNextPatch: Array<FetchError | Error> = []
let raceBeforeNextPatch: ((path: string) => void) | null = null

function sidecar(overrides: Partial<Sidecar> = {}): Sidecar {
  return { v: 1, tags: [], notes: '', star: null, version: 1, updated_at: '', updated_by: 'server', ...overrides }
}

function applyPatch(current: Sidecar, body: SidecarPatch): Sidecar {
  let tags = body.set_tags ?? current.tags
  tags = tags.filter((tag) => !(body.remove_tags ?? []).includes(tag))
  for (const tag of body.add_tags ?? []) if (!tags.includes(tag)) tags = [...tags, tag]
  return {
    ...current,
    tags,
    star: body.set_star !== undefined ? body.set_star : current.star,
    notes: body.set_notes !== undefined ? body.set_notes : current.notes,
    version: current.version + 1,
  }
}

vi.mock('../client', () => ({
  makeIdempotencyKey: (prefix: string) => `${prefix}-${Math.random()}`,
  api: {
    getSidecar: vi.fn(async (path: string) => {
      const current = server.get(path)
      if (!current) throw new FetchError(404, 'not found', path)
      return { ...current }
    }),
    patchSidecar: vi.fn(async (path: string, body: SidecarPatch, opts?: { ifMatch?: number }) => {
      raceBeforeNextPatch?.(path)
      raceBeforeNextPatch = null
      const failure = failNextPatch.shift()
      if (failure) throw failure
      const current = server.get(path)
      if (!current) throw new FetchError(404, 'not found', path)
      if (opts?.ifMatch !== current.version) {
        throw new FetchError(409, 'version_conflict', path, { current })
      }
      patches.push({ path, body, ifMatch: opts?.ifMatch })
      const next = applyPatch(current, body)
      server.set(path, next)
      const response: SidecarMutationResponse = {
        sidecar: next,
        mutation_id: 'm',
        accepted_event: null,
        persistence: 'saved',
        durable_watermark: { boot_epoch: 'b', event_id: 1 },
      }
      return response
    }),
  },
}))

const items = await import('../items')

async function settle(): Promise<void> {
  for (let i = 0; i < 20; i += 1) await vi.advanceTimersByTimeAsync(0)
}

function status(): { state: string; message?: string } {
  let latest = { state: 'idle' } as { state: string; message?: string }
  items.subscribeSyncStatus((next) => { latest = next })()
  return latest
}

describe('annotation queue', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    server.clear()
    patches.length = 0
    failNextPatch = []
    raceBeforeNextPatch = null
    items.resetAnnotationQueueForTests()
  })

  afterEach(() => {
    items.resetAnnotationQueueForTests()
    vi.useRealTimers()
  })

  it('keeps a failed rating queued, reports it, and retries until it is saved', async () => {
    server.set('/a.jpg', sidecar())
    server.set('/b.jpg', sidecar())
    failNextPatch = [new TypeError('network down')]
    items.enqueueAnnotationEdit('/a.jpg', { star: 3 })
    await settle()
    expect(server.get('/a.jpg')?.star).toBeNull()
    expect(status()).toMatchObject({ state: 'error', message: 'a.jpg, retrying' })
    expect(items.hasUnsavedAnnotations()).toBe(true)

    // Another image saving must not hide the unsaved one.
    items.enqueueAnnotationEdit('/b.jpg', { star: 5 })
    await settle()
    expect(server.get('/b.jpg')?.star).toBe(5)
    expect(status().state).toBe('error')

    await vi.advanceTimersByTimeAsync(1_000)
    await settle()
    expect(server.get('/a.jpg')?.star).toBe(3)
    expect(items.hasUnsavedAnnotations()).toBe(false)
    expect(status().state).toBe('idle')
  })

  it('keeps the user text in a conflict when another writer changed the notes', async () => {
    server.set('/a.jpg', sidecar({ notes: 'theirs', version: 2 }))
    items.enqueueAnnotationEdit('/a.jpg', { notes: { from: 'original', to: 'mine' }, star: 4 })
    await settle()
    expect(server.get('/a.jpg')).toMatchObject({ notes: 'theirs', star: 4 })
    expect(items.getConflict('/a.jpg')).toMatchObject({ mine: 'mine', current: { notes: 'theirs' } })
    expect(status()).toMatchObject({ state: 'error', message: 'conflicting notes on a.jpg' })

    // Keep mine: overwrite exactly the server text the user has now seen.
    items.clearConflict('/a.jpg')
    items.enqueueAnnotationEdit('/a.jpg', { notes: { from: 'theirs', to: 'mine' } })
    await settle()
    expect(server.get('/a.jpg')?.notes).toBe('mine')
  })

  it('re-reads and resends when another write lands between read and write', async () => {
    server.set('/a.jpg', sidecar({ notes: 'base' }))
    raceBeforeNextPatch = (path) => {
      server.set(path, applyPatch(server.get(path)!, { add_tags: ['theirs'] }))
    }
    items.enqueueAnnotationEdit('/a.jpg', { notes: { from: 'base', to: 'mine' }, addTags: ['mine'] })
    await settle()
    expect(server.get('/a.jpg')).toMatchObject({ notes: 'mine', tags: ['theirs', 'mine'], version: 3 })
    expect(patches[patches.length - 1]?.ifMatch).toBe(2)
  })

  it('restores server truth and names the image when the server refuses an edit', async () => {
    const published: Array<{ path: string; star: unknown }> = []
    const off = items.subscribeAnnotationMutationResponses((mutation) => {
      published.push({ path: mutation.path, star: mutation.response.sidecar.star })
    })
    server.set('/a.jpg', sidecar({ star: 2 }))
    failNextPatch = [new FetchError(403, 'forbidden', '/item')]
    items.enqueueAnnotationEdit('/a.jpg', { star: 5 })
    await settle()
    off()
    expect(server.get('/a.jpg')?.star).toBe(2)
    expect(published).toEqual([{ path: '/a.jpg', star: 2 }])
    expect(status()).toMatchObject({ state: 'error', message: 'a.jpg: not allowed to edit labels' })
    expect(items.hasUnsavedAnnotations()).toBe(false)
  })

  it('coalesces rapid edits to one image and sends the latest intent', async () => {
    server.set('/a.jpg', sidecar())
    items.enqueueAnnotationEdit('/a.jpg', { star: 1 })
    items.enqueueAnnotationEdit('/a.jpg', { star: 2 })
    items.enqueueAnnotationEdit('/a.jpg', { star: 4 })
    await settle()
    expect(server.get('/a.jpg')?.star).toBe(4)
    expect(patches.length).toBeLessThanOrEqual(2)
  })

  it('composes tag diffs so later edits win and cancel earlier ones', () => {
    expect(items.mergeAnnotationEdits({ addTags: ['a', 'b'] }, { removeTags: ['a'] }))
      .toEqual({ addTags: ['b'], removeTags: ['a'] })
    expect(items.mergeAnnotationEdits({ removeTags: ['x'] }, { addTags: ['x'] }))
      .toEqual({ addTags: ['x'] })
    expect(items.mergeAnnotationEdits(
      { notes: { from: 'start', to: 'mid' } },
      { notes: { from: 'mid', to: 'end' } },
    )).toEqual({ notes: { from: 'start', to: 'end' } })
    expect(items.tagEditBetween(['a', 'b'], ['b', 'c'])).toEqual({ addTags: ['c'], removeTags: ['a'] })
  })
})

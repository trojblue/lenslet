import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Sidecar, SidecarMutationResponse, SidecarPatch } from '../../lib/types'
import { FetchError } from '../../lib/fetcher'

type Server = Map<string, Sidecar>

const server: Server = new Map()
const patches: Array<{ path: string; body: SidecarPatch; ifMatch?: number }> = []
let failNextPatch: Array<FetchError | Error> = []
let raceBeforeNextPatch: ((path: string) => void) | null = null
let loseNextResponse = false
let persistence: { epoch: string; pending: boolean } = { epoch: 'b', pending: false }
let nextEventId = 1
const answered = new Map<string, SidecarMutationResponse>()

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
    patchSidecar: vi.fn(async (
      path: string,
      body: SidecarPatch,
      opts?: { ifMatch?: number; idempotencyKey?: string },
    ) => {
      const replay = opts?.idempotencyKey ? answered.get(opts.idempotencyKey) : undefined
      if (replay) return replay
      raceBeforeNextPatch?.(path)
      raceBeforeNextPatch = null
      const failure = failNextPatch.shift()
      if (failure) throw failure
      const current = server.get(path)
      if (!current) throw new FetchError(404, 'not found', path)
      if (opts?.ifMatch !== current.version) {
        throw new FetchError(409, 'version_conflict', path, { error: 'version_conflict', current })
      }
      patches.push({ path, body, ifMatch: opts?.ifMatch })
      const next = applyPatch(current, body)
      server.set(path, next)
      const eventId = nextEventId++
      const response: SidecarMutationResponse = {
        sidecar: next,
        mutation_id: 'm',
        accepted_event: { boot_epoch: persistence.epoch, event_id: eventId },
        persistence: persistence.pending ? 'pending' : 'saved',
        durable_watermark: { boot_epoch: persistence.epoch, event_id: persistence.pending ? 0 : eventId },
      }
      if (opts?.idempotencyKey) answered.set(opts.idempotencyKey, response)
      if (loseNextResponse) {
        loseNextResponse = false
        throw new TypeError('connection reset')
      }
      return response
    }),
  },
}))

const items = await import('../items')
const { labelPersistenceTracker } = await import('../labelPersistence')

function serverStatus(epoch: string, durableEventId: number) {
  return {
    enabled: true,
    boot_epoch: epoch,
    state: 'saved' as const,
    durable_watermark: { boot_epoch: epoch, event_id: durableEventId },
    pending_count: 0,
    pending_bytes: 0,
    max_pending_count: 10_000,
    max_pending_bytes: 1,
    oldest_pending_age_ms: null,
    error: null,
    failure_total: 0,
    deadline_breach_total: 0,
  }
}

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
    loseNextResponse = false
    persistence = { epoch: 'b', pending: false }
    nextEventId = 1
    answered.clear()
    labelPersistenceTracker.reset()
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

    // Text typed while the conflict is open lives in the conflict until resolved.
    items.updateConflictMine('/a.jpg', 'mine, revised')
    expect(items.getConflict('/a.jpg')?.mine).toBe('mine, revised')
    expect(items.hasUnsavedAnnotations()).toBe(true)

    // Keep mine: overwrite exactly the server text the user has now seen.
    items.clearConflict('/a.jpg')
    items.enqueueAnnotationEdit('/a.jpg', { notes: { from: 'theirs', to: 'mine, revised' } })
    await settle()
    expect(server.get('/a.jpg')?.notes).toBe('mine, revised')
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

  it('appends a multi-select note to each image without replacing existing notes', async () => {
    server.set('/a.jpg', sidecar({ notes: 'blurry' }))
    server.set('/b.jpg', sidecar())
    items.enqueueAnnotationEdits(['/a.jpg', '/b.jpg'], { appendNotes: 'reviewed' })
    await settle()
    expect(server.get('/a.jpg')?.notes).toBe('blurry\nreviewed')
    expect(server.get('/b.jpg')?.notes).toBe('reviewed')
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

  it('resends an applied write whose answer was lost instead of applying it twice', async () => {
    server.set('/a.jpg', sidecar({ notes: 'old' }))
    loseNextResponse = true
    items.enqueueAnnotationEdits(['/a.jpg'], { appendNotes: 'new', star: 2 })
    await settle()
    // Another writer rates the image after our (unacknowledged) write landed.
    server.set('/a.jpg', applyPatch(server.get('/a.jpg')!, { set_star: 5 }))
    await vi.advanceTimersByTimeAsync(1_000)
    await settle()
    expect(server.get('/a.jpg')).toMatchObject({ notes: 'old\nnew', star: 5 })
    expect(items.hasUnsavedAnnotations()).toBe(false)
  })

  it('keeps an accepted write until it is on disk, and resends it if the server lost it', async () => {
    server.set('/a.jpg', sidecar({ notes: '' }))
    persistence = { epoch: 'e1', pending: true }
    labelPersistenceTracker.observeStatus(serverStatus('e1', 0))
    items.enqueueAnnotationEdit('/a.jpg', { appendNotes: 'kept', star: 3 })
    await settle()
    expect(items.hasUnsavedAnnotations()).toBe(true)

    // The server crashes before saving: its replacement starts from disk.
    server.set('/a.jpg', sidecar({ notes: '' }))
    answered.clear()
    persistence = { epoch: 'e2', pending: false }
    labelPersistenceTracker.observeStatus(serverStatus('e2', 0))
    await settle()
    expect(server.get('/a.jpg')).toMatchObject({ notes: 'kept', star: 3 })
    expect(items.hasUnsavedAnnotations()).toBe(false)
  })

  it('forgets an accepted write once the server reports it saved', async () => {
    server.set('/a.jpg', sidecar())
    persistence = { epoch: 'e1', pending: true }
    labelPersistenceTracker.observeStatus(serverStatus('e1', 0))
    items.enqueueAnnotationEdit('/a.jpg', { star: 4 })
    await settle()
    expect(items.hasUnsavedAnnotations()).toBe(true)
    labelPersistenceTracker.observeStatus(serverStatus('e1', 1))
    expect(items.hasUnsavedAnnotations()).toBe(false)
    expect(patches).toHaveLength(1)
  })

  it('reports the unanswered rating for an image until the server answers it', async () => {
    server.set('/a.jpg', sidecar({ star: 1 }))
    items.enqueueAnnotationEdit('/a.jpg', { star: 3 })
    expect(items.pendingAnnotationStar('/a.jpg')).toBe(3)
    items.enqueueAnnotationEdit('/a.jpg', { addTags: ['x'] })
    expect(items.pendingAnnotationStar('/a.jpg')).toBe(3)
    await settle()
    expect(server.get('/a.jpg')?.star).toBe(3)
    expect(items.pendingAnnotationStar('/a.jpg')).toBeUndefined()
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

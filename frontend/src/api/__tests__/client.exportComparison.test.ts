import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../client'
import type { ExportComparisonRequest } from '../../lib/types'

function resetExportComparisonApiTestState(): void {
  vi.restoreAllMocks()
}

describe('exportComparison api contract', () => {
  beforeEach(resetExportComparisonApiTestState)
  afterEach(resetExportComparisonApiTestState)

  it('posts export payload and returns a blob', async () => {
    const sourceBlob = new Blob([new Uint8Array([1, 2, 3, 4])], { type: 'image/png' })
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(sourceBlob, { status: 200, headers: { 'content-type': 'image/png' } }),
    )

    const payload: ExportComparisonRequest = {
      v: 1,
      paths: ['/a.png', '/b.png'],
      labels: ['Prompt A', 'Prompt B'],
      embed_metadata: true,
      reverse_order: false,
    }

    const blob = await api.exportComparison(payload)

    expect(fetchSpy).toHaveBeenCalledTimes(1)
    const [url, init] = fetchSpy.mock.calls[0]
    expect(String(url)).toContain('/export-comparison')
    expect(init?.method).toBe('POST')
    expect((init?.headers as Record<string, string>)['Content-Type']).toBe('application/json')
    expect(init?.body).toBe(JSON.stringify(payload))
    expect(blob.type).toBe('image/png')
    expect(blob.size).toBe(sourceBlob.size)
  })

  it('keeps reverse_order in the request body for reverse export', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(new Blob([new Uint8Array([7])], { type: 'image/png' }), {
        status: 200,
        headers: { 'content-type': 'image/png' },
      }),
    )

    await api.exportComparison({
      v: 1,
      paths: ['/a.png', '/b.png'],
      labels: ['A label', 'B label'],
      embed_metadata: false,
      reverse_order: true,
    })

    const [, init] = fetchSpy.mock.calls[0]
    const parsed = JSON.parse(String(init?.body)) as ExportComparisonRequest
    expect(parsed.reverse_order).toBe(true)
    expect(parsed.paths).toEqual(['/a.png', '/b.png'])
    expect(parsed.labels).toEqual(['A label', 'B label'])
  })

  it('supports posting v2 export payloads', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(new Blob([new Uint8Array([9, 8])], { type: 'image/png' }), {
        status: 200,
        headers: { 'content-type': 'image/png' },
      }),
    )

    await api.exportComparison({
      v: 2,
      paths: ['/a.png', '/b.png', '/c.png'],
      labels: ['A label', 'B label', 'C label'],
      embed_metadata: true,
      reverse_order: false,
    })

    const [, init] = fetchSpy.mock.calls[0]
    const parsed = JSON.parse(String(init?.body)) as ExportComparisonRequest
    expect(parsed.v).toBe(2)
    expect(parsed.paths).toEqual(['/a.png', '/b.png', '/c.png'])
    expect(parsed.labels).toEqual(['A label', 'B label', 'C label'])
  })
})

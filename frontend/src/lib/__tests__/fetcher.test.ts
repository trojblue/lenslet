import { afterEach, describe, expect, it, vi } from 'vitest'
import { FetchError, fetchBlob, fetchJSON } from '../fetcher'

afterEach(() => {
  vi.unstubAllGlobals()
})

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

async function expectFetchError(promise: Promise<unknown>): Promise<FetchError> {
  try {
    await promise
  } catch (error) {
    expect(error).toBeInstanceOf(FetchError)
    return error as FetchError
  }
  throw new Error('expected fetch to fail')
}

describe('fetcher error messages', () => {
  it('uses FastAPI string detail for JSON failures', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: 'file not found' }, 404)))

    const error = await expectFetchError(fetchJSON('/item').promise)

    expect(error.message).toBe('file not found')
    expect(error.body).toEqual({ detail: 'file not found' })
  })

  it('summarizes FastAPI validation detail arrays', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(
          {
            detail: [
              { loc: ['body', 'query', 'path'], msg: 'Field required', type: 'missing' },
              { loc: ['body', 'top_k'], msg: 'Input should be greater than 0', type: 'greater_than' },
            ],
          },
          422
        )
      )
    )

    const error = await expectFetchError(fetchJSON('/embeddings/search').promise)

    expect(error.message).toBe(
      'validation failed: body.query.path: Field required; body.top_k: Input should be greater than 0'
    )
  })

  it('parses JSON error envelopes for blob failures', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({ error: 'export_failed', message: 'too many paths' }, 400))
    )

    const error = await expectFetchError(fetchBlob('/export-comparison').promise)

    expect(error.message).toBe('export_failed: too many paths')
    expect(error.body).toEqual({ error: 'export_failed', message: 'too many paths' })
  })
})

import { describe, expect, it } from 'vitest'
import { FetchError } from '../fetcher'
import {
  browserDecodeMediaError,
  isAbortMediaError,
  mediaErrorFromUnknown,
  mediaErrorSummary,
} from '../mediaResourceState'

describe('media resource error state', () => {
  it('keeps cancelled media requests out of visible retry errors', () => {
    const abort = new Error('request aborted')
    abort.name = 'AbortError'

    expect(isAbortMediaError(abort)).toBe(true)
    expect(mediaErrorFromUnknown(abort)).toMatchObject({
      category: 'aborted',
      retryable: false,
    })
  })

  it('preserves typed backend media error categories from HTTP failures', () => {
    expect(mediaErrorFromUnknown(new FetchError(403, 'remote source access denied', '/file'))).toMatchObject({
      category: 'permission',
      retryable: true,
      status: 403,
    })
    expect(mediaErrorFromUnknown(new FetchError(504, 'remote source timed out', '/file'))).toMatchObject({
      category: 'timeout',
      retryable: true,
    })
    expect(mediaErrorFromUnknown(new FetchError(422, 'failed to decode source image', '/thumb'))).toMatchObject({
      category: 'decode',
      retryable: false,
    })
  })

  it('formats concise media messages for user-facing overlays', () => {
    expect(mediaErrorSummary(browserDecodeMediaError())).toBe('Could not decode this image.')
    expect(mediaErrorSummary({
      category: 'remote_not_found',
      message: 'file not found',
      retryable: true,
    })).toBe('Remote source not found.')
  })
})

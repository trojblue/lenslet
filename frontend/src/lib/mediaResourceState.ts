import { FetchError } from './fetcher'

export type MediaResourceSource = 'direct' | 'blob' | 'proxy' | 'thumbnail' | 'hover'

export type MediaErrorCategory =
  | 'aborted'
  | 'local_not_found'
  | 'remote_not_found'
  | 'permission'
  | 'timeout'
  | 'decode'
  | 'upstream'
  | 'read'
  | 'network'
  | 'direct_display'
  | 'unknown'

export type MediaResourceError = {
  category: MediaErrorCategory
  message: string
  status?: number
  retryable: boolean
}

export type BlobMediaResourceState =
  | { status: 'idle' }
  | { status: 'loading'; requestId: number; source: MediaResourceSource }
  | { status: 'ready'; requestId: number; source: MediaResourceSource; url: string }
  | { status: 'error'; requestId: number; error: MediaResourceError; retry: () => void }
  | { status: 'unsupported'; reason: string }

export function browserDecodeMediaError(): MediaResourceError {
  return {
    category: 'decode',
    message: 'Browser could not decode this image.',
    retryable: false,
  }
}

export function isAbortMediaError(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false
  const candidate = error as { name?: unknown; message?: unknown }
  if (candidate.name === 'AbortError') return true
  const message = typeof candidate.message === 'string' ? candidate.message.toLowerCase() : ''
  return message.includes('abort') || message.includes('cancel')
}

function categoryForFetchError(error: FetchError): MediaErrorCategory {
  if (error.status === 403) return 'permission'
  if (error.status === 422) return 'decode'
  if (error.status === 504) return 'timeout'
  if (error.status === 502) return 'upstream'
  if (error.status === 404) {
    return error.message.toLowerCase().includes('remote') ? 'remote_not_found' : 'local_not_found'
  }
  if (error.status >= 500) return 'read'
  return 'unknown'
}

export function mediaErrorFromUnknown(
  error: unknown,
  fallbackMessage = 'Media failed to load.',
): MediaResourceError {
  if (isAbortMediaError(error)) {
    return {
      category: 'aborted',
      message: 'Media request was cancelled.',
      retryable: false,
    }
  }
  if (error instanceof FetchError) {
    const category = categoryForFetchError(error)
    return {
      category,
      status: error.status,
      message: error.message || fallbackMessage,
      retryable: category !== 'decode',
    }
  }
  if (error instanceof TypeError) {
    return {
      category: 'network',
      message: error.message || fallbackMessage,
      retryable: true,
    }
  }
  if (error instanceof Error) {
    return {
      category: 'unknown',
      message: error.message || fallbackMessage,
      retryable: true,
    }
  }
  return {
    category: 'unknown',
    message: fallbackMessage,
    retryable: true,
  }
}

export function mediaErrorSummary(error: MediaResourceError): string {
  if (error.category === 'permission') return 'Permission denied.'
  if (error.category === 'timeout') return 'Remote source timed out.'
  if (error.category === 'decode') return 'Could not decode this image.'
  if (error.category === 'local_not_found') return 'File not found.'
  if (error.category === 'remote_not_found') return 'Remote source not found.'
  if (error.category === 'upstream') return 'Remote source failed.'
  if (error.category === 'network') return 'Network request failed.'
  return error.message
}

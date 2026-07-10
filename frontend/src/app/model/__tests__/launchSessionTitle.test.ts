import { describe, expect, it } from 'vitest'
import { resolveLensletDocumentTitle } from '../launchSessionTitle'

describe('launch session document title', () => {
  it('uses the backend-provided title label when present', () => {
    expect(resolveLensletDocumentTitle({
      kind: 'hf_dataset',
      loaded_from_label: 'Hugging Face dataset',
      target_label: 'owner/repo',
      title_label: 'owner/repo',
    })).toBe('Lenslet · owner/repo')
  })

  it('falls back to Lenslet without session metadata', () => {
    expect(resolveLensletDocumentTitle(null)).toBe('Lenslet')
    expect(resolveLensletDocumentTitle({
      kind: 'remote_parquet',
      loaded_from_label: 'Remote Parquet',
      target_label: 'https://example.test/items.parquet',
      title_label: '   ',
    })).toBe('Lenslet')
  })
})

import { describe, expect, it } from 'vitest'
import {
  shouldAutoActivateMetadataCompare,
  shouldDisableMetadataCompare,
} from '../useInspectorUiState'

describe('inspector metadata compare activation guards', () => {
  it('disables metadata compare below two selections or when compare targets are unavailable', () => {
    expect(shouldDisableMetadataCompare(1, false)).toBe(true)
    expect(shouldDisableMetadataCompare(1, true)).toBe(true)
    expect(shouldDisableMetadataCompare(2, false)).toBe(true)
    expect(shouldDisableMetadataCompare(2, true)).toBe(false)
    expect(shouldDisableMetadataCompare(3, true)).toBe(false)
  })

  it('auto-activates metadata compare only when autoload is on and at least two are selected', () => {
    expect(shouldAutoActivateMetadataCompare(false, 1, false)).toBe(false)
    expect(shouldAutoActivateMetadataCompare(false, 2, true)).toBe(false)
    expect(shouldAutoActivateMetadataCompare(false, 3, true)).toBe(false)

    expect(shouldAutoActivateMetadataCompare(true, 1, true)).toBe(false)
    expect(shouldAutoActivateMetadataCompare(true, 2, false)).toBe(false)
    expect(shouldAutoActivateMetadataCompare(true, 2, true)).toBe(true)
    expect(shouldAutoActivateMetadataCompare(true, 3, true)).toBe(true)
  })
})

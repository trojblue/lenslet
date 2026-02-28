import { describe, expect, it } from 'vitest'
import { deriveAppModeFromHealth } from '../appMode'

describe('app mode boot contracts', () => {
  it('routes ranking mode when health reports ranking', () => {
    expect(deriveAppModeFromHealth({ ok: true, mode: 'ranking' })).toBe('ranking')
  })

  it('defaults to browse when health is missing or non-ranking', () => {
    expect(deriveAppModeFromHealth(null)).toBe('browse')
    expect(deriveAppModeFromHealth({ ok: true, mode: 'dataset' })).toBe('browse')
    expect(deriveAppModeFromHealth({ ok: true })).toBe('browse')
  })
})


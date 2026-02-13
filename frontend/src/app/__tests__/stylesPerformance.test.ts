import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

describe('styles performance guardrails', () => {
  it('keeps critical CSS free of external font imports', () => {
    const here = dirname(fileURLToPath(import.meta.url))
    const cssPath = resolve(here, '../../styles.css')
    const css = readFileSync(cssPath, 'utf-8')

    expect(css).not.toMatch(/fonts\.googleapis\.com/i)
  })
})

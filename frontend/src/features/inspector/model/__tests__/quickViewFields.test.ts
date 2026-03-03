import { describe, expect, it } from 'vitest'
import {
  buildQuickViewRows,
  parseQuickViewCustomPathsInput,
  parseQuickViewPath,
  parseStoredQuickViewCustomPaths,
  shouldShowQuickViewSection,
} from '../quickViewFields'

const SAMPLE_META = {
  quick_view_defaults: {
    prompt: 'a cat in rain',
    model: 'flux-dev',
    lora: 'cinematic.safetensors (0.7)',
  },
  quick_fields: {
    parameters: 'steps=20,cfg=7',
  },
  found_text_chunks: [
    {
      keyword: 'qfty_meta',
    },
  ],
}

describe('quick view field model', () => {
  it('accepts strict dot/[index] quick-view path syntax', () => {
    const parsed = parseQuickViewPath('found_text_chunks[0].keyword')
    expect(parsed).toEqual({
      ok: true,
      path: 'found_text_chunks[0].keyword',
      segments: ['found_text_chunks', 0, 'keyword'],
    })

    expect(parseQuickViewPath(' quick_fields.parameters ')).toEqual({
      ok: true,
      path: 'quick_fields.parameters',
      segments: ['quick_fields', 'parameters'],
    })
  })

  it('rejects unsupported path tokens and invalid array syntax', () => {
    const missingIdentifier = parseQuickViewPath('quick_fields..parameters')
    expect(missingIdentifier.ok).toBe(false)

    const invalidIndex = parseQuickViewPath('found_text_chunks[abc].keyword')
    expect(invalidIndex.ok).toBe(false)

    const unsupportedToken = parseQuickViewPath('quick_fields[0]/name')
    expect(unsupportedToken.ok).toBe(false)
  })

  it('parses custom quick-view path input and rejects invalid lines with line numbers', () => {
    const parsed = parseQuickViewCustomPathsInput(
      'quick_fields.parameters\nfound_text_chunks[0].keyword\nquick_fields.parameters',
    )
    expect(parsed).toEqual({
      paths: ['quick_fields.parameters', 'found_text_chunks[0].keyword'],
      error: null,
    })

    const invalid = parseQuickViewCustomPathsInput('quick_fields.parameters\ninvalid path')
    expect(invalid.paths).toEqual([])
    expect(invalid.error).toContain('Line 2:')
  })

  it('sanitizes persisted custom paths and marks stale payloads for rewrite', () => {
    const parsed = parseStoredQuickViewCustomPaths(
      JSON.stringify([' quick_fields.parameters ', 'quick_fields.parameters', 'invalid path']),
    )

    expect(parsed).toEqual({
      paths: ['quick_fields.parameters'],
      shouldRewrite: true,
    })

    const canonical = parseStoredQuickViewCustomPaths(
      JSON.stringify(['quick_fields.parameters', 'found_text_chunks[0].keyword']),
    )
    expect(canonical).toEqual({
      paths: ['quick_fields.parameters', 'found_text_chunks[0].keyword'],
      shouldRewrite: false,
    })
  })

  it('shows quick view only when single-select autoload is on and PNG defaults exist', () => {
    expect(
      shouldShowQuickViewSection({
        multi: false,
        autoloadMetadata: true,
        meta: SAMPLE_META,
      }),
    ).toBe(true)

    expect(
      shouldShowQuickViewSection({
        multi: true,
        autoloadMetadata: true,
        meta: SAMPLE_META,
      }),
    ).toBe(false)

    expect(
      shouldShowQuickViewSection({
        multi: false,
        autoloadMetadata: false,
        meta: SAMPLE_META,
      }),
    ).toBe(false)

    expect(
      shouldShowQuickViewSection({
        multi: false,
        autoloadMetadata: true,
        meta: { quick_fields: { parameters: 'steps=20' } },
      }),
    ).toBe(false)
  })

  it('builds default and custom quick-view rows from metadata payload', () => {
    const rows = buildQuickViewRows(SAMPLE_META, ['quick_fields.parameters', 'found_text_chunks[0].keyword'])

    expect(rows.slice(0, 3)).toEqual([
      {
        id: 'default:prompt',
        label: 'Prompt',
        value: 'a cat in rain',
        sourcePath: 'quick_view_defaults.prompt',
      },
      {
        id: 'default:model',
        label: 'Model',
        value: 'flux-dev',
        sourcePath: 'quick_view_defaults.model',
      },
      {
        id: 'default:lora',
        label: 'LoRA',
        value: 'cinematic.safetensors (0.7)',
        sourcePath: 'quick_view_defaults.lora',
      },
    ])

    expect(rows[3]).toEqual({
      id: 'custom:quick_fields.parameters',
      label: 'quick_fields.parameters',
      value: 'steps=20,cfg=7',
      sourcePath: 'quick_fields.parameters',
    })
    expect(rows[4]).toEqual({
      id: 'custom:found_text_chunks[0].keyword',
      label: 'found_text_chunks[0].keyword',
      value: 'qfty_meta',
      sourcePath: 'found_text_chunks[0].keyword',
    })
  })
})

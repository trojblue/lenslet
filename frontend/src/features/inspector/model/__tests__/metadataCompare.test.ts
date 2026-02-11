import { describe, expect, it } from 'vitest'
import {
  buildCompareMetadataDiffFromNormalized,
  buildCompareMetadataDiff,
  buildDisplayMetadataFromNormalized,
  buildDisplayMetadata,
  formatCopyValue,
  formatPathLabel,
  getValueAtPath,
  hasPilInfoMetadata,
  normalizeMetadataRecord,
  normalizeMetadata,
  renderJsonValue,
} from '../metadataCompare'

describe('inspector metadata model utilities', () => {
  it('normalizes JSON-like metadata strings recursively', () => {
    const value = normalizeMetadata({
      prompt: '{"steps": 30, "cfg": 6.5}',
      tags: '["a","b"]',
      list: ['{"x":1}', 'not json'],
    }) as Record<string, unknown>

    expect(value.prompt).toEqual({ steps: 30, cfg: 6.5 })
    expect(value.tags).toEqual(['a', 'b'])
    expect(value.list).toEqual([{ x: 1 }, 'not json'])
  })

  it('builds display metadata and masks pil_info when hidden', () => {
    const meta = {
      author: 'lenslet',
      pil_info: { mode: 'RGB' },
    }
    expect(buildDisplayMetadata(meta, true)).toEqual(meta)
    expect(buildDisplayMetadata(meta, false)).toEqual({
      author: 'lenslet',
      pil_info: 'Hidden (toggle Show PIL info to expand)',
    })
  })

  it('reuses normalized metadata for display and compare diff helpers', () => {
    const metaA = {
      prompt: '{"steps": 24, "cfg": 7}',
      pil_info: { mode: 'RGB' },
      nested: { score: 1, tags: ['a', 'b'] },
    }
    const metaB = {
      prompt: '{"steps": 30, "cfg": 6}',
      pil_info: { mode: 'RGBA' },
      nested: { score: 2, tags: ['a', 'b'] },
    }
    const opts = {
      includePilInfo: false,
      limit: 50,
      maxDepth: 8,
      maxArray: 80,
    }

    const normalizedA = normalizeMetadataRecord(metaA)
    const normalizedB = normalizeMetadataRecord(metaB)
    expect(buildDisplayMetadata(metaA, false)).toEqual(
      buildDisplayMetadataFromNormalized(normalizedA, false),
    )
    expect(buildDisplayMetadata(metaA, true)).toEqual(
      buildDisplayMetadataFromNormalized(normalizedA, true),
    )
    expect(buildCompareMetadataDiff(metaA, metaB, opts)).toEqual(
      buildCompareMetadataDiffFromNormalized(normalizedA, normalizedB, opts),
    )
  })

  it('renders html-safe JSON with clickable path markers', () => {
    const html = renderJsonValue(
      {
        nested: {
          title: '<unsafe>',
        },
      },
      [],
      0,
    )

    expect(html).toContain('data-json-path=\'[&quot;nested&quot;,&quot;title&quot;]\'')
    expect(html).toContain('&lt;unsafe&gt;')
  })

  it('formats and resolves metadata paths', () => {
    const root = {
      safe: [{ value: 2 }],
      'needs space': {
        child: true,
      },
    }
    expect(formatPathLabel(['safe', 0, 'value'])).toBe('safe[0].value')
    expect(formatPathLabel(['needs space', 'child'])).toBe('["needs space"].child')
    expect(formatPathLabel([])).toBe('(root)')
    expect(getValueAtPath(root, ['safe', 0, 'value'])).toBe(2)
    expect(getValueAtPath(root, ['missing'])).toBeUndefined()
  })

  it('formats copy text for edge values', () => {
    expect(formatCopyValue(undefined)).toBe('undefined')
    expect(formatCopyValue(null)).toBe('null')
    expect(formatCopyValue('raw')).toBe('raw')
    expect(formatCopyValue({ a: 1 })).toContain('"a": 1')
  })

  it('detects PIL info presence for top-level metadata objects', () => {
    expect(hasPilInfoMetadata({ pil_info: {} })).toBe(true)
    expect(hasPilInfoMetadata({ other: 1 })).toBe(false)
    expect(hasPilInfoMetadata(null)).toBe(false)
  })

  it('builds compare diffs and excludes pil_info when disabled', () => {
    const diff = buildCompareMetadataDiff(
      {
        score: 1,
        onlyA: 'left',
        same: 'value',
        pil_info: { mode: 'RGB' },
      },
      {
        score: 2,
        onlyB: 'right',
        same: 'value',
        pil_info: { mode: 'RGBA' },
      },
      {
        includePilInfo: false,
        limit: 20,
        maxDepth: 8,
        maxArray: 80,
      },
    )

    expect(diff).not.toBeNull()
    expect(diff?.different).toBe(1)
    expect(diff?.onlyA).toBe(1)
    expect(diff?.onlyB).toBe(1)
    expect(diff?.entries.map((entry) => entry.key)).toEqual(['onlyA', 'onlyB', 'score'])
  })

  it('includes pil_info keys when compare diff opts enable them', () => {
    const diff = buildCompareMetadataDiff(
      {
        a: 1,
        b: 2,
        pil_info: { mode: 'RGB' },
      },
      {
        a: 10,
        b: 20,
        pil_info: { mode: 'RGBA' },
      },
      {
        includePilInfo: true,
        limit: 20,
        maxDepth: 8,
        maxArray: 80,
      },
    )

    expect(diff).not.toBeNull()
    expect(diff?.different).toBe(3)
    expect(diff?.entries).toHaveLength(3)
    expect(diff?.entries.some((entry) => entry.key.startsWith('pil_info'))).toBe(true)
  })

  it('truncates compare diffs beyond the configured limit', () => {
    const diff = buildCompareMetadataDiff(
      {
        a: 1,
        b: 2,
        c: 3,
      },
      {
        a: 10,
        b: 20,
        c: 30,
      },
      {
        includePilInfo: false,
        limit: 2,
        maxDepth: 8,
        maxArray: 80,
      },
    )

    expect(diff).not.toBeNull()
    expect(diff?.different).toBe(3)
    expect(diff?.entries).toHaveLength(2)
    expect(diff?.truncatedCount).toBe(1)
  })
})

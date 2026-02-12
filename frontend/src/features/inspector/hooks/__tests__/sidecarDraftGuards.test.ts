import { describe, expect, it } from 'vitest'
import {
  buildSidecarDraft,
  hasSemanticNotesChange,
  hasSemanticTagsChange,
  parseSidecarTags,
} from '../sidecarDraftGuards'

describe('inspector sidecar draft guards', () => {
  it('builds local drafts from sidecar values with safe empty defaults', () => {
    expect(buildSidecarDraft(undefined)).toEqual({ notes: '', tags: '' })
    expect(buildSidecarDraft({ notes: 'hello', tags: ['a', 'b'] })).toEqual({
      notes: 'hello',
      tags: 'a, b',
    })
  })

  it('parses comma-separated tags into trimmed non-empty values', () => {
    expect(parseSidecarTags('tag1, tag2 ,, , tag3')).toEqual(['tag1', 'tag2', 'tag3'])
  })

  it('treats notes as changed only when text differs exactly', () => {
    expect(hasSemanticNotesChange('notes', 'notes')).toBe(false)
    expect(hasSemanticNotesChange('notes', 'notes!')).toBe(true)
  })

  it('ignores whitespace-only formatting differences in tag text', () => {
    expect(hasSemanticTagsChange('a,b,c', 'a, b, c')).toBe(false)
    expect(hasSemanticTagsChange('a, b, c', 'a, b, c')).toBe(false)
  })

  it('detects real semantic tag changes', () => {
    expect(hasSemanticTagsChange('a, b', 'a, b, c')).toBe(true)
    expect(hasSemanticTagsChange('a, b', 'b, a')).toBe(true)
    expect(hasSemanticTagsChange('a, b, b', 'a, b')).toBe(true)
  })
})

import { describe, expect, it } from 'vitest'
import {
  buildSidecarDraft,
  buildDraftAnnotationEdit,
  hasSemanticNotesChange,
  hasSemanticTagsChange,
  mergeAuthoritativeSidecarDraft,
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

  it('accepts authoritative clean fields while retaining dirty drafts', () => {
    expect(
      mergeAuthoritativeSidecarDraft(
        { notes: 'local notes', tags: 'local-tag' },
        { notes: 'remote notes', tags: 'remote-tag' },
        { notes: true, tags: false },
      ),
    ).toEqual({ notes: 'local notes', tags: 'remote-tag' })
    expect(
      mergeAuthoritativeSidecarDraft(
        { notes: 'local notes', tags: 'local-tag' },
        { notes: 'remote notes', tags: 'remote-tag' },
        { notes: false, tags: true },
      ),
    ).toEqual({ notes: 'remote notes', tags: 'local-tag' })
  })

  it('describes single-image edits relative to what the user started from', () => {
    expect(
      buildDraftAnnotationEdit(
        { notes: 'draft A', tags: 'a, c' },
        { notes: 'settled A', tags: 'a, b' },
        { notes: true, tags: true },
        { multi: false },
      ),
    ).toEqual({ notes: { from: 'settled A', to: 'draft A' }, addTags: ['c'], removeTags: ['b'] })
    expect(
      buildDraftAnnotationEdit(
        { notes: 'settled A', tags: 'b, a' },
        { notes: 'settled A', tags: 'a, b' },
        { notes: true, tags: true },
        { multi: false },
      ),
    ).toBeNull()
  })

  it('only adds tags across a multi-selection and never removes per-image tags', () => {
    expect(
      buildDraftAnnotationEdit(
        { notes: '', tags: 'reviewed' },
        { notes: '', tags: '' },
        { notes: false, tags: true },
        { multi: true },
      ),
    ).toEqual({ addTags: ['reviewed'] })
  })

  it('ignores fields the user did not touch', () => {
    expect(
      buildDraftAnnotationEdit(
        { notes: 'remote', tags: 'x' },
        { notes: 'older', tags: '' },
        { notes: false, tags: false },
        { multi: false },
      ),
    ).toBeNull()
  })
})

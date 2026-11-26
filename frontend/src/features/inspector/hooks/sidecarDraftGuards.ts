import { mergeAnnotationEdits, tagEditBetween, type AnnotationEdit } from '../../../api/items'
import type { Sidecar } from '../../../lib/types'

export type SidecarDraft = {
  notes: string
  tags: string
}

export type SidecarDraftDirtyFields = {
  notes: boolean
  tags: boolean
}

export function buildSidecarDraft(sidecar: Pick<Sidecar, 'notes' | 'tags'> | undefined): SidecarDraft {
  return {
    notes: sidecar?.notes ?? '',
    tags: (sidecar?.tags ?? []).join(', '),
  }
}

export function parseSidecarTags(value: string): string[] {
  return value
    .split(',')
    .map((tag) => tag.trim())
    .filter(Boolean)
}

export function mergeAuthoritativeSidecarDraft(
  current: SidecarDraft,
  authoritative: SidecarDraft,
  dirty: SidecarDraftDirtyFields,
): SidecarDraft {
  return {
    notes: dirty.notes ? current.notes : authoritative.notes,
    tags: dirty.tags ? current.tags : authoritative.tags,
  }
}

function tagsEqual(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false
  for (let i = 0; i < a.length; i += 1) {
    if (a[i] !== b[i]) return false
  }
  return true
}

export function hasSemanticNotesChange(currentNotes: string, baselineNotes: string): boolean {
  return currentNotes !== baselineNotes
}

export function hasSemanticTagsChange(currentTags: string, baselineTags: string): boolean {
  return !tagsEqual(parseSidecarTags(currentTags), parseSidecarTags(baselineTags))
}

/**
 * Turn the dirty fields of a draft into a queue edit relative to what the user
 * started from. Multi-select drafts apply to images with different values, so
 * they only ever add: tags are added and notes are appended to each image.
 */
export function buildDraftAnnotationEdit(
  current: SidecarDraft,
  baseline: SidecarDraft,
  dirty: SidecarDraftDirtyFields,
  { multi }: { multi: boolean },
): AnnotationEdit | null {
  let edit: AnnotationEdit = {}
  if (dirty.notes && hasSemanticNotesChange(current.notes, baseline.notes)) {
    if (!multi) edit.notes = { from: baseline.notes, to: current.notes }
    else if (current.notes.trim()) edit.appendNotes = current.notes.trim()
  }
  if (dirty.tags && hasSemanticTagsChange(current.tags, baseline.tags)) {
    const tags = tagEditBetween(multi ? [] : parseSidecarTags(baseline.tags), parseSidecarTags(current.tags))
    edit = mergeAnnotationEdits(edit, tags)
  }
  return edit.notes || edit.appendNotes || edit.addTags?.length || edit.removeTags?.length ? edit : null
}

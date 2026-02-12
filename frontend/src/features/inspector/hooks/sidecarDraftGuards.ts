import type { Sidecar } from '../../../lib/types'

export type SidecarDraft = {
  notes: string
  tags: string
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

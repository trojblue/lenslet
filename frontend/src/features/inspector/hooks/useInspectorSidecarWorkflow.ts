import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { QueryClient } from '@tanstack/react-query'
import {
  clearConflict,
  enqueueAnnotationEdit,
  setSidecarQueryDataForPath,
  updateConflictMine,
} from '../../../api/items'
import type { ConflictEntry } from '../../../api/items'
import type { Sidecar } from '../../../lib/types'
import {
  buildDraftAnnotationEdit,
  buildSidecarDraft,
  mergeAuthoritativeSidecarDraft,
  type SidecarDraft,
  type SidecarDraftDirtyFields,
} from './sidecarDraftGuards'

type UseInspectorSidecarWorkflowParams = {
  path: string | null
  selectedPaths: string[]
  resetKey: string
  multi: boolean
  sidecar: Sidecar | undefined
  conflict: ConflictEntry | null
  queryClient: QueryClient
  onLocalTypingChange?: (active: boolean) => void
}

type UseInspectorSidecarWorkflowResult = {
  tags: string
  notes: string
  notesConflict: boolean
  applyConflict: () => void
  keepTheirs: () => void
  handleNotesChange: (value: string) => void
  handleNotesBlur: () => void
  handleTagsChange: (value: string) => void
  handleTagsBlur: () => void
}

/** Who a draft belongs to: edits are always saved to the images they were typed for. */
type DraftOwner = {
  identity: string | null
  path: string | null
  targets: string[]
  multi: boolean
}

type DraftState = {
  values: SidecarDraft
  /** What the user started editing from; it only follows the server for clean fields. */
  baseline: SidecarDraft
  dirty: SidecarDraftDirtyFields
}

const CLEAN: SidecarDraftDirtyFields = { notes: false, tags: false }
const ALL_FIELDS: SidecarDraftDirtyFields = { notes: true, tags: true }
const TAGS_ONLY: SidecarDraftDirtyFields = { notes: false, tags: true }

function draftOwner(path: string | null, selectedPaths: string[], multi: boolean, resetKey: string): DraftOwner {
  return {
    identity: path ? JSON.stringify([resetKey, path, selectedPaths]) : null,
    path,
    targets: multi ? [...selectedPaths] : path ? [path] : [],
    multi,
  }
}

export function useInspectorSidecarWorkflow({
  path,
  selectedPaths,
  resetKey,
  multi,
  sidecar,
  conflict,
  queryClient,
  onLocalTypingChange,
}: UseInspectorSidecarWorkflowParams): UseInspectorSidecarWorkflowResult {
  const owner = useMemo(
    () => draftOwner(path, selectedPaths, multi, resetKey),
    [multi, path, resetKey, selectedPaths],
  )
  const authoritativeDraft = useMemo(
    () => buildSidecarDraft(path && !multi ? sidecar : undefined),
    [multi, path, sidecar],
  )
  const [values, setValues] = useState<SidecarDraft>(authoritativeDraft)
  const [valuesOwner, setValuesOwner] = useState<string | null>(owner.identity)
  const ownerRef = useRef(owner)
  const draftRef = useRef<DraftState>({ values: authoritativeDraft, baseline: authoritativeDraft, dirty: CLEAN })
  const localTypingActiveRef = useRef(false)
  // An unresolved notes conflict keeps the user's text out of automatic saves;
  // it stays in the conflict entry (and the status bar) until resolved.
  const conflictOpen = !!conflict && !multi
  const conflictOpenRef = useRef(conflictOpen)
  conflictOpenRef.current = conflictOpen
  const shownConflictRef = useRef<string | null>(null)

  const notifyLocalTyping = useCallback((active: boolean) => {
    if (localTypingActiveRef.current === active) return
    localTypingActiveRef.current = active
    onLocalTypingChange?.(active)
  }, [onLocalTypingChange])

  const writeDraft = useCallback((next: DraftState) => {
    draftRef.current = next
    setValues(next.values)
  }, [])

  // Save what the user typed to the images it was typed for, then mark those fields clean.
  const flushDraft = useCallback((fields?: SidecarDraftDirtyFields) => {
    fields ??= conflictOpenRef.current ? TAGS_ONLY : ALL_FIELDS
    const draft = draftRef.current
    const target = ownerRef.current
    const flushing = { notes: draft.dirty.notes && fields.notes, tags: draft.dirty.tags && fields.tags }
    const edit = buildDraftAnnotationEdit(draft.values, draft.baseline, flushing, { multi: target.multi })
    if (edit) {
      for (const targetPath of target.targets) enqueueAnnotationEdit(targetPath, edit)
    }
    const dirty = { notes: draft.dirty.notes && !flushing.notes, tags: draft.dirty.tags && !flushing.tags }
    if (target.multi) {
      // "Add to all" inputs empty once added, so typing again never adds twice.
      const values = {
        notes: flushing.notes ? '' : draft.values.notes,
        tags: flushing.tags ? '' : draft.values.tags,
      }
      draftRef.current = { values, baseline: draft.baseline, dirty }
      if (values.notes !== draft.values.notes || values.tags !== draft.values.tags) setValues(values)
    } else {
      draftRef.current = {
        values: draft.values,
        baseline: {
          notes: flushing.notes ? draft.values.notes : draft.baseline.notes,
          tags: flushing.tags ? draft.values.tags : draft.baseline.tags,
        },
        dirty,
      }
    }
    if (!dirty.notes && !dirty.tags) notifyLocalTyping(false)
  }, [notifyLocalTyping])

  // Any new owner (selection, folder, source, workspace) saves the previous draft first.
  useEffect(() => {
    if (ownerRef.current.identity === owner.identity) return
    flushDraft()
    ownerRef.current = owner
    shownConflictRef.current = null
    setValuesOwner(owner.identity)
    writeDraft({ values: authoritativeDraft, baseline: authoritativeDraft, dirty: CLEAN })
  }, [authoritativeDraft, flushDraft, owner, writeDraft])

  // Server truth moved: adopt it only for fields the user is not editing.
  useEffect(() => {
    if (ownerRef.current.identity !== owner.identity) return
    const draft = draftRef.current
    const baseline = {
      notes: draft.dirty.notes ? draft.baseline.notes : authoritativeDraft.notes,
      tags: draft.dirty.tags ? draft.baseline.tags : authoritativeDraft.tags,
    }
    const merged = mergeAuthoritativeSidecarDraft(draft.values, authoritativeDraft, draft.dirty)
    const unchanged = merged.notes === draft.values.notes && merged.tags === draft.values.tags
      && baseline.notes === draft.baseline.notes && baseline.tags === draft.baseline.tags
    if (!unchanged) writeDraft({ values: merged, baseline, dirty: draft.dirty })
  }, [authoritativeDraft, owner.identity, writeDraft])

  // A notes conflict puts the user's text back in the field, unsaved, until resolved.
  useEffect(() => {
    if (!conflict || multi || conflict.path !== ownerRef.current.path) return
    const shown = `${conflict.path}\u0000${conflict.receivedAt}`
    if (shownConflictRef.current === shown) return
    shownConflictRef.current = shown
    const draft = draftRef.current
    writeDraft({
      values: { ...draft.values, notes: conflict.mine },
      baseline: { ...draft.baseline, notes: conflict.current.notes ?? '' },
      dirty: { ...draft.dirty, notes: true },
    })
    notifyLocalTyping(true)
  }, [conflict, multi, notifyLocalTyping, writeDraft])

  // Unmounting (lazy-surface reset, layout swap) must not drop a draft either.
  useEffect(() => () => flushDraft(), [flushDraft])

  const handleBlur = useCallback(() => flushDraft(), [flushDraft])

  const handleNotesChange = useCallback((value: string) => {
    const draft = draftRef.current
    writeDraft({ ...draft, values: { ...draft.values, notes: value }, dirty: { ...draft.dirty, notes: true } })
    // Conflicted text is never auto-saved; the conflict keeps it across navigation.
    const target = ownerRef.current
    if (conflictOpenRef.current && target.path && !target.multi) updateConflictMine(target.path, value)
    notifyLocalTyping(true)
  }, [notifyLocalTyping, writeDraft])

  const handleTagsChange = useCallback((value: string) => {
    const draft = draftRef.current
    writeDraft({ ...draft, values: { ...draft.values, tags: value }, dirty: { ...draft.dirty, tags: true } })
    notifyLocalTyping(true)
  }, [notifyLocalTyping, writeDraft])

  // Keep mine: overwrite exactly the server text the user has now been shown.
  const applyConflict = useCallback(() => {
    if (!conflict || !path) return
    const draft = draftRef.current
    draftRef.current = {
      ...draft,
      baseline: { ...draft.baseline, notes: conflict.current.notes ?? '' },
      dirty: { ...draft.dirty, notes: true },
    }
    clearConflict(path)
    flushDraft(ALL_FIELDS)
  }, [conflict, flushDraft, path])

  const keepTheirs = useCallback(() => {
    if (!conflict || !path) return
    const theirs = conflict.current.notes ?? ''
    const draft = draftRef.current
    writeDraft({
      values: { ...draft.values, notes: theirs },
      baseline: { ...draft.baseline, notes: theirs },
      dirty: { ...draft.dirty, notes: false },
    })
    if (!draftRef.current.dirty.tags) notifyLocalTyping(false)
    setSidecarQueryDataForPath(queryClient, path, conflict.current)
    clearConflict(path)
  }, [conflict, notifyLocalTyping, path, queryClient, writeDraft])

  const projected = valuesOwner === owner.identity ? values : authoritativeDraft

  return {
    tags: projected.tags,
    notes: projected.notes,
    notesConflict: conflictOpen,
    applyConflict,
    keepTheirs,
    handleNotesChange,
    handleNotesBlur: handleBlur,
    handleTagsChange,
    handleTagsBlur: handleBlur,
  }
}

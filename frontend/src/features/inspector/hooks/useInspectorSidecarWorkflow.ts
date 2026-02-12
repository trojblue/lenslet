import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { QueryClient } from '@tanstack/react-query'
import { bulkUpdateSidecars, clearConflict, sidecarQueryKey } from '../../../shared/api/items'
import type { ConflictEntry } from '../../../shared/api/items'
import type { Sidecar, StarRating } from '../../../lib/types'
import {
  buildSidecarDraft,
  hasSemanticNotesChange,
  hasSemanticTagsChange,
  parseSidecarTags,
  type SidecarDraft,
} from './sidecarDraftGuards'

type SidecarPatch = {
  notes?: string
  tags?: string[]
  star?: StarRating | null
}

type UseInspectorSidecarWorkflowParams = {
  path: string | null
  selectedPaths: string[]
  multi: boolean
  sidecar: Sidecar | undefined
  conflict: ConflictEntry | null
  star: StarRating | null
  queryClient: QueryClient
  mutateSidecar: (patch: SidecarPatch, baseVersion: number) => void
  onStarChanged?: (paths: string[], value: StarRating) => void
  onLocalTypingChange?: (active: boolean) => void
}

type UseInspectorSidecarWorkflowResult = {
  tags: string
  notes: string
  conflictFields: { tags: boolean; notes: boolean; star: boolean }
  commitSidecar: (patch: SidecarPatch) => void
  applyConflict: () => void
  keepTheirs: () => void
  handleNotesChange: (value: string) => void
  handleNotesBlur: () => void
  handleTagsChange: (value: string) => void
  handleTagsBlur: () => void
}

export function useInspectorSidecarWorkflow({
  path,
  selectedPaths,
  multi,
  sidecar,
  conflict,
  star,
  queryClient,
  mutateSidecar,
  onStarChanged,
  onLocalTypingChange,
}: UseInspectorSidecarWorkflowParams): UseInspectorSidecarWorkflowResult {
  const [tags, setTags] = useState('')
  const [notes, setNotes] = useState('')
  const localTypingActiveRef = useRef(false)
  const notesDirtyRef = useRef(false)
  const tagsDirtyRef = useRef(false)
  const baselineDraftRef = useRef<SidecarDraft>(buildSidecarDraft(undefined))

  const notifyLocalTyping = useCallback(
    (active: boolean) => {
      if (localTypingActiveRef.current === active) return
      localTypingActiveRef.current = active
      onLocalTypingChange?.(active)
    },
    [onLocalTypingChange],
  )

  const resetDraftState = useCallback(
    (nextDraft: SidecarDraft) => {
      baselineDraftRef.current = nextDraft
      notesDirtyRef.current = false
      tagsDirtyRef.current = false
      setTags(nextDraft.tags)
      setNotes(nextDraft.notes)
      notifyLocalTyping(false)
    },
    [notifyLocalTyping],
  )

  useEffect(() => {
    if (!path) {
      resetDraftState(buildSidecarDraft(undefined))
      return
    }
    resetDraftState(buildSidecarDraft(sidecar))
  }, [path, resetDraftState, sidecar?.updated_at, sidecar?.version])

  useEffect(
    () => () => {
      notifyLocalTyping(false)
    },
    [notifyLocalTyping],
  )

  const commitSidecar = useCallback(
    (patch: SidecarPatch) => {
      if (multi && selectedPaths.length) {
        bulkUpdateSidecars(selectedPaths, patch)
        return
      }
      if (!path) return
      mutateSidecar(patch, sidecar?.version ?? 1)
    },
    [multi, mutateSidecar, path, selectedPaths, sidecar?.version],
  )

  const conflictFields = useMemo(
    () => ({
      tags: !!conflict?.pending.set_tags,
      notes: conflict?.pending.set_notes !== undefined,
      star: conflict?.pending.set_star !== undefined,
    }),
    [conflict],
  )

  const handleNotesChange = useCallback(
    (value: string) => {
      setNotes(value)
      notesDirtyRef.current = true
      notifyLocalTyping(true)
    },
    [notifyLocalTyping],
  )

  const handleNotesBlur = useCallback(() => {
    const wasDirty = notesDirtyRef.current
    notesDirtyRef.current = false
    if (wasDirty && hasSemanticNotesChange(notes, baselineDraftRef.current.notes)) {
      commitSidecar({ notes })
      baselineDraftRef.current = { ...baselineDraftRef.current, notes }
    }
    notifyLocalTyping(false)
  }, [commitSidecar, notes, notifyLocalTyping])

  const handleTagsChange = useCallback(
    (value: string) => {
      setTags(value)
      tagsDirtyRef.current = true
      notifyLocalTyping(true)
    },
    [notifyLocalTyping],
  )

  const handleTagsBlur = useCallback(() => {
    const wasDirty = tagsDirtyRef.current
    tagsDirtyRef.current = false
    if (wasDirty && hasSemanticTagsChange(tags, baselineDraftRef.current.tags)) {
      commitSidecar({ tags: parseSidecarTags(tags) })
      baselineDraftRef.current = { ...baselineDraftRef.current, tags }
    }
    notifyLocalTyping(false)
  }, [commitSidecar, notifyLocalTyping, tags])

  const applyConflict = useCallback(() => {
    if (!conflict || !path) return
    const patch: SidecarPatch = {}
    if (conflict.pending.set_tags !== undefined) {
      patch.tags = parseSidecarTags(tags)
    }
    if (conflict.pending.set_notes !== undefined) {
      patch.notes = notes
    }
    if (conflict.pending.set_star !== undefined) {
      patch.star = star ?? null
    }
    mutateSidecar(patch, conflict.current.version ?? 1)
  }, [conflict, mutateSidecar, notes, path, star, tags])

  const keepTheirs = useCallback(() => {
    if (!conflict || !path) return
    const current = conflict.current
    const currentDraft = buildSidecarDraft(current)
    baselineDraftRef.current = currentDraft
    notesDirtyRef.current = false
    tagsDirtyRef.current = false
    setTags(currentDraft.tags)
    setNotes(currentDraft.notes)
    notifyLocalTyping(false)
    queryClient.setQueryData(sidecarQueryKey(path), current)
    clearConflict(path)
    onStarChanged?.([path], current.star ?? null)
  }, [conflict, notifyLocalTyping, onStarChanged, path, queryClient])

  return {
    tags,
    notes,
    conflictFields,
    commitSidecar,
    applyConflict,
    keepTheirs,
    handleNotesChange,
    handleNotesBlur,
    handleTagsChange,
    handleTagsBlur,
  }
}

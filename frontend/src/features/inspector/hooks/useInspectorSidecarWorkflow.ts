import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { QueryClient } from '@tanstack/react-query'
import { bulkUpdateSidecars, clearConflict, sidecarQueryKey } from '../../../shared/api/items'
import type { ConflictEntry } from '../../../shared/api/items'
import type { Sidecar, StarRating } from '../../../lib/types'

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

function parseTags(value: string): string[] {
  return value
    .split(',')
    .map((tag) => tag.trim())
    .filter(Boolean)
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

  const notifyLocalTyping = useCallback(
    (active: boolean) => {
      if (localTypingActiveRef.current === active) return
      localTypingActiveRef.current = active
      onLocalTypingChange?.(active)
    },
    [onLocalTypingChange],
  )

  useEffect(() => {
    if (sidecar) {
      setTags((sidecar.tags || []).join(', '))
      setNotes(sidecar.notes || '')
    }
    notifyLocalTyping(false)
  }, [sidecar?.updated_at, notifyLocalTyping, path])

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
      notifyLocalTyping(true)
    },
    [notifyLocalTyping],
  )

  const handleNotesBlur = useCallback(() => {
    commitSidecar({ notes })
    notifyLocalTyping(false)
  }, [commitSidecar, notes, notifyLocalTyping])

  const handleTagsChange = useCallback(
    (value: string) => {
      setTags(value)
      notifyLocalTyping(true)
    },
    [notifyLocalTyping],
  )

  const handleTagsBlur = useCallback(() => {
    commitSidecar({ tags: parseTags(tags) })
    notifyLocalTyping(false)
  }, [commitSidecar, notifyLocalTyping, tags])

  const applyConflict = useCallback(() => {
    if (!conflict || !path) return
    const patch: SidecarPatch = {}
    if (conflict.pending.set_tags !== undefined) {
      patch.tags = parseTags(tags)
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
    setTags((current.tags || []).join(', '))
    setNotes(current.notes || '')
    queryClient.setQueryData(sidecarQueryKey(path), current)
    clearConflict(path)
    onStarChanged?.([path], current.star ?? null)
  }, [conflict, onStarChanged, path, queryClient])

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

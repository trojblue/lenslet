import { useCallback, useEffect, useState } from 'react'
import type { ChangeEvent, Dispatch, RefObject, SetStateAction } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { api } from '../../shared/api/client'
import type { ContextMenuState, FolderIndex } from '../../lib/types'
import { FetchError } from '../../lib/fetcher'
import { getPathName, joinPath, sanitizePath } from '../routing/hash'

const MOVE_FOLDER_SCAN_LIMIT = 600

export type MoveDialogState = {
  paths: string[]
}

type UseAppActionsParams = {
  appRef: RefObject<HTMLDivElement | null>
  uploadInputRef: RefObject<HTMLInputElement | null>
  current: string
  currentDirCount: number
  selectedPaths: string[]
  setSelectedPaths: Dispatch<SetStateAction<string[]>>
  refetch: () => Promise<unknown>
  invalidateDerivedCounts: () => void
}

type UseAppActionsResult = {
  uploading: boolean
  actionError: string | null
  isDraggingOver: boolean
  moveDialog: MoveDialogState | null
  moveFolders: string[]
  moveFoldersLoading: boolean
  ctx: ContextMenuState | null
  setCtx: Dispatch<SetStateAction<ContextMenuState | null>>
  closeMoveDialog: () => void
  openUploadPicker: () => void
  handleUploadInputChange: (event: ChangeEvent<HTMLInputElement>) => Promise<void>
  openGridActions: (targetPath: string, anchor: { x: number; y: number }) => void
  openFolderActions: (path: string, anchor: { x: number; y: number }) => void
  openMoveDialogForPaths: (paths: string[]) => void
  moveSelectedToFolder: (paths: string[], destination: string) => Promise<boolean>
}

function isReadOnlyError(error: unknown): boolean {
  if (!(error instanceof FetchError)) return false
  if (error.status === 403 || error.status === 405) return true
  const message = String(error.message || '').toLowerCase()
  return message.includes('read-only') || message.includes('no-write') || message.includes('write')
}

function formatMutationError(error: unknown, fallback: string): string {
  if (isReadOnlyError(error)) {
    return 'This workspace is read-only. Upload and move actions are disabled.'
  }
  if (error instanceof FetchError) return error.message
  if (error instanceof Error && error.message) return error.message
  return fallback
}

function dedupePaths(paths: string[]): string[] {
  return Array.from(new Set(paths.filter(Boolean)))
}

function summarizeFailures(label: string, failures: string[]): string {
  if (!failures.length) return ''
  if (failures.length === 1) return failures[0]
  return `${label} failed for ${failures.length} item(s). ${failures[0]}`
}

async function collectMoveFolders(): Promise<string[]> {
  const queue: string[] = ['/']
  const visited = new Set<string>()
  const found = new Set<string>(['/'])

  while (queue.length > 0 && visited.size < MOVE_FOLDER_SCAN_LIMIT) {
    const path = queue.shift() ?? '/'
    const safePath = sanitizePath(path)
    if (visited.has(safePath)) continue
    visited.add(safePath)
    let folder: FolderIndex | null = null
    try {
      folder = await api.getFolder(safePath)
    } catch {
      folder = null
    }
    if (!folder) continue
    for (const dir of folder.dirs ?? []) {
      const child = sanitizePath(joinPath(safePath, dir.name))
      if (found.has(child)) continue
      found.add(child)
      queue.push(child)
    }
  }

  return Array.from(found).sort((a, b) => {
    if (a === '/') return -1
    if (b === '/') return 1
    return a.localeCompare(b)
  })
}

export function useAppActions({
  appRef,
  uploadInputRef,
  current,
  currentDirCount,
  selectedPaths,
  setSelectedPaths,
  refetch,
  invalidateDerivedCounts,
}: UseAppActionsParams): UseAppActionsResult {
  const queryClient = useQueryClient()

  const [uploading, setUploading] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [isDraggingOver, setDraggingOver] = useState(false)
  const [moveDialog, setMoveDialog] = useState<MoveDialogState | null>(null)
  const [moveFolders, setMoveFolders] = useState<string[]>(['/'])
  const [moveFoldersLoading, setMoveFoldersLoading] = useState(false)
  const [ctx, setCtx] = useState<ContextMenuState | null>(null)

  useEffect(() => {
    setActionError(null)
  }, [current])

  const resolveGridActionPaths = useCallback((targetPath: string): string[] => {
    const currentSelection = dedupePaths(selectedPaths)
    if (currentSelection.includes(targetPath)) return currentSelection
    return [targetPath]
  }, [selectedPaths])

  const openGridActions = useCallback((targetPath: string, anchor: { x: number; y: number }) => {
    const paths = resolveGridActionPaths(targetPath)
    setSelectedPaths(paths)
    setCtx({ x: anchor.x, y: anchor.y, kind: 'grid', payload: { paths } })
  }, [resolveGridActionPaths, setSelectedPaths])

  const openFolderActions = useCallback((path: string, anchor: { x: number; y: number }) => {
    setCtx({ x: anchor.x, y: anchor.y, kind: 'tree', payload: { path } })
  }, [])

  useEffect(() => {
    if (!moveDialog) return
    let cancelled = false
    setMoveFoldersLoading(true)
    void collectMoveFolders()
      .then((paths) => {
        if (!cancelled) setMoveFolders(paths)
      })
      .catch((err) => {
        if (!cancelled) setActionError(formatMutationError(err, 'Failed to load destination folders.'))
      })
      .finally(() => {
        if (!cancelled) setMoveFoldersLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [moveDialog])

  const moveSelectedToFolder = useCallback(async (paths: string[], destination: string): Promise<boolean> => {
    const selected = dedupePaths(paths)
    if (!selected.length) return false
    const targetDir = sanitizePath(destination || '/')
    setActionError(null)

    const failures: string[] = []
    const failedPaths: string[] = []
    for (const path of selected) {
      try {
        await api.moveFile(path, targetDir)
      } catch (err) {
        failures.push(`${getPathName(path) || path}: ${formatMutationError(err, 'Move failed.')}`)
        failedPaths.push(path)
      }
    }
    try {
      await queryClient.invalidateQueries({
        predicate: ({ queryKey }) => Array.isArray(queryKey) && queryKey[0] === 'folder',
      })
      invalidateDerivedCounts()
      await refetch()
    } catch (err) {
      failures.push(formatMutationError(err, 'Move completed, but refresh failed.'))
    }

    if (failures.length) {
      setActionError(summarizeFailures('Move', failures))
      setSelectedPaths(failedPaths)
      return false
    }

    setMoveDialog(null)
    setCtx(null)
    const moved = new Set(selected)
    setSelectedPaths((prev) => prev.filter((path) => !moved.has(path)))
    return true
  }, [invalidateDerivedCounts, queryClient, refetch, setSelectedPaths])

  const openMoveDialogForPaths = useCallback((paths: string[]) => {
    const selected = dedupePaths(paths)
    if (!selected.length) return
    setActionError(null)
    setMoveDialog({ paths: selected })
    setCtx(null)
  }, [])

  const uploadFiles = useCallback(async (files: File[]): Promise<void> => {
    if (!files.length) return
    const isLeaf = currentDirCount === 0
    if (!isLeaf) {
      setActionError('Uploads are only allowed into folders without subdirectories.')
      return
    }

    setUploading(true)
    setActionError(null)
    const failures: string[] = []

    try {
      for (const file of files) {
        try {
          await api.uploadFile(current, file)
        } catch (err) {
          failures.push(`${file.name}: ${formatMutationError(err, 'Upload failed.')}`)
        }
      }
      try {
        await refetch()
      } catch (err) {
        failures.push(formatMutationError(err, 'Upload completed, but refresh failed.'))
      }
    } finally {
      setUploading(false)
    }

    if (failures.length) {
      setActionError(summarizeFailures('Upload', failures))
      return
    }
    setActionError(null)
  }, [current, currentDirCount, refetch])

  const openUploadPicker = useCallback(() => {
    if (uploading) return
    uploadInputRef.current?.click()
  }, [uploadInputRef, uploading])

  const handleUploadInputChange = useCallback(async (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? [])
    event.target.value = ''
    if (!files.length) return
    await uploadFiles(files)
  }, [uploadFiles])

  useEffect(() => {
    const el = appRef.current
    if (!el) return

    const onDragOver = (e: DragEvent) => {
      if (!e.dataTransfer) return
      if (Array.from(e.dataTransfer.types).includes('Files')) {
        e.preventDefault()
        setDraggingOver(true)
      }
    }

    const onDragLeave = (e: DragEvent) => {
      const related = e.relatedTarget as Node | null
      if (related && el.contains(related)) return
      setDraggingOver(false)
    }

    const onDrop = async (e: DragEvent) => {
      e.preventDefault()
      setDraggingOver(false)

      const files = Array.from(e.dataTransfer?.files ?? [])
      if (!files.length) return
      await uploadFiles(files)
    }

    el.addEventListener('dragover', onDragOver)
    el.addEventListener('dragleave', onDragLeave)
    el.addEventListener('drop', onDrop)

    return () => {
      el.removeEventListener('dragover', onDragOver)
      el.removeEventListener('dragleave', onDragLeave)
      el.removeEventListener('drop', onDrop)
    }
  }, [appRef, uploadFiles])

  useEffect(() => {
    const onGlobalClick = () => setCtx(null)
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setCtx(null)
    }

    window.addEventListener('click', onGlobalClick)
    window.addEventListener('keydown', onEsc)

    return () => {
      window.removeEventListener('click', onGlobalClick)
      window.removeEventListener('keydown', onEsc)
    }
  }, [])

  const closeMoveDialog = useCallback(() => {
    setMoveDialog(null)
  }, [])

  return {
    uploading,
    actionError,
    isDraggingOver,
    moveDialog,
    moveFolders,
    moveFoldersLoading,
    ctx,
    setCtx,
    closeMoveDialog,
    openUploadPicker,
    handleUploadInputChange,
    openGridActions,
    openFolderActions,
    openMoveDialogForPaths,
    moveSelectedToFolder,
  }
}

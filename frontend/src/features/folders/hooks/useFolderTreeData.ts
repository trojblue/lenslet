import { useCallback, useEffect, useMemo, useRef } from 'react'
import { useQueries, useQueryClient, type UseQueryResult } from '@tanstack/react-query'
import { folderCountQueryOptions, folderQueryOptions } from '../../../api/folders'
import { usePollingEnabled } from '../../../api/polling'
import { joinPath } from '../../../lib/paths'
import type { BrowseFolderPayload } from '../../../lib/types'
import type { FolderRoot } from '../model/treeRows'

// Query observers belong to expanded/current paths, not virtual rows. Collapsed
// branches retain settled records without keeping inactive query observers alive.
// The parent keys this tree by workspace/source identity to retire those records.
export function useFolderTreeData(
  roots: readonly FolderRoot[],
  expanded: ReadonlySet<string>,
  current: string,
  active: boolean,
  initial?: BrowseFolderPayload,
  countVersion = 0,
) {
  const polling = usePollingEnabled()
  const queryClient = useQueryClient()
  const previousCountVersion = useRef(countVersion)
  useEffect(() => {
    if (previousCountVersion.current === countVersion) return
    previousCountVersion.current = countVersion
    void queryClient.invalidateQueries({ queryKey: ['folder-count'] })
  }, [countVersion, queryClient])
  const paths = useMemo(() => [...new Set([
    ...roots.map((root) => root.path), ...expanded, current,
  ])], [roots, expanded, current])
  const settledPayloads = useRef<Record<string, BrowseFolderPayload>>({})
  const settledCounts = useRef<Record<string, number>>({})
  const rootPaths = new Set(roots.map((root) => root.path))
  const combine = useCallback((results: UseQueryResult<BrowseFolderPayload>[]) => ({
    payloads: Object.fromEntries(results.map((result, index) => [paths[index], result.data])),
    errors: results.flatMap((result, index) => result.isError ? [paths[index]] : []),
  }), [paths])
  const combined = useQueries({
    queries: paths.map((path) => folderQueryOptions(path, {
      enabled: active && (rootPaths.has(path) || expanded.has(path) || current === path),
    }, polling)),
    combine,
  })
  const payloads = useMemo(() => {
    const next = { ...settledPayloads.current }
    for (const [path, payload] of Object.entries(combined.payloads)) {
      if (payload) next[path] = payload
    }
    if (initial) next[initial.path] = initial
    settledPayloads.current = next
    return next
  }, [combined.payloads, initial])
  const errors = useMemo(() => new Set(combined.errors), [combined.errors])
  const combineCounts = useCallback((results: UseQueryResult<number>[]) => ({
    values: Object.fromEntries(results.map((result, index) => [paths[index], result.data])),
    pending: results.flatMap((result, index) => result.isFetching && result.data == null ? [paths[index]] : []),
  }), [paths])
  const indexedCounts = useMemo(() => Object.fromEntries(
    Object.values(payloads).flatMap((payload) => payload.folders.flatMap((folder) => (
      folder.total_items == null ? [] : [[joinPath(payload.path, folder.name), folder.total_items]]
    ))),
  ), [payloads])
  const countQueries = useQueries({
    queries: paths.map((path) => folderCountQueryOptions(path, {
      enabled: active && indexedCounts[path] == null && !!payloads[path] && expanded.has(path)
        && (rootPaths.has(path) || !!payloads[path.slice(0, path.lastIndexOf('/')) || '/'])
        && (path !== '/' || current === path),
    }, polling)),
    combine: combineCounts,
  })
  const counts = useMemo(() => {
    const next = { ...settledCounts.current }
    for (const [path, count] of Object.entries(countQueries.values)) {
      if (count != null) next[path] = count
    }
    settledCounts.current = next
    return next
  }, [countQueries.values])
  const pendingCounts = useMemo(() => new Set(countQueries.pending), [countQueries.pending])
  return { payloads, errors, counts, pendingCounts }
}

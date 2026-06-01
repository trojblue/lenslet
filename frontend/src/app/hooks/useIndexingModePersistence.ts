import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type Dispatch,
  type SetStateAction,
} from 'react'
import type { ViewState } from '../../lib/types'
import {
  captureScanGeneration,
  deriveIndexingBrowseMode,
  normalizeIndexingGeneration,
  type IndexingBrowseMode,
} from '../model/indexingBrowseMode'
import type { HealthIndexing } from './healthIndexing'

const INDEXING_MODE_STORAGE_KEYS = {
  scanGeneration: 'indexingScanGeneration',
  recentGeneration: 'indexingMostRecentGeneration',
} as const

type UseIndexingModePersistenceParams = {
  indexing: HealthIndexing | null
  setScanStableMode: Dispatch<SetStateAction<boolean>>
  setViewState: Dispatch<SetStateAction<ViewState>>
}

type UseIndexingModePersistenceResult = {
  indexingBrowseMode: IndexingBrowseMode
  handleSwitchToMostRecent: () => void
}

function readStoredGeneration(key: string): string | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.localStorage.getItem(key)
    return normalizeIndexingGeneration(raw)
  } catch {
    return null
  }
}

function writeStoredGeneration(key: string, generation: string): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(key, generation)
  } catch {
    // Ignore storage failures.
  }
}

export function useIndexingModePersistence({
  indexing,
  setScanStableMode,
  setViewState,
}: UseIndexingModePersistenceParams): UseIndexingModePersistenceResult {
  const [scanGeneration, setScanGeneration] = useState<string | null>(() => (
    readStoredGeneration(INDEXING_MODE_STORAGE_KEYS.scanGeneration)
  ))
  const [recentGeneration, setRecentGeneration] = useState<string | null>(() => (
    readStoredGeneration(INDEXING_MODE_STORAGE_KEYS.recentGeneration)
  ))

  useEffect(() => {
    const nextScanGeneration = captureScanGeneration(scanGeneration, indexing)
    if (!nextScanGeneration || nextScanGeneration === scanGeneration) return
    setScanGeneration(nextScanGeneration)
    writeStoredGeneration(INDEXING_MODE_STORAGE_KEYS.scanGeneration, nextScanGeneration)
  }, [indexing, scanGeneration])

  const indexingBrowseMode = useMemo(() => {
    return deriveIndexingBrowseMode(indexing, {
      scanGeneration,
      recentGeneration,
    })
  }, [indexing, recentGeneration, scanGeneration])

  useEffect(() => {
    setScanStableMode((prev) => (
      prev === indexingBrowseMode.scanStableActive
        ? prev
        : indexingBrowseMode.scanStableActive
    ))
  }, [indexingBrowseMode.scanStableActive, setScanStableMode])

  const handleSwitchToMostRecent = useCallback(() => {
    const generation = normalizeIndexingGeneration(indexing?.generation) ?? scanGeneration
    if (!generation) return
    if (recentGeneration !== generation) {
      setRecentGeneration(generation)
      writeStoredGeneration(INDEXING_MODE_STORAGE_KEYS.recentGeneration, generation)
    }
    setViewState((prev) => {
      if (prev.sort.kind === 'builtin' && prev.sort.key === 'added' && prev.sort.dir === 'desc') {
        return prev
      }
      return {
        ...prev,
        sort: { kind: 'builtin', key: 'added', dir: 'desc' },
      }
    })
  }, [indexing?.generation, recentGeneration, scanGeneration, setViewState])

  return {
    indexingBrowseMode,
    handleSwitchToMostRecent,
  }
}

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from 'react'
import { normalizeFilterAst } from '../../features/browse/model/filters'
import type {
  CompareOrderMode,
  FilterAST,
  SortSpec,
  ViewMode,
  ViewState,
} from '../../lib/types'
import { safeJsonParse } from '../../lib/util'
import {
  createDeferredWriteScheduler,
  type PersistedAppShellSettings,
} from '../model/appShellStateSync'

export const STORAGE_KEYS = {
  sortKey: 'sortKey',
  sortDir: 'sortDir',
  sortSpec: 'sortSpec',
  filterAst: 'filterAst',
  selectedMetric: 'selectedMetric',
  viewMode: 'viewMode',
  gridItemSize: 'gridItemSize',
  leftOpen: 'leftOpen',
  rightOpen: 'rightOpen',
  autoloadImageMetadata: 'autoloadImageMetadata',
  compareOrderMode: 'compareOrderMode',
} as const

type UsePersistedAppShellSettingsParams = {
  viewState: ViewState
  viewMode: ViewMode
  gridItemSize: number
  leftOpen: boolean
  rightOpen: boolean
  autoloadImageMetadata: boolean
  compareOrderMode: CompareOrderMode
  setViewState: Dispatch<SetStateAction<ViewState>>
  setRandomSeed: Dispatch<SetStateAction<number>>
  setViewMode: Dispatch<SetStateAction<ViewMode>>
  setGridItemSize: Dispatch<SetStateAction<number>>
  setLeftOpen: Dispatch<SetStateAction<boolean>>
  setRightOpen: Dispatch<SetStateAction<boolean>>
  setAutoloadImageMetadata: Dispatch<SetStateAction<boolean>>
  setCompareOrderMode: Dispatch<SetStateAction<CompareOrderMode>>
}

function writePersistedSettings(settings: PersistedAppShellSettings): void {
  if (typeof window === 'undefined') return
  try {
    const storage = window.localStorage
    storage.setItem(
      STORAGE_KEYS.sortKey,
      settings.sortSpec.kind === 'builtin' ? settings.sortSpec.key : 'added',
    )
    storage.setItem(STORAGE_KEYS.sortDir, settings.sortSpec.dir)
    storage.setItem(STORAGE_KEYS.sortSpec, JSON.stringify(settings.sortSpec))
    storage.setItem(STORAGE_KEYS.filterAst, JSON.stringify(settings.filterAst))
    if (settings.selectedMetric) {
      storage.setItem(STORAGE_KEYS.selectedMetric, settings.selectedMetric)
    } else {
      storage.removeItem(STORAGE_KEYS.selectedMetric)
    }
    storage.setItem(STORAGE_KEYS.viewMode, settings.viewMode)
    storage.setItem(STORAGE_KEYS.gridItemSize, String(settings.gridItemSize))
    storage.setItem(STORAGE_KEYS.leftOpen, settings.leftOpen ? '1' : '0')
    storage.setItem(STORAGE_KEYS.rightOpen, settings.rightOpen ? '1' : '0')
    storage.setItem(
      STORAGE_KEYS.autoloadImageMetadata,
      settings.autoloadImageMetadata ? '1' : '0',
    )
    storage.setItem(STORAGE_KEYS.compareOrderMode, settings.compareOrderMode)
  } catch {
    // Ignore localStorage errors.
  }
}

function isSortDir(value: unknown): value is SortSpec['dir'] {
  return value === 'asc' || value === 'desc'
}

function parseSortSpec(raw: string | null): SortSpec | null {
  if (!raw) return null
  const parsed = safeJsonParse<unknown>(raw)
  if (!parsed || typeof parsed !== 'object') return null
  const spec = parsed as Partial<SortSpec>
  if (spec.kind === 'builtin') {
    if (
      (spec.key === 'name' || spec.key === 'added' || spec.key === 'random') &&
      isSortDir(spec.dir)
    ) {
      return spec as SortSpec
    }
  }
  if (spec.kind === 'metric') {
    if (typeof spec.key === 'string' && spec.key.length > 0 && isSortDir(spec.dir)) {
      return spec as SortSpec
    }
  }
  return null
}

function parseFilterAst(raw: string | null): FilterAST | null {
  if (!raw) return null
  const parsed = safeJsonParse<unknown>(raw)
  return normalizeFilterAst(parsed)
}

export function usePersistedAppShellSettings({
  viewState,
  viewMode,
  gridItemSize,
  leftOpen,
  rightOpen,
  autoloadImageMetadata,
  compareOrderMode,
  setViewState,
  setRandomSeed,
  setViewMode,
  setGridItemSize,
  setLeftOpen,
  setRightOpen,
  setAutoloadImageMetadata,
  setCompareOrderMode,
}: UsePersistedAppShellSettingsParams): void {
  const [persistedSettingsReady, setPersistedSettingsReady] = useState(false)
  const writerRef = useRef(
    createDeferredWriteScheduler<PersistedAppShellSettings>(writePersistedSettings),
  )

  useEffect(() => {
    if (typeof window === 'undefined') return
    const writer = writerRef.current
    const flush = () => {
      writer.flush()
    }
    window.addEventListener('pagehide', flush)
    window.addEventListener('beforeunload', flush)
    return () => {
      window.removeEventListener('pagehide', flush)
      window.removeEventListener('beforeunload', flush)
      writer.flush()
    }
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined') {
      setPersistedSettingsReady(true)
      return
    }
    try {
      const storage = window.localStorage
      const storedSortKey = storage.getItem(STORAGE_KEYS.sortKey)
      const storedSortDir = storage.getItem(STORAGE_KEYS.sortDir)
      const storedSortSpec = storage.getItem(STORAGE_KEYS.sortSpec)
      const storedFilterAst = storage.getItem(STORAGE_KEYS.filterAst)
      const storedSelectedMetric = storage.getItem(STORAGE_KEYS.selectedMetric)
      const storedViewMode = storage.getItem(STORAGE_KEYS.viewMode) as ViewMode | null
      const storedGridSize = storage.getItem(STORAGE_KEYS.gridItemSize)
      const storedLeftOpen = storage.getItem(STORAGE_KEYS.leftOpen)
      const storedRightOpen = storage.getItem(STORAGE_KEYS.rightOpen)
      const storedAutoloadImageMetadata = storage.getItem(STORAGE_KEYS.autoloadImageMetadata)
      const storedCompareOrderMode = storage.getItem(STORAGE_KEYS.compareOrderMode)

      const sort: SortSpec = parseSortSpec(storedSortSpec) ?? {
        kind: 'builtin',
        key: storedSortKey === 'name' || storedSortKey === 'added' || storedSortKey === 'random'
          ? storedSortKey
          : 'added',
        dir: storedSortDir === 'asc' || storedSortDir === 'desc' ? storedSortDir : 'desc',
      }
      if (sort.key === 'random') {
        setRandomSeed(Date.now())
      }

      const filters = parseFilterAst(storedFilterAst) ?? { and: [] }
      setViewState((prev) => ({
        ...prev,
        sort,
        filters,
        selectedMetric: storedSelectedMetric || prev.selectedMetric,
      }))

      if (storedViewMode === 'grid' || storedViewMode === 'adaptive') {
        setViewMode(storedViewMode)
      }
      if (storedGridSize) {
        const size = Number(storedGridSize)
        if (!Number.isNaN(size) && size >= 80 && size <= 500) {
          setGridItemSize(size)
        }
      }
      if (storedLeftOpen === '0' || storedLeftOpen === 'false') setLeftOpen(false)
      if (storedRightOpen === '0' || storedRightOpen === 'false') setRightOpen(false)
      if (storedAutoloadImageMetadata === '0' || storedAutoloadImageMetadata === 'false') {
        setAutoloadImageMetadata(false)
      } else if (storedAutoloadImageMetadata === '1' || storedAutoloadImageMetadata === 'true') {
        setAutoloadImageMetadata(true)
      }
      if (storedCompareOrderMode === 'gallery' || storedCompareOrderMode === 'selection') {
        setCompareOrderMode(storedCompareOrderMode)
      }
    } catch {
      // Ignore localStorage errors.
    }
    setPersistedSettingsReady(true)
  }, [
    setAutoloadImageMetadata,
    setCompareOrderMode,
    setGridItemSize,
    setLeftOpen,
    setRandomSeed,
    setRightOpen,
    setViewMode,
    setViewState,
  ])

  const persistedSettings = useMemo<PersistedAppShellSettings>(() => ({
    sortSpec: viewState.sort,
    filterAst: viewState.filters,
    selectedMetric: viewState.selectedMetric,
    viewMode,
    gridItemSize,
    leftOpen,
    rightOpen,
    autoloadImageMetadata,
    compareOrderMode,
  }), [
    autoloadImageMetadata,
    compareOrderMode,
    gridItemSize,
    leftOpen,
    rightOpen,
    viewMode,
    viewState.filters,
    viewState.selectedMetric,
    viewState.sort,
  ])

  useEffect(() => {
    if (!persistedSettingsReady) return
    writerRef.current.schedule(persistedSettings)
  }, [persistedSettings, persistedSettingsReady])
}

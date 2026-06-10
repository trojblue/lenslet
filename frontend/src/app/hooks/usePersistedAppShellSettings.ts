import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from 'react'
import type {
  CompareOrderMode,
  ViewMode,
  ViewState,
} from '../../lib/types'
import {
  createDeferredWriteScheduler,
  type PersistedAppShellSettings,
} from '../model/appShellStateSync'

export const STORAGE_KEYS = {
  viewState: 'viewState',
  viewMode: 'viewMode',
  gridItemSize: 'gridItemSize',
  leftOpen: 'leftOpen',
  rightOpen: 'rightOpen',
  autoloadImageMetadata: 'autoloadImageMetadata',
  compareOrderMode: 'compareOrderMode',
  proxyHttpOriginals: 'proxyHttpOriginals',
} as const

const LEGACY_VIEW_STORAGE_KEYS = [
  'sortKey',
  'sortDir',
  'sortSpec',
  'filterAst',
  'selectedMetric',
] as const

export type RestoredAppShellSettings = {
  viewState?: ViewState
  viewMode?: ViewMode
  gridItemSize?: number
  leftOpen?: boolean
  rightOpen?: boolean
  autoloadImageMetadata?: boolean
  compareOrderMode?: CompareOrderMode
  proxyHttpOriginals?: boolean
}

type UsePersistedAppShellSettingsParams = {
  viewState: ViewState
  viewMode: ViewMode
  gridItemSize: number
  leftOpen: boolean
  rightOpen: boolean
  autoloadImageMetadata: boolean
  compareOrderMode: CompareOrderMode
  proxyHttpOriginals: boolean
  setViewState: Dispatch<SetStateAction<ViewState>>
  setRandomSeed: Dispatch<SetStateAction<number>>
  setViewMode: Dispatch<SetStateAction<ViewMode>>
  setGridItemSize: Dispatch<SetStateAction<number>>
  setLeftOpen: Dispatch<SetStateAction<boolean>>
  setRightOpen: Dispatch<SetStateAction<boolean>>
  setAutoloadImageMetadata: Dispatch<SetStateAction<boolean>>
  setCompareOrderMode: Dispatch<SetStateAction<CompareOrderMode>>
  setProxyHttpOriginals: Dispatch<SetStateAction<boolean>>
  restoreViewState?: boolean
}

export function writePersistedSettingsToStorage(
  storage: Storage,
  settings: PersistedAppShellSettings,
): void {
  storage.removeItem(STORAGE_KEYS.viewState)
  for (const key of LEGACY_VIEW_STORAGE_KEYS) {
    storage.removeItem(key)
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
  storage.setItem(STORAGE_KEYS.proxyHttpOriginals, settings.proxyHttpOriginals ? '1' : '0')
}

export function readPersistedSettingsFromStorage(storage: Storage): RestoredAppShellSettings {
  const restored: RestoredAppShellSettings = {}

  const storedViewMode = storage.getItem(STORAGE_KEYS.viewMode)
  if (storedViewMode === 'grid' || storedViewMode === 'adaptive') {
    restored.viewMode = storedViewMode
  }

  const storedGridSize = storage.getItem(STORAGE_KEYS.gridItemSize)
  if (storedGridSize) {
    const size = Number(storedGridSize)
    if (!Number.isNaN(size) && size >= 80 && size <= 500) {
      restored.gridItemSize = size
    }
  }

  const storedLeftOpen = storage.getItem(STORAGE_KEYS.leftOpen)
  if (storedLeftOpen === '0' || storedLeftOpen === 'false') {
    restored.leftOpen = false
  }

  const storedRightOpen = storage.getItem(STORAGE_KEYS.rightOpen)
  if (storedRightOpen === '0' || storedRightOpen === 'false') {
    restored.rightOpen = false
  }

  const storedAutoloadImageMetadata = storage.getItem(STORAGE_KEYS.autoloadImageMetadata)
  if (storedAutoloadImageMetadata === '0' || storedAutoloadImageMetadata === 'false') {
    restored.autoloadImageMetadata = false
  } else if (storedAutoloadImageMetadata === '1' || storedAutoloadImageMetadata === 'true') {
    restored.autoloadImageMetadata = true
  }

  const storedCompareOrderMode = storage.getItem(STORAGE_KEYS.compareOrderMode)
  if (storedCompareOrderMode === 'gallery' || storedCompareOrderMode === 'selection') {
    restored.compareOrderMode = storedCompareOrderMode
  }

  const storedProxyHttpOriginals = storage.getItem(STORAGE_KEYS.proxyHttpOriginals)
  if (storedProxyHttpOriginals === '1' || storedProxyHttpOriginals === 'true') {
    restored.proxyHttpOriginals = true
  } else if (storedProxyHttpOriginals === '0' || storedProxyHttpOriginals === 'false') {
    restored.proxyHttpOriginals = false
  }

  return restored
}

function writePersistedSettings(settings: PersistedAppShellSettings): void {
  if (typeof window === 'undefined') return
  try {
    writePersistedSettingsToStorage(window.localStorage, settings)
  } catch {
    // Ignore localStorage errors.
  }
}

export function usePersistedAppShellSettings({
  viewState,
  viewMode,
  gridItemSize,
  leftOpen,
  rightOpen,
  autoloadImageMetadata,
  compareOrderMode,
  proxyHttpOriginals,
  setViewState,
  setRandomSeed,
  setViewMode,
  setGridItemSize,
  setLeftOpen,
  setRightOpen,
  setAutoloadImageMetadata,
  setCompareOrderMode,
  setProxyHttpOriginals,
  restoreViewState = true,
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
      const restored = readPersistedSettingsFromStorage(storage)
      if (restoreViewState && restored.viewState) {
        if (restored.viewState.sort.kind === 'builtin' && restored.viewState.sort.key === 'random') {
          setRandomSeed(Date.now())
        }
        setViewState(restored.viewState)
      }

      if (restored.viewMode) {
        setViewMode(restored.viewMode)
      }
      if (restored.gridItemSize !== undefined) {
        setGridItemSize(restored.gridItemSize)
      }
      if (restored.leftOpen !== undefined) {
        setLeftOpen(restored.leftOpen)
      }
      if (restored.rightOpen !== undefined) {
        setRightOpen(restored.rightOpen)
      }
      if (restored.autoloadImageMetadata !== undefined) {
        setAutoloadImageMetadata(restored.autoloadImageMetadata)
      }
      if (restored.compareOrderMode) {
        setCompareOrderMode(restored.compareOrderMode)
      }
      if (restored.proxyHttpOriginals !== undefined) {
        setProxyHttpOriginals(restored.proxyHttpOriginals)
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
    setProxyHttpOriginals,
    setRandomSeed,
    setRightOpen,
    setViewMode,
    setViewState,
    restoreViewState,
  ])

  const persistedSettings = useMemo<PersistedAppShellSettings>(() => ({
    viewState,
    viewMode,
    gridItemSize,
    leftOpen,
    rightOpen,
    autoloadImageMetadata,
    compareOrderMode,
    proxyHttpOriginals,
  }), [
    autoloadImageMetadata,
    compareOrderMode,
    gridItemSize,
    leftOpen,
    proxyHttpOriginals,
    rightOpen,
    viewMode,
    viewState,
  ])

  useEffect(() => {
    if (!persistedSettingsReady) return
    writerRef.current.schedule(persistedSettings)
  }, [persistedSettings, persistedSettingsReady])
}

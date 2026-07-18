import { useEffect, useMemo, useRef } from 'react'
import type { CompareOrderMode, ViewMode } from '../../lib/types'
import { GRID_ITEM_SIZE_CONTRACT } from '../../lib/gridItemSize'
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
  viewMode?: ViewMode
  gridItemSize?: number
  leftOpen?: boolean
  rightOpen?: boolean
  autoloadImageMetadata?: boolean
  compareOrderMode?: CompareOrderMode
  proxyHttpOriginals?: boolean
}

type UsePersistedAppShellSettingsParams = {
  viewMode: ViewMode
  gridItemSize: number
  leftOpen: boolean
  rightOpen: boolean
  autoloadImageMetadata: boolean
  compareOrderMode: CompareOrderMode
  proxyHttpOriginals: boolean
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
    if (
      !Number.isNaN(size)
      && size >= GRID_ITEM_SIZE_CONTRACT.min
      && size <= GRID_ITEM_SIZE_CONTRACT.max
    ) {
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

export function readInitialPersistedAppShellSettings(): RestoredAppShellSettings {
  if (typeof window === 'undefined') return {}
  try {
    return readPersistedSettingsFromStorage(window.localStorage)
  } catch {
    return {}
  }
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
  viewMode,
  gridItemSize,
  leftOpen,
  rightOpen,
  autoloadImageMetadata,
  compareOrderMode,
  proxyHttpOriginals,
}: UsePersistedAppShellSettingsParams): void {
  const writerRef = useRef(
    createDeferredWriteScheduler<PersistedAppShellSettings>(writePersistedSettings),
  )

  useEffect(() => {
    if (typeof window === 'undefined') return
    const writer = writerRef.current
    const flush = () => writer.flush()
    window.addEventListener('pagehide', flush)
    window.addEventListener('beforeunload', flush)
    return () => {
      window.removeEventListener('pagehide', flush)
      window.removeEventListener('beforeunload', flush)
      writer.flush()
    }
  }, [])

  const persistedSettings = useMemo<PersistedAppShellSettings>(() => ({
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
  ])

  useEffect(() => {
    writerRef.current.schedule(persistedSettings)
  }, [persistedSettings])
}

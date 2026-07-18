import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Copy } from 'lucide-react'
import { THEME_PRESETS, resolveThemePresetId, type ThemePresetId } from '../../theme/runtime'
import type {
  CompareOrderMode,
  LaunchSessionPayload,
  TableLaunchStatusPayload,
  TableSourceColumnOption,
  TableSourceColumnsPayload,
} from '../../lib/types'
import Dropdown from './Dropdown'
import {
  clampMenuPosition,
  getVisibleViewportBounds,
  subscribeVisibleViewportChanges,
  type ViewportBounds,
} from '../../lib/menuPosition'

export type ThemeSettingsMenuPlacement = 'sidebar' | 'mobile'
export type ThemeSettingsMenuCloseIntent = 'toggle' | 'close' | 'escape' | 'outside_click' | 'select'

type ThemeSettingsMenuProps = {
  value: ThemePresetId
  onChange: (themeId: ThemePresetId) => void
  placement: ThemeSettingsMenuPlacement
  autoloadImageMetadata?: boolean
  onAutoloadImageMetadataChange?: (enabled: boolean) => void
  compareOrderMode?: CompareOrderMode
  onCompareOrderModeChange?: (mode: CompareOrderMode) => void
  proxyHttpOriginals?: boolean
  onProxyHttpOriginalsChange?: (enabled: boolean) => void
  sourceColumns?: TableSourceColumnsPayload | null
  tableLaunchStatus?: TableLaunchStatusPayload | null
  launchSession?: LaunchSessionPayload | null
  sourceColumnSwitching?: boolean
  onSourceColumnChange?: (sourceColumn: string) => void
}

type ThemeMenuOption = {
  id: ThemePresetId
  label: string
  accent: string
}

export type SourceColumnMenuState = {
  enabled: boolean
  selectedSourceColumn: string
  selectedSourceStatus: TableSourceColumnOption | null
}

type RectLike = {
  left: number
  right: number
  top: number
  bottom: number
}

type SizeLike = {
  width: number
  height: number
}

type ThemeMenuPanelLayout = {
  placement: ThemeSettingsMenuPlacement
  anchorRect: RectLike
  panelSize: SizeLike
  viewport: ViewportBounds
}

type ThemeMenuPanelPosition = {
  x: number
  y: number
  ready: boolean
  maxHeight: number | null
}

type ClipboardWriter = {
  writeText: (text: string) => Promise<void> | void
}

const THEME_OPTIONS: readonly ThemeMenuOption[] = (['default', 'teal', 'charcoal'] as const).map((id) => ({
  id,
  label: THEME_PRESETS[id].label,
  accent: THEME_PRESETS[id].tokens['--accent'],
}))
const VIEWPORT_PADDING = 8
const SIDEBAR_PANEL_GAP = 10
const MOBILE_PANEL_GAP = 8
const useIsomorphicLayoutEffect = typeof window === 'undefined' ? useEffect : useLayoutEffect

function getInitialPanelPosition(): ThemeMenuPanelPosition {
  return { x: 0, y: 0, ready: false, maxHeight: null }
}

export function getThemeMenuPanelPosition({
  placement,
  anchorRect,
  panelSize,
  viewport,
}: ThemeMenuPanelLayout): { x: number; y: number } {
  if (placement === 'sidebar') {
    return clampMenuPosition({
      x: anchorRect.right + SIDEBAR_PANEL_GAP,
      y: anchorRect.bottom - panelSize.height,
      menuWidth: panelSize.width,
      menuHeight: panelSize.height,
      viewport,
      margin: VIEWPORT_PADDING,
    })
  }

  return clampMenuPosition({
    x: anchorRect.left,
    y: anchorRect.top - panelSize.height - MOBILE_PANEL_GAP,
    menuWidth: panelSize.width,
    menuHeight: panelSize.height,
    viewport,
    margin: VIEWPORT_PADDING,
  })
}

export function getThemeMenuPanelMaxHeight(
  placement: ThemeSettingsMenuPlacement,
  anchorRect: RectLike,
  viewport: ViewportBounds,
): number {
  const anchoredBottom = placement === 'sidebar'
    ? anchorRect.bottom
    : anchorRect.top - MOBILE_PANEL_GAP
  return Math.max(1, Math.min(
    viewport.height - VIEWPORT_PADDING * 2,
    anchoredBottom - viewport.top - VIEWPORT_PADDING,
  ))
}

export function resolveThemeMenuSelection(value: string | null | undefined): ThemePresetId {
  return resolveThemePresetId(value)
}

export function resolveSourceColumnMenuState(
  sourceColumns?: TableSourceColumnsPayload | null,
): SourceColumnMenuState {
  const selectedSourceColumn = sourceColumns?.current ?? ''
  return {
    enabled: sourceColumns?.enabled === true && sourceColumns.columns.length > 0,
    selectedSourceColumn,
    selectedSourceStatus: sourceColumns?.columns.find((column) => column.name === selectedSourceColumn) ?? null,
  }
}

export function reduceThemeSettingsMenuOpenState(open: boolean, intent: ThemeSettingsMenuCloseIntent): boolean {
  if (intent === 'toggle') return !open
  return false
}

export async function copyLaunchCommandToClipboard(
  command: string,
  clipboard: ClipboardWriter | null | undefined = typeof navigator !== 'undefined' ? navigator.clipboard : null,
): Promise<boolean> {
  if (!clipboard) return false
  try {
    await clipboard.writeText(command)
    return true
  } catch {
    return false
  }
}

export function LaunchSessionMenuSection({
  launchSession,
  onCopyCommand,
}: {
  launchSession: LaunchSessionPayload
  onCopyCommand?: (command: string) => void
}): JSX.Element {
  const copyCommand = launchSession.copy_command?.trim() || null
  return (
    <>
      <div className="theme-settings-menu-divider" />
      <div className="theme-settings-menu-header">Session</div>
      <div className="theme-settings-menu-options">
        <div className="theme-settings-menu-field">
          <span className="theme-settings-menu-option-label">Loaded from</span>
          <span className="theme-settings-menu-option-subtitle">{launchSession.loaded_from_label}</span>
          <span
            className="theme-settings-menu-option-subtitle"
            style={{ color: 'var(--text)', overflowWrap: 'anywhere' }}
          >
            {launchSession.target_label}
          </span>
          {launchSession.detail_label ? (
            <span className="theme-settings-menu-option-subtitle">{launchSession.detail_label}</span>
          ) : null}
          {copyCommand ? (
            <button
              type="button"
              className="theme-settings-menu-option"
              style={{ marginTop: 1, paddingInline: 0 }}
              onClick={() => onCopyCommand?.(copyCommand)}
            >
              <Copy size={13} strokeWidth={1.9} aria-hidden="true" />
              <span className="theme-settings-menu-option-label">Copy command</span>
            </button>
          ) : null}
        </div>
      </div>
    </>
  )
}

function formatCount(value: number): string {
  return value.toLocaleString()
}

function formatTableRows(status: TableLaunchStatusPayload): string {
  if (status.gallery_rows === status.source_table_rows) {
    return `${formatCount(status.gallery_rows)} rows`
  }
  return `${formatCount(status.gallery_rows)} / ${formatCount(status.source_table_rows)} rows`
}

function formatSkippedRows(status: TableLaunchStatusPayload): string | null {
  if (status.skipped_rows.total <= 0) return null
  return `${formatCount(status.skipped_rows.total)} skipped`
}

function formatLaunchSummary(status: TableLaunchStatusPayload): string {
  const skipped = formatSkippedRows(status)
  const source = status.source_column ? `, source: ${status.source_column}` : ''
  return `${formatTableRows(status)}${skipped ? `, ${skipped}` : ''}${source}`
}

function formatDimensionCoverage(status: TableLaunchStatusPayload): string {
  const coverage = status.dimension_coverage
  return `${formatCount(coverage.known)} / ${formatCount(coverage.total)} dimensions`
}

export function formatSourceRefresh(status: TableLaunchStatusPayload): string | null {
  const source = status.source_refresh
  if (!source) return null
  switch (source.state) {
    case 'current':
      return 'Source snapshot: current'
    case 'refreshing':
      return 'Source snapshot: refreshing…'
    case 'stale':
      return source.message || 'Source snapshot: stale'
    case 'restart-required':
      return source.message || 'Source snapshot changed; restart Lenslet to reload it.'
  }
}

function formatMediaPolicyMode(mode: TableLaunchStatusPayload['original_media_policy']['mode']): string {
  switch (mode) {
    case 'local_streaming':
      return 'local streaming'
    case 'backend_proxy_required':
      return 'backend proxy'
    case 'browser_direct_allowed':
      return 'browser direct'
    case 'browser_direct_preferred_with_proxy_fallback':
      return 'browser direct + proxy fallback'
    case 'unsupported':
      return 'unsupported'
  }
}

function getTriggerClassName(placement: ThemeSettingsMenuPlacement): string {
  if (placement === 'sidebar') {
    return 'theme-settings-menu-trigger-sidebar w-11 h-11 rounded-md border border-border flex items-center justify-center transition-colors bg-surface text-text hover:bg-surface-hover'
  }
  return 'theme-settings-menu-trigger-mobile mobile-pill mobile-pill-icon'
}

export default function ThemeSettingsMenu({
  value,
  onChange,
  placement,
  autoloadImageMetadata = true,
  onAutoloadImageMetadataChange,
  compareOrderMode = 'gallery',
  onCompareOrderModeChange,
  proxyHttpOriginals = false,
  onProxyHttpOriginalsChange,
  sourceColumns = null,
  tableLaunchStatus = null,
  launchSession = null,
  sourceColumnSwitching = false,
  onSourceColumnChange,
}: ThemeSettingsMenuProps): JSX.Element {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const [panelPosition, setPanelPosition] = useState<ThemeMenuPanelPosition>(getInitialPanelPosition)
  const selectedThemeId = resolveThemeMenuSelection(value)
  const selectedTheme = THEME_PRESETS[selectedThemeId]
  const supportsInspectorAutoloadSetting = typeof onAutoloadImageMetadataChange === 'function'
  const supportsCompareOrderSetting = typeof onCompareOrderModeChange === 'function'
  const supportsMediaSetting = typeof onProxyHttpOriginalsChange === 'function'
  const sourceColumnState = resolveSourceColumnMenuState(sourceColumns)
  const supportsSourceColumnSetting = sourceColumnState.enabled && typeof onSourceColumnChange === 'function'
  const showSourceSection = supportsSourceColumnSetting || tableLaunchStatus !== null
  const sourceRefreshLabel = tableLaunchStatus ? formatSourceRefresh(tableLaunchStatus) : null
  const { selectedSourceColumn, selectedSourceStatus } = sourceColumnState
  const sourceColumnOptions = useMemo(() => (
    sourceColumns?.columns.map((column) => ({
      value: column.name,
      label: column.name,
      keywords: [column.name],
    })) ?? []
  ), [sourceColumns])
  const handleCopyLaunchCommand = useCallback((command: string) => {
    void copyLaunchCommandToClipboard(command)
  }, [])
  const updatePanelPosition = useCallback(() => {
    if (!open || typeof window === 'undefined') return
    const rootElement = rootRef.current
    const panelElement = panelRef.current
    if (!rootElement || !panelElement) return

    const anchorRect = rootElement.getBoundingClientRect()
    const panelRect = panelElement.getBoundingClientRect()
    const viewport = getVisibleViewportBounds()
    const next = getThemeMenuPanelPosition({
      placement,
      anchorRect,
      panelSize: { width: panelRect.width, height: panelRect.height },
      viewport,
    })
    const maxHeight = getThemeMenuPanelMaxHeight(placement, anchorRect, viewport)

    setPanelPosition((prev) => (
      prev.ready && prev.x === next.x && prev.y === next.y && prev.maxHeight === maxHeight
        ? prev
        : { x: next.x, y: next.y, ready: true, maxHeight }
    ))
  }, [open, placement])

  useIsomorphicLayoutEffect(() => {
    if (!open) {
      setPanelPosition(getInitialPanelPosition())
      return
    }

    updatePanelPosition()
    const panelElement = panelRef.current
    if (!panelElement || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(updatePanelPosition)
    observer.observe(panelElement)
    return () => observer.disconnect()
  }, [open, updatePanelPosition])

  useEffect(() => {
    if (!open) return

    const onWindowClick = (event: MouseEvent) => {
      const target = event.target as Node | null
      if (target && rootRef.current?.contains(target)) return
      if (target && panelRef.current?.contains(target)) return
      setOpen((current) => reduceThemeSettingsMenuOpenState(current, 'outside_click'))
    }

    const onWindowKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      setOpen((current) => reduceThemeSettingsMenuOpenState(current, 'escape'))
    }

    window.addEventListener('click', onWindowClick)
    window.addEventListener('keydown', onWindowKeyDown)
    const unsubscribeViewport = subscribeVisibleViewportChanges(updatePanelPosition)
    return () => {
      window.removeEventListener('click', onWindowClick)
      window.removeEventListener('keydown', onWindowKeyDown)
      unsubscribeViewport()
    }
  }, [open, updatePanelPosition])

  const triggerTitle = `Settings (${selectedTheme.label})`

  const panelStyle = {
    position: 'fixed' as const,
    left: panelPosition.x,
    top: panelPosition.y,
    visibility: panelPosition.ready ? ('visible' as const) : ('hidden' as const),
    maxHeight: panelPosition.maxHeight ?? undefined,
  }

  const panelNode = open ? (
    <div
      ref={panelRef}
      className="theme-settings-menu-panel scrollbar-thin"
      role="menu"
      aria-label="Settings"
      style={panelStyle}
    >
      <div className="theme-settings-menu-header">Theme</div>
      <div className="theme-settings-menu-options">
        {THEME_OPTIONS.map((option) => {
          const active = option.id === selectedThemeId
          return (
            <button
              key={option.id}
              type="button"
              className={`theme-settings-menu-option ${active ? 'is-active' : ''}`}
              role="menuitemradio"
              aria-checked={active}
              onClick={() => {
                onChange(option.id)
                setOpen((current) => reduceThemeSettingsMenuOpenState(current, 'select'))
              }}
            >
              <span
                className="theme-settings-menu-option-swatch"
                style={{ backgroundColor: option.accent }}
                aria-hidden="true"
              />
              <span className="theme-settings-menu-option-label">{option.label}</span>
              {active ? (
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              ) : null}
            </button>
          )
        })}
      </div>
      {launchSession ? (
        <LaunchSessionMenuSection
          launchSession={launchSession}
          onCopyCommand={handleCopyLaunchCommand}
        />
      ) : null}
      {showSourceSection && (
        <>
          <div className="theme-settings-menu-divider" />
          <div className="theme-settings-menu-header">Source</div>
          <div className="theme-settings-menu-options">
            {supportsSourceColumnSetting && (
              <div className="theme-settings-menu-field">
                <span className="theme-settings-menu-option-label">Image column</span>
                <Dropdown
                  value={selectedSourceColumn}
                  onChange={(nextColumn) => onSourceColumnChange?.(nextColumn)}
                  options={sourceColumnOptions}
                  aria-label="Image column"
                  title={selectedSourceColumn || 'Image column'}
                  disabled={sourceColumnSwitching}
                  triggerClassName="theme-settings-menu-select theme-settings-menu-dropdown justify-between"
                  width="trigger"
                  searchable="auto"
                  searchPlaceholder="Search columns..."
                  emptyMessage="No matching columns"
                  portal={false}
                />
                {selectedSourceStatus && (
                  <span className="theme-settings-menu-option-subtitle">
                    {selectedSourceStatus.sample_usable} / {selectedSourceStatus.sample_total} sampled rows look image-like
                  </span>
                )}
              </div>
            )}
            {tableLaunchStatus && (
              <div className="theme-settings-menu-field">
                <span className="theme-settings-menu-option-label">Launch status</span>
                <span className="theme-settings-menu-option-subtitle">
                  {formatLaunchSummary(tableLaunchStatus)}
                </span>
                <span className="theme-settings-menu-option-subtitle">
                  {formatDimensionCoverage(tableLaunchStatus)}, cache: {tableLaunchStatus.dimension_cache_policy}, write: {tableLaunchStatus.dimension_write_policy}
                </span>
                <span className="theme-settings-menu-option-subtitle">
                  Media: {formatMediaPolicyMode(tableLaunchStatus.original_media_policy.mode)}
                  {tableLaunchStatus.original_media_policy.redacted_origin ? `, ${tableLaunchStatus.original_media_policy.redacted_origin}` : ''}
                </span>
                {sourceRefreshLabel && (
                  <span className="theme-settings-menu-option-subtitle">
                    {sourceRefreshLabel}
                  </span>
                )}
                {tableLaunchStatus.warnings.slice(0, 2).map((warning) => (
                  <span key={warning} className="theme-settings-menu-option-subtitle">{warning}</span>
                ))}
              </div>
            )}
          </div>
        </>
      )}
      {supportsInspectorAutoloadSetting && (
        <>
          <div className="theme-settings-menu-divider" />
          <div className="theme-settings-menu-header">Inspector</div>
          <div className="theme-settings-menu-options">
            <button
              type="button"
              className={`theme-settings-menu-option theme-settings-menu-option-toggle ${autoloadImageMetadata ? 'is-active' : ''}`}
              role="menuitemcheckbox"
              aria-checked={autoloadImageMetadata}
              onClick={() => onAutoloadImageMetadataChange?.(!autoloadImageMetadata)}
            >
              <span className="theme-settings-menu-option-label-group">
                <span className="theme-settings-menu-option-label">Autoload image metadata</span>
                <span className="theme-settings-menu-option-subtitle">Load PNG metadata when selecting an image</span>
              </span>
              <span
                className={`theme-settings-menu-toggle ${autoloadImageMetadata ? 'is-active' : ''}`}
                aria-hidden="true"
              >
                <span className="theme-settings-menu-toggle-knob" />
              </span>
            </button>
          </div>
        </>
      )}
      {supportsMediaSetting && (
        <>
          <div className="theme-settings-menu-divider" />
          <div className="theme-settings-menu-header">Media</div>
          <div className="theme-settings-menu-options">
            <button
              type="button"
              className={`theme-settings-menu-option theme-settings-menu-option-toggle ${proxyHttpOriginals ? 'is-active' : ''}`}
              role="menuitemcheckbox"
              aria-checked={proxyHttpOriginals}
              onClick={() => onProxyHttpOriginalsChange?.(!proxyHttpOriginals)}
            >
              <span className="theme-settings-menu-option-label-group">
                <span className="theme-settings-menu-option-label">Proxy HTTP originals</span>
                <span className="theme-settings-menu-option-subtitle">Off loads full-size HTTP images directly</span>
              </span>
              <span
                className={`theme-settings-menu-toggle ${proxyHttpOriginals ? 'is-active' : ''}`}
                aria-hidden="true"
              >
                <span className="theme-settings-menu-toggle-knob" />
              </span>
            </button>
          </div>
        </>
      )}
      {supportsCompareOrderSetting && (
        <>
          <div className="theme-settings-menu-divider" />
          <div className="theme-settings-menu-header">Compare</div>
          <div className="theme-settings-menu-options">
            <button
              type="button"
              className={`theme-settings-menu-option theme-settings-menu-option-toggle ${compareOrderMode === 'selection' ? 'is-active' : ''}`}
              role="menuitemcheckbox"
              aria-checked={compareOrderMode === 'selection'}
              onClick={() => {
                const nextMode: CompareOrderMode = compareOrderMode === 'selection' ? 'gallery' : 'selection'
                onCompareOrderModeChange?.(nextMode)
              }}
            >
              <span className="theme-settings-menu-option-label-group">
                <span className="theme-settings-menu-option-label">Order compare by selection</span>
                <span className="theme-settings-menu-option-subtitle">Off uses gallery sort order (default)</span>
              </span>
              <span
                className={`theme-settings-menu-toggle ${compareOrderMode === 'selection' ? 'is-active' : ''}`}
                aria-hidden="true"
              >
                <span className="theme-settings-menu-toggle-knob" />
              </span>
            </button>
          </div>
        </>
      )}
    </div>
  ) : null

  return (
    <div ref={rootRef} className="theme-settings-menu-root relative">
      <button
        type="button"
        className={getTriggerClassName(placement)}
        aria-label={triggerTitle}
        title={triggerTitle}
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen((current) => reduceThemeSettingsMenuOpenState(current, 'toggle'))}
      >
        {placement === 'sidebar' ? (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M10.5 2h3l.6 2.1a7.8 7.8 0 0 1 1.8.8l2-1 2.1 2.1-1 2a7.8 7.8 0 0 1 .8 1.8L22 10.5v3l-2.1.6a7.8 7.8 0 0 1-.8 1.8l1 2-2.1 2.1-2-1a7.8 7.8 0 0 1-1.8.8L13.5 22h-3l-.6-2.1a7.8 7.8 0 0 1-1.8-.8l-2 1L4 18l1-2a7.8 7.8 0 0 1-.8-1.8L2 13.5v-3l2.1-.6a7.8 7.8 0 0 1 .8-1.8l-1-2L6 4l2 1a7.8 7.8 0 0 1 1.8-.8z" />
            <circle cx="12" cy="12" r="3.1" />
          </svg>
        ) : (
          <>
            <span
              className="theme-settings-trigger-swatch"
              style={{ backgroundColor: selectedTheme.tokens['--accent'] }}
              aria-hidden="true"
            />
            <span>Settings</span>
          </>
        )}
      </button>
      {panelNode && typeof document !== 'undefined'
        ? createPortal(panelNode, document.body)
        : panelNode}
    </div>
  )
}

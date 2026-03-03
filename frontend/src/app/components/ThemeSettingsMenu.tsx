import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { THEME_PRESETS, resolveThemePresetId, type ThemePresetId } from '../../theme/runtime'

export type ThemeSettingsMenuPlacement = 'sidebar' | 'mobile'
export type ThemeSettingsMenuCloseIntent = 'toggle' | 'close' | 'escape' | 'outside_click' | 'select'

type ThemeSettingsMenuProps = {
  value: ThemePresetId
  onChange: (themeId: ThemePresetId) => void
  placement: ThemeSettingsMenuPlacement
  autoloadImageMetadata?: boolean
  onAutoloadImageMetadataChange?: (enabled: boolean) => void
}

type ThemeMenuOption = {
  id: ThemePresetId
  label: string
  accent: string
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

type ViewportLike = {
  width: number
  height: number
}

type ThemeMenuPanelLayout = {
  placement: ThemeSettingsMenuPlacement
  anchorRect: RectLike
  panelSize: SizeLike
  viewport: ViewportLike
}

type ThemeMenuPanelPosition = {
  x: number
  y: number
  ready: boolean
}

const THEME_OPTIONS: readonly ThemeMenuOption[] = (['default', 'teal', 'charcoal'] as const).map((id) => ({
  id,
  label: THEME_PRESETS[id].label,
  accent: THEME_PRESETS[id].tokens['--accent'],
}))
const VIEWPORT_PADDING = 8
const SIDEBAR_PANEL_GAP = 10
const MOBILE_PANEL_GAP = 8

function clamp(value: number, min: number, max: number): number {
  if (max < min) return min
  return Math.min(max, Math.max(min, value))
}

function getInitialPanelPosition(): ThemeMenuPanelPosition {
  return { x: 0, y: 0, ready: false }
}

export function getThemeMenuPanelPosition({
  placement,
  anchorRect,
  panelSize,
  viewport,
}: ThemeMenuPanelLayout): { x: number; y: number } {
  const maxX = viewport.width - panelSize.width - VIEWPORT_PADDING
  const maxY = viewport.height - panelSize.height - VIEWPORT_PADDING

  if (placement === 'sidebar') {
    return {
      x: clamp(anchorRect.right + SIDEBAR_PANEL_GAP, VIEWPORT_PADDING, maxX),
      y: clamp(anchorRect.bottom - panelSize.height, VIEWPORT_PADDING, maxY),
    }
  }

  return {
    x: clamp(anchorRect.left, VIEWPORT_PADDING, maxX),
    y: clamp(anchorRect.top - panelSize.height - MOBILE_PANEL_GAP, VIEWPORT_PADDING, maxY),
  }
}

export function resolveThemeMenuSelection(value: string | null | undefined): ThemePresetId {
  return resolveThemePresetId(value)
}

export function reduceThemeSettingsMenuOpenState(open: boolean, intent: ThemeSettingsMenuCloseIntent): boolean {
  if (intent === 'toggle') return !open
  return false
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
  autoloadImageMetadata = false,
  onAutoloadImageMetadataChange,
}: ThemeSettingsMenuProps): JSX.Element {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const [panelPosition, setPanelPosition] = useState<ThemeMenuPanelPosition>(getInitialPanelPosition)
  const selectedThemeId = resolveThemeMenuSelection(value)
  const selectedTheme = THEME_PRESETS[selectedThemeId]
  const supportsInspectorAutoloadSetting = typeof onAutoloadImageMetadataChange === 'function'
  const updatePanelPosition = useCallback(() => {
    if (!open || typeof window === 'undefined') return
    const rootElement = rootRef.current
    const panelElement = panelRef.current
    if (!rootElement || !panelElement) return

    const anchorRect = rootElement.getBoundingClientRect()
    const panelRect = panelElement.getBoundingClientRect()
    const next = getThemeMenuPanelPosition({
      placement,
      anchorRect,
      panelSize: { width: panelRect.width, height: panelRect.height },
      viewport: { width: window.innerWidth, height: window.innerHeight },
    })

    setPanelPosition((prev) => (
      prev.ready && prev.x === next.x && prev.y === next.y
        ? prev
        : { x: next.x, y: next.y, ready: true }
    ))
  }, [open, placement])

  useEffect(() => {
    if (!open) {
      setPanelPosition(getInitialPanelPosition())
      return
    }

    const onWindowViewportChange = () => updatePanelPosition()

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

    updatePanelPosition()
    const rafHandle = typeof window !== 'undefined'
      ? window.requestAnimationFrame(() => updatePanelPosition())
      : null

    window.addEventListener('click', onWindowClick)
    window.addEventListener('keydown', onWindowKeyDown)
    window.addEventListener('resize', onWindowViewportChange)
    window.addEventListener('scroll', onWindowViewportChange, true)
    return () => {
      window.removeEventListener('click', onWindowClick)
      window.removeEventListener('keydown', onWindowKeyDown)
      window.removeEventListener('resize', onWindowViewportChange)
      window.removeEventListener('scroll', onWindowViewportChange, true)
      if (rafHandle != null) {
        window.cancelAnimationFrame(rafHandle)
      }
    }
  }, [open, updatePanelPosition])

  const triggerTitle = `Theme settings (${selectedTheme.label})`

  const panelStyle = {
    position: 'fixed' as const,
    left: panelPosition.x,
    top: panelPosition.y,
    visibility: panelPosition.ready ? ('visible' as const) : ('hidden' as const),
  }

  const panelNode = open ? (
    <div
      ref={panelRef}
      className="theme-settings-menu-panel"
      role="menu"
      aria-label="Theme settings"
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
            <span>Theme</span>
          </>
        )}
      </button>
      {panelNode && typeof document !== 'undefined'
        ? createPortal(panelNode, document.body)
        : panelNode}
    </div>
  )
}

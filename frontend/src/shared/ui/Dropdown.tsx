import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { getDropdownPanelPosition, getViewportSize } from '../../lib/menuPosition'

export interface DropdownOption {
  value: string
  label: string
  icon?: React.ReactNode
  disabled?: boolean
}

export interface DropdownGroup {
  label?: string
  options: DropdownOption[]
}

export interface DropdownProps {
  /** Currently selected value */
  value: string
  /** Called when selection changes */
  onChange: (value: string) => void
  /** Options - can be flat array or grouped */
  options: DropdownOption[] | DropdownGroup[]
  /** Placeholder when no value selected */
  placeholder?: string
  /** Custom trigger element (overrides default button) */
  trigger?: React.ReactNode
  /** Additional class for trigger button */
  triggerClassName?: string
  /** Additional class for dropdown panel */
  panelClassName?: string
  /** Alignment of dropdown panel */
  align?: 'left' | 'right'
  /** Width of dropdown panel */
  width?: number | 'trigger' | 'auto'
  /** Show chevron indicator */
  showChevron?: boolean
  /** Tooltip for trigger */
  title?: string
  /** Disabled state */
  disabled?: boolean
  /** aria-label for accessibility */
  'aria-label'?: string
}

function isGrouped(options: DropdownOption[] | DropdownGroup[]): options is DropdownGroup[] {
  return options.length > 0 && 'options' in options[0]
}

interface FloatingPanelPosition {
  x: number
  y: number
  ready: boolean
}

const NOOP_ON_OPEN_CHANGE = (_open: boolean) => {}

function getInitialPosition(): FloatingPanelPosition {
  return { x: 0, y: 0, ready: false }
}

export default function Dropdown({
  value,
  onChange,
  options,
  placeholder = 'Select...',
  trigger,
  triggerClassName = '',
  panelClassName = '',
  align = 'left',
  width = 'auto',
  showChevron = true,
  title,
  disabled = false,
  'aria-label': ariaLabel,
}: DropdownProps) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const [panelPosition, setPanelPosition] = useState<FloatingPanelPosition>(getInitialPosition)

  const findLabel = useCallback((): string => {
    const search = (opts: DropdownOption[]): string | null => {
      const found = opts.find((o) => o.value === value)
      return found ? found.label : null
    }

    if (isGrouped(options)) {
      for (const group of options) {
        const label = search(group.options)
        if (label) return label
      }
    } else {
      const label = search(options)
      if (label) return label
    }
    return placeholder
  }, [value, options, placeholder])

  const selectedLabel = findLabel()

  const triggerWidth = containerRef.current?.getBoundingClientRect().width
    ?? triggerRef.current?.offsetWidth
    ?? 0
  const forcedPanelWidth = width === 'trigger'
    ? triggerWidth
    : width === 'auto'
      ? undefined
      : width

  const updatePanelPosition = useCallback(() => {
    if (!open) return
    const anchor = containerRef.current
    const panel = panelRef.current
    if (!anchor || !panel) return

    const anchorRect = anchor.getBoundingClientRect()
    const panelRect = panel.getBoundingClientRect()
    const panelWidth = forcedPanelWidth ?? panelRect.width ?? 180
    const panelHeight = panelRect.height || panel.scrollHeight || 1
    const next = getDropdownPanelPosition({
      anchorRect,
      menuSize: { width: panelWidth, height: panelHeight },
      viewport: getViewportSize(),
      align,
    })

    setPanelPosition((prev) => (
      prev.x === next.x && prev.y === next.y && prev.ready
        ? prev
        : { x: next.x, y: next.y, ready: true }
    ))
  }, [align, forcedPanelWidth, open])

  useLayoutEffect(() => {
    if (!open) {
      setPanelPosition(getInitialPosition())
      return
    }
    updatePanelPosition()
  }, [open, updatePanelPosition, options, value])

  useEffect(() => {
    if (!open) return

    const onClick = (e: MouseEvent) => {
      const target = e.target as Node
      if (containerRef.current?.contains(target)) return
      if (panelRef.current?.contains(target)) return
      setOpen(false)
    }

    const onEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false)
        triggerRef.current?.focus()
      }
    }

    const onViewportChange = () => updatePanelPosition()

    window.addEventListener('click', onClick)
    window.addEventListener('keydown', onEscape)
    window.addEventListener('resize', onViewportChange)
    window.addEventListener('scroll', onViewportChange, true)

    return () => {
      window.removeEventListener('click', onClick)
      window.removeEventListener('keydown', onEscape)
      window.removeEventListener('resize', onViewportChange)
      window.removeEventListener('scroll', onViewportChange, true)
    }
  }, [open, updatePanelPosition])

  const handleSelect = (optValue: string) => {
    onChange(optValue)
    setOpen(false)
    triggerRef.current?.focus()
  }

  const renderOptions = (opts: DropdownOption[]) => {
    return opts.map((opt) => (
      <button
        key={opt.value}
        className="dropdown-item"
        data-active={opt.value === value}
        disabled={opt.disabled}
        onClick={() => !opt.disabled && handleSelect(opt.value)}
        role="menuitem"
      >
        {opt.icon && <span className="shrink-0">{opt.icon}</span>}
        <span className="flex-1 truncate">{opt.label}</span>
        {opt.value === value && (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="shrink-0 text-accent">
            <polyline points="20 6 9 17 4 12" />
          </svg>
        )}
      </button>
    ))
  }

  const panelStyle: React.CSSProperties = useMemo(() => ({
    position: 'fixed',
    left: panelPosition.x,
    top: panelPosition.y,
    visibility: panelPosition.ready ? 'visible' : 'hidden',
    ...(forcedPanelWidth ? { width: forcedPanelWidth, minWidth: forcedPanelWidth } : {}),
  }), [forcedPanelWidth, panelPosition])

  const panelNode = open ? (
    <div
      ref={panelRef}
      className={`dropdown-panel ${panelClassName}`}
      style={panelStyle}
      role="listbox"
      aria-label={ariaLabel}
    >
      {isGrouped(options) ? (
        options.map((group, idx) => (
          <div key={group.label || idx}>
            {group.label && <div className="dropdown-label">{group.label}</div>}
            {renderOptions(group.options)}
            {idx < options.length - 1 && <div className="dropdown-divider" />}
          </div>
        ))
      ) : (
        renderOptions(options)
      )}
    </div>
  ) : null

  return (
    <div ref={containerRef} className="relative">
      {trigger ? (
        <div onClick={() => !disabled && setOpen((o) => !o)}>{trigger}</div>
      ) : (
        <button
          ref={triggerRef}
          type="button"
          className={`dropdown-trigger ${triggerClassName}`}
          onClick={() => setOpen((o) => !o)}
          disabled={disabled}
          title={title}
          aria-label={ariaLabel}
          aria-haspopup="listbox"
          aria-expanded={open}
        >
          <span className="truncate">{selectedLabel}</span>
          {showChevron && (
            <svg
              width="10"
              height="10"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className={`shrink-0 opacity-60 transition-transform ${open ? 'rotate-180' : ''}`}
            >
              <polyline points="6 9 12 15 18 9" />
            </svg>
          )}
        </button>
      )}

      {panelNode && typeof document !== 'undefined'
        ? createPortal(panelNode, document.body)
        : panelNode}
    </div>
  )
}

/**
 * Simple icon button that opens a dropdown panel with custom content.
 */
export interface DropdownMenuProps {
  /** Trigger element */
  trigger: React.ReactNode
  /** Panel content */
  children: React.ReactNode
  /** Open state (controlled) */
  open?: boolean
  /** Called when open state changes */
  onOpenChange?: (open: boolean) => void
  /** Panel class name */
  panelClassName?: string
  /** Alignment */
  align?: 'left' | 'right'
  /** Width */
  width?: number
}

export function DropdownMenu({
  trigger,
  children,
  open: controlledOpen,
  onOpenChange,
  panelClassName = '',
  align = 'left',
  width,
}: DropdownMenuProps) {
  const [internalOpen, setInternalOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const [panelPosition, setPanelPosition] = useState<FloatingPanelPosition>(getInitialPosition)

  const isControlled = controlledOpen !== undefined
  const open = isControlled ? controlledOpen : internalOpen
  const setOpen = isControlled ? (onOpenChange ?? NOOP_ON_OPEN_CHANGE) : setInternalOpen

  const updatePanelPosition = useCallback(() => {
    if (!open) return
    const anchor = containerRef.current
    const panel = panelRef.current
    if (!anchor || !panel) return

    const anchorRect = anchor.getBoundingClientRect()
    const panelRect = panel.getBoundingClientRect()
    const panelWidth = width ?? panelRect.width ?? 180
    const panelHeight = panelRect.height || panel.scrollHeight || 1
    const next = getDropdownPanelPosition({
      anchorRect,
      menuSize: { width: panelWidth, height: panelHeight },
      viewport: getViewportSize(),
      align,
    })

    setPanelPosition((prev) => (
      prev.x === next.x && prev.y === next.y && prev.ready
        ? prev
        : { x: next.x, y: next.y, ready: true }
    ))
  }, [align, open, width])

  useLayoutEffect(() => {
    if (!open) {
      setPanelPosition(getInitialPosition())
      return
    }
    updatePanelPosition()
  }, [open, updatePanelPosition])

  useEffect(() => {
    if (!open) return

    const onClick = (e: MouseEvent) => {
      const target = e.target as Node
      if (containerRef.current?.contains(target)) return
      if (panelRef.current?.contains(target)) return
      setOpen(false)
    }

    const onEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false)
      }
    }

    const onViewportChange = () => updatePanelPosition()

    window.addEventListener('click', onClick)
    window.addEventListener('keydown', onEscape)
    window.addEventListener('resize', onViewportChange)
    window.addEventListener('scroll', onViewportChange, true)

    return () => {
      window.removeEventListener('click', onClick)
      window.removeEventListener('keydown', onEscape)
      window.removeEventListener('resize', onViewportChange)
      window.removeEventListener('scroll', onViewportChange, true)
    }
  }, [open, setOpen, updatePanelPosition])

  const panelStyle: React.CSSProperties = {
    position: 'fixed',
    left: panelPosition.x,
    top: panelPosition.y,
    visibility: panelPosition.ready ? 'visible' : 'hidden',
    ...(width ? { width, minWidth: width } : {}),
  }

  const panelNode = open ? (
    <div ref={panelRef} className={`dropdown-panel ${panelClassName}`} style={panelStyle}>
      {children}
    </div>
  ) : null

  return (
    <div ref={containerRef} className="relative">
      <div onClick={() => setOpen(!open)}>{trigger}</div>
      {panelNode && typeof document !== 'undefined'
        ? createPortal(panelNode, document.body)
        : panelNode}
    </div>
  )
}

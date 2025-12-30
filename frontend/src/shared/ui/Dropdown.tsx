import React, { useEffect, useLayoutEffect, useRef, useState, useCallback } from 'react'
import { createPortal } from 'react-dom'

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

  // Find selected option label
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

  // Close on click outside
  useEffect(() => {
    if (!open) return

    const onClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }

    const onEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false)
        triggerRef.current?.focus()
      }
    }

    window.addEventListener('click', onClick)
    window.addEventListener('keydown', onEscape)

    return () => {
      window.removeEventListener('click', onClick)
      window.removeEventListener('keydown', onEscape)
    }
  }, [open])

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

  const triggerWidth = triggerRef.current?.offsetWidth ?? 0
  const panelWidth = width === 'trigger' ? triggerWidth : width === 'auto' ? undefined : width
  const panelStyle: React.CSSProperties = {
    ...(panelWidth ? { width: panelWidth, minWidth: panelWidth } : {}),
    ...(align === 'right' ? { right: 0 } : { left: 0 }),
  }

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

      {open && (
        <div
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
      )}
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
  const triggerRef = useRef<HTMLDivElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const [panelStyle, setPanelStyle] = useState<React.CSSProperties>({
    position: 'fixed',
    top: 0,
    left: 0,
  })

  const isControlled = controlledOpen !== undefined
  const open = isControlled ? controlledOpen : internalOpen
  const setOpen = isControlled ? (onOpenChange ?? (() => {})) : setInternalOpen

  // Close on click outside
  useEffect(() => {
    if (!open) return

    const onClick = (e: MouseEvent) => {
      const target = e.target as Node
      if (containerRef.current?.contains(target)) return
      if (panelRef.current?.contains(target)) return
      if (containerRef.current && !containerRef.current.contains(target)) {
        setOpen(false)
      }
    }

    const onEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false)
      }
    }

    window.addEventListener('click', onClick)
    window.addEventListener('keydown', onEscape)

    return () => {
      window.removeEventListener('click', onClick)
      window.removeEventListener('keydown', onEscape)
    }
  }, [open, setOpen])

  const updatePanelPosition = useCallback(() => {
    const triggerEl = triggerRef.current
    if (!triggerEl) return

    const rect = triggerEl.getBoundingClientRect()
    const gap = 6
    const panelWidth = width ?? panelRef.current?.offsetWidth ?? rect.width
    const panelHeight = panelRef.current?.offsetHeight ?? 0

    let top = rect.bottom + gap
    let left: number | undefined
    let right: number | undefined

    if (align === 'right') {
      right = Math.max(8, window.innerWidth - rect.right)
    } else {
      left = rect.left
    }

    if (align === 'left') {
      const maxLeft = Math.max(8, window.innerWidth - panelWidth - 8)
      left = Math.min(Math.max(8, left ?? 8), maxLeft)
    } else if (align === 'right') {
      const maxRight = Math.max(8, window.innerWidth - panelWidth - 8)
      right = Math.min(Math.max(8, right ?? 8), maxRight)
    }

    if (panelHeight && top + panelHeight > window.innerHeight - 8) {
      const above = rect.top - gap - panelHeight
      if (above >= 8) {
        top = above
      } else {
        top = Math.max(8, window.innerHeight - panelHeight - 8)
      }
    }

    setPanelStyle({
      position: 'fixed',
      top,
      ...(left !== undefined ? { left } : {}),
      ...(right !== undefined ? { right } : {}),
      ...(width ? { width, minWidth: width } : {}),
    })
  }, [align, width])

  useLayoutEffect(() => {
    if (!open) return
    updatePanelPosition()
  }, [open, updatePanelPosition])

  useEffect(() => {
    if (!open) return
    const handle = () => updatePanelPosition()
    window.addEventListener('resize', handle)
    window.addEventListener('scroll', handle, true)
    return () => {
      window.removeEventListener('resize', handle)
      window.removeEventListener('scroll', handle, true)
    }
  }, [open, updatePanelPosition])

  return (
    <div ref={containerRef} className="relative">
      <div ref={triggerRef} onClick={() => setOpen(!open)}>{trigger}</div>
      {open && createPortal(
        <div ref={panelRef} className={`dropdown-panel ${panelClassName}`} style={panelStyle}>
          {children}
        </div>,
        document.body,
      )}
    </div>
  )
}

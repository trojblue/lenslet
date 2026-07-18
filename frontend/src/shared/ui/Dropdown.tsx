import React, { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  getDropdownPanelPosition,
  getVisibleViewportBounds,
  subscribeVisibleViewportChanges,
} from '../../lib/menuPosition'
import {
  filterDropdownOptions,
  findEnabledOption,
  findFirstEnabledOption,
  findNextEnabledOption,
  flattenDropdownOptions,
  isDropdownGrouped,
} from './dropdownSearch'

export interface DropdownOption {
  value: string
  label: string
  keywords?: string[]
  icon?: React.ReactNode
  disabled?: boolean
}

export interface DropdownGroup {
  label?: string
  options: DropdownOption[]
}

export interface DropdownProps {
  value: string
  onChange: (value: string) => void
  options: DropdownOption[] | DropdownGroup[]
  placeholder?: string
  trigger?: React.ReactNode
  triggerClassName?: string
  panelClassName?: string
  align?: 'left' | 'right'
  width?: number | 'trigger' | 'auto'
  showChevron?: boolean
  title?: string
  disabled?: boolean
  searchable?: boolean | 'auto'
  searchThreshold?: number
  searchPlaceholder?: string
  emptyMessage?: string
  editable?: boolean
  portal?: boolean
  'aria-label'?: string
}

interface FloatingPanelPosition {
  x: number
  y: number
  ready: boolean
}

const NOOP_ON_OPEN_CHANGE = (_open: boolean) => {}
const DEFAULT_SEARCH_THRESHOLD = 12
const useIsomorphicLayoutEffect = typeof window === 'undefined' ? useEffect : useLayoutEffect

export function getDropdownPanelClassName(
  panelClassName = '',
  searchable = false,
): string {
  return `dropdown-panel scrollbar-thin ${searchable ? 'dropdown-panel-searchable' : ''} ${panelClassName}`
}

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
  searchable = false,
  searchThreshold = DEFAULT_SEARCH_THRESHOLD,
  searchPlaceholder = 'Search options...',
  emptyMessage = 'No matching options',
  editable = false,
  portal = true,
  'aria-label': ariaLabel,
}: DropdownProps) {
  const listboxId = useId()
  const [open, setOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [highlightedValue, setHighlightedValue] = useState<string | null>(null)
  const [keyboardNavigated, setKeyboardNavigated] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const editableInputRef = useRef<HTMLInputElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const searchInputRef = useRef<HTMLInputElement>(null)
  const itemRefs = useRef<Map<string, HTMLButtonElement>>(new Map())
  const [panelPosition, setPanelPosition] = useState<FloatingPanelPosition>(getInitialPosition)

  const flatOptions = useMemo(() => flattenDropdownOptions(options), [options])
  const selectedLabel = flatOptions.find((option) => option.value === value)?.label ?? (value || placeholder)
  const effectiveSearchable = editable || searchable === true || (
    searchable === 'auto' && flatOptions.length >= searchThreshold
  )
  const filteredOptions = useMemo(() => (
    effectiveSearchable
      ? filterDropdownOptions(options, searchQuery)
      : { options, totalCount: flatOptions.length, matchCount: flatOptions.length }
  ), [effectiveSearchable, flatOptions.length, options, searchQuery])
  const visibleFlatOptions = useMemo(
    () => flattenDropdownOptions(filteredOptions.options),
    [filteredOptions.options],
  )
  const optionIds = useMemo(() => new Map(
    flatOptions.map((option, index) => [option.value, `${listboxId}-option-${index}`]),
  ), [flatOptions, listboxId])

  const triggerWidth = containerRef.current?.getBoundingClientRect().width
    ?? triggerRef.current?.offsetWidth
    ?? editableInputRef.current?.offsetWidth
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
      viewport: getVisibleViewportBounds(),
      align,
    })

    setPanelPosition((prev) => (
      prev.x === next.x && prev.y === next.y && prev.ready
        ? prev
        : { x: next.x, y: next.y, ready: true }
    ))
  }, [align, forcedPanelWidth, open])

  const closeDropdown = useCallback((focusTrigger = false) => {
    setOpen(false)
    if (focusTrigger) {
      window.requestAnimationFrame(() => (editableInputRef.current ?? triggerRef.current)?.focus())
    }
  }, [])

  const openDropdown = useCallback((seedQuery?: string) => {
    if (disabled) return
    if (seedQuery !== undefined) setSearchQuery(seedQuery)
    setOpen(true)
  }, [disabled])

  useIsomorphicLayoutEffect(() => {
    if (!open) {
      setPanelPosition(getInitialPosition())
      return
    }
    updatePanelPosition()
  }, [filteredOptions.options, open, updatePanelPosition, value])

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
        closeDropdown(true)
      }
    }

    const onViewportChange = () => updatePanelPosition()
    const unsubscribeViewport = subscribeVisibleViewportChanges(onViewportChange)

    window.addEventListener('click', onClick)
    window.addEventListener('keydown', onEscape)

    return () => {
      window.removeEventListener('click', onClick)
      window.removeEventListener('keydown', onEscape)
      unsubscribeViewport()
    }
  }, [closeDropdown, open, updatePanelPosition])

  useEffect(() => {
    if (open) return
    itemRefs.current.clear()
    setSearchQuery('')
    setHighlightedValue(null)
    setKeyboardNavigated(false)
  }, [open])

  useEffect(() => {
    if (!open) return
    setHighlightedValue((current) => {
      if (findEnabledOption(filteredOptions.options, current)) return current
      return (
        findEnabledOption(filteredOptions.options, value)
        ?? findFirstEnabledOption(filteredOptions.options)
      )?.value ?? null
    })
  }, [filteredOptions.options, open, value])

  useEffect(() => {
    if (!open || !effectiveSearchable || editable) return
    const handle = window.requestAnimationFrame(() => searchInputRef.current?.focus())
    return () => window.cancelAnimationFrame(handle)
  }, [editable, effectiveSearchable, open])

  useEffect(() => {
    if (!open || !highlightedValue) return
    itemRefs.current.get(highlightedValue)?.scrollIntoView({ block: 'nearest' })
  }, [highlightedValue, open])

  const handleSelect = useCallback((optValue: string) => {
    onChange(optValue)
    closeDropdown(!editable)
  }, [closeDropdown, editable, onChange])

  const moveHighlight = useCallback((direction: 1 | -1) => {
    setKeyboardNavigated(true)
    setHighlightedValue((current) => (
      findNextEnabledOption(filteredOptions.options, current, direction)?.value ?? current
    ))
  }, [filteredOptions.options])

  const selectHighlighted = useCallback(() => {
    const highlighted = findEnabledOption(filteredOptions.options, highlightedValue)
    if (!highlighted) return
    handleSelect(highlighted.value)
  }, [filteredOptions.options, handleSelect, highlightedValue])

  const handlePanelKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      moveHighlight(1)
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      moveHighlight(-1)
    } else if (event.key === 'Home') {
      event.preventDefault()
      setHighlightedValue(findFirstEnabledOption(filteredOptions.options)?.value ?? null)
    } else if (event.key === 'End') {
      event.preventDefault()
      setHighlightedValue(findNextEnabledOption(filteredOptions.options, null, -1)?.value ?? null)
    } else if (event.key === 'Enter') {
      event.preventDefault()
      selectHighlighted()
    } else if (event.key === 'Escape') {
      event.preventDefault()
      closeDropdown(true)
    }
  }

  const handleTriggerKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    if (disabled) return
    if (open && event.key === 'Enter') {
      event.preventDefault()
      selectHighlighted()
    } else if (open && event.key === 'Escape') {
      event.preventDefault()
      closeDropdown(true)
    } else if (open && event.key === 'Home') {
      event.preventDefault()
      setHighlightedValue(findFirstEnabledOption(filteredOptions.options)?.value ?? null)
    } else if (open && event.key === 'End') {
      event.preventDefault()
      setHighlightedValue(findNextEnabledOption(filteredOptions.options, null, -1)?.value ?? null)
    } else if (event.key === 'ArrowDown') {
      event.preventDefault()
      openDropdown()
      moveHighlight(1)
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      openDropdown()
      moveHighlight(-1)
    } else if (effectiveSearchable && isPrintableKey(event)) {
      event.preventDefault()
      openDropdown(event.key)
    }
  }

  const handleEditableKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (disabled) return
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      if (!open) openDropdown(searchQuery)
      moveHighlight(1)
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      if (!open) openDropdown(searchQuery)
      moveHighlight(-1)
    } else if (event.key === 'Enter' && open) {
      event.preventDefault()
      if (keyboardNavigated) selectHighlighted()
      else closeDropdown()
    } else if (event.key === 'Escape' && open) {
      event.preventDefault()
      closeDropdown()
    }
  }

  const setItemRef = (optValue: string, node: HTMLButtonElement | null) => {
    if (node) {
      itemRefs.current.set(optValue, node)
    } else {
      itemRefs.current.delete(optValue)
    }
  }

  const renderOptions = (opts: DropdownOption[]) => {
    return opts.map((opt) => (
      <button
        key={opt.value}
        id={optionIds.get(opt.value)}
        ref={(node) => setItemRef(opt.value, node)}
        className="dropdown-item"
        data-active={opt.value === value}
        data-highlighted={opt.value === highlightedValue}
        disabled={opt.disabled}
        onClick={() => !opt.disabled && handleSelect(opt.value)}
        onMouseDown={(event) => {
          if (editable) event.preventDefault()
        }}
        onMouseEnter={() => !opt.disabled && setHighlightedValue(opt.value)}
        role="option"
        aria-selected={opt.value === value}
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
      className={getDropdownPanelClassName(panelClassName, effectiveSearchable && !editable)}
      style={panelStyle}
      role="listbox"
      aria-label={ariaLabel}
      id={listboxId}
      onKeyDown={handlePanelKeyDown}
    >
      {effectiveSearchable && !editable && (
        <div className="dropdown-search-wrap">
          <input
            ref={searchInputRef}
            className="dropdown-search-input"
            value={searchQuery}
            role="searchbox"
            aria-label={`Search ${ariaLabel ?? 'options'}`}
            placeholder={searchPlaceholder}
            autoComplete="off"
            spellCheck={false}
            onChange={(event) => setSearchQuery(event.currentTarget.value)}
          />
        </div>
      )}
      {visibleFlatOptions.length ? (
        isDropdownGrouped(filteredOptions.options) ? (
          filteredOptions.options.map((group, idx) => (
            <div key={group.label || idx}>
              {group.label && <div className="dropdown-label">{group.label}</div>}
              {renderOptions(group.options)}
              {idx < filteredOptions.options.length - 1 && <div className="dropdown-divider" />}
            </div>
          ))
        ) : (
          renderOptions(filteredOptions.options)
        )
      ) : (
        <div className="dropdown-empty">{emptyMessage}</div>
      )}
      {effectiveSearchable && searchQuery.trim() && filteredOptions.matchCount > 0 && filteredOptions.matchCount < filteredOptions.totalCount && (
        <div className="dropdown-results-note">
          {filteredOptions.matchCount} / {filteredOptions.totalCount}
        </div>
      )}
    </div>
  ) : null

  return (
    <div ref={containerRef} className="relative">
      {trigger ? (
        <div onClick={() => !disabled && setOpen((o) => !o)}>{trigger}</div>
      ) : editable ? (
        <input
          ref={editableInputRef}
          type="text"
          className={`dropdown-trigger ${triggerClassName}`}
          value={value}
          placeholder={placeholder}
          disabled={disabled}
          title={title}
          role="combobox"
          aria-label={ariaLabel}
          aria-autocomplete="list"
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-controls={open ? listboxId : undefined}
          aria-activedescendant={open && highlightedValue
            ? optionIds.get(highlightedValue)
            : undefined}
          autoComplete="off"
          spellCheck={false}
          onFocus={() => openDropdown('')}
          onClick={() => {
            if (!open) openDropdown('')
          }}
          onChange={(event) => {
            const nextValue = event.currentTarget.value
            onChange(nextValue)
            setSearchQuery(nextValue)
            setKeyboardNavigated(false)
            if (!open) openDropdown(nextValue)
          }}
          onKeyDown={handleEditableKeyDown}
        />
      ) : (
        <button
          ref={triggerRef}
          type="button"
          className={`dropdown-trigger ${triggerClassName}`}
          onClick={() => setOpen((o) => !o)}
          onKeyDown={handleTriggerKeyDown}
          disabled={disabled}
          title={title}
          aria-label={ariaLabel}
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-controls={open ? listboxId : undefined}
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

      {panelNode && typeof document !== 'undefined' && portal
        ? createPortal(panelNode, document.body)
        : panelNode}
    </div>
  )
}

function isPrintableKey(event: React.KeyboardEvent): boolean {
  return event.key.length === 1 && !event.altKey && !event.ctrlKey && !event.metaKey
}

export interface DropdownMenuProps {
  trigger: React.ReactNode
  children: React.ReactNode
  open?: boolean
  onOpenChange?: (open: boolean) => void
  panelClassName?: string
  align?: 'left' | 'right'
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
      viewport: getVisibleViewportBounds(),
      align,
    })

    setPanelPosition((prev) => (
      prev.x === next.x && prev.y === next.y && prev.ready
        ? prev
        : { x: next.x, y: next.y, ready: true }
    ))
  }, [align, open, width])

  useIsomorphicLayoutEffect(() => {
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
    const unsubscribeViewport = subscribeVisibleViewportChanges(onViewportChange)

    window.addEventListener('click', onClick)
    window.addEventListener('keydown', onEscape)

    return () => {
      window.removeEventListener('click', onClick)
      window.removeEventListener('keydown', onEscape)
      unsubscribeViewport()
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
    <div ref={panelRef} className={getDropdownPanelClassName(panelClassName)} style={panelStyle} role="menu">
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

import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import {
  clampMenuPosition,
  getVisibleViewportBounds,
  MENU_VIEWPORT_MARGIN_PX,
  subscribeVisibleViewportChanges,
} from '../../lib/menuPosition'

export interface MenuItem {
  label: string
  icon?: React.ReactNode
  danger?: boolean
  disabled?: boolean
  onClick: () => void
}

interface ContextMenuProps {
  x: number
  y: number
  items: MenuItem[]
}

export default function ContextMenu({ x, y, items }: ContextMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null)
  const [position, setPosition] = useState<{ x: number; y: number; width?: number }>({ x, y })
  const [ready, setReady] = useState(false)
  const handleItemClick = useCallback((item: MenuItem, event: React.MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation()
    if (!item.disabled) item.onClick()
  }, [])

  const updatePosition = useCallback(() => {
    const menuEl = menuRef.current
    const viewport = getVisibleViewportBounds()
    const rect = menuEl?.getBoundingClientRect()
    const menuWidth = Math.min(
      280,
      Math.max(0, viewport.width - (2 * MENU_VIEWPORT_MARGIN_PX)),
    )
    const menuHeight = rect?.height ?? Math.max(40, items.length * 36)
    const next = clampMenuPosition({
      x,
      y,
      menuWidth,
      menuHeight,
      viewport,
    })
    setPosition((prev) => (
      prev.x === next.x && prev.y === next.y && prev.width === menuWidth
        ? prev
        : { ...next, width: menuWidth }
    ))
    setReady(true)
  }, [items.length, x, y])

  useLayoutEffect(() => {
    updatePosition()
  }, [updatePosition])

  useEffect(() => {
    return subscribeVisibleViewportChanges(updatePosition)
  }, [updatePosition])

  return (
    <div
      ref={menuRef}
      className="dropdown-panel context-menu-panel fixed"
      role="menu"
      style={{
        left: position.x,
        top: position.y,
        width: position.width,
        visibility: ready ? 'visible' : 'hidden',
      }}
      onClick={(e) => e.stopPropagation()}
    >
      {items.map((item, idx) => (
        <button
          key={idx}
          className={`dropdown-item w-full ${item.danger ? 'text-danger hover:text-danger' : ''}`}
          role="menuitem"
          aria-disabled={item.disabled}
          disabled={item.disabled}
          onClick={(e) => handleItemClick(item, e)}
        >
          {item.icon && <span className="shrink-0">{item.icon}</span>}
          <span className="context-menu-label" title={item.label}>{item.label}</span>
        </button>
      ))}
    </div>
  )
}

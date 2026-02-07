import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { clampMenuPosition, getViewportSize } from '../../lib/menuPosition'

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
  const [position, setPosition] = useState({ x, y })
  const [ready, setReady] = useState(false)
  const handleItemClick = useCallback((item: MenuItem, event: React.MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation()
    if (!item.disabled) item.onClick()
  }, [])

  const updatePosition = useCallback(() => {
    const menuEl = menuRef.current
    const viewport = getViewportSize()
    const rect = menuEl?.getBoundingClientRect()
    const menuWidth = rect?.width ?? 180
    const menuHeight = rect?.height ?? Math.max(40, items.length * 36)
    const next = clampMenuPosition({
      x,
      y,
      menuWidth,
      menuHeight,
      viewport,
    })
    setPosition((prev) => (prev.x === next.x && prev.y === next.y ? prev : next))
    setReady(true)
  }, [items.length, x, y])

  useLayoutEffect(() => {
    updatePosition()
  }, [updatePosition])

  useEffect(() => {
    window.addEventListener('resize', updatePosition)
    window.addEventListener('scroll', updatePosition, true)
    return () => {
      window.removeEventListener('resize', updatePosition)
      window.removeEventListener('scroll', updatePosition, true)
    }
  }, [updatePosition])

  return (
    <div
      ref={menuRef}
      className="dropdown-panel fixed"
      role="menu"
      style={{ left: position.x, top: position.y, minWidth: 180, visibility: ready ? 'visible' : 'hidden' }}
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
          <span>{item.label}</span>
        </button>
      ))}
    </div>
  )
}

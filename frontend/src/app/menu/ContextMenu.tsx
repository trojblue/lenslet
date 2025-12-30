import React from 'react'

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
  return (
    <div
      className="dropdown-panel fixed"
      role="menu"
      style={{ left: x, top: y, minWidth: 180 }}
      onClick={(e) => e.stopPropagation()}
    >
      {items.map((item, idx) => (
        <button
          key={idx}
          className={`dropdown-item w-full ${item.danger ? 'text-danger hover:text-danger' : ''}`}
          role="menuitem"
          aria-disabled={item.disabled}
          disabled={item.disabled}
          onClick={(e) => {
            e.stopPropagation()
            if (!item.disabled) item.onClick()
          }}
        >
          {item.icon && <span className="shrink-0">{item.icon}</span>}
          <span>{item.label}</span>
        </button>
      ))}
    </div>
  )
}

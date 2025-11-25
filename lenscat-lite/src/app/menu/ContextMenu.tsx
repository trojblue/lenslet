import React from 'react'

export type MenuItem = { label: string; danger?: boolean; disabled?: boolean; onClick: () => void }

export default function ContextMenu({ x, y, items }:{ x:number; y:number; items: MenuItem[] }){
  return (
    <div className="fixed z-menu bg-[#1b1b1b] border border-border rounded-lg min-w-[160px] py-1.5 shadow-[0_10px_30px_rgba(0,0,0,0.4)]" role="menu" style={{ left: x, top: y }} onClick={e=> e.stopPropagation()}>
      {items.map((it, idx) => (
        <div
          key={idx}
          className={`px-3 py-2 text-text cursor-default hover:bg-hover ${it.danger ? 'text-[#ff6b6b]' : ''} ${it.disabled ? 'text-muted cursor-not-allowed' : ''}`}
          role="menuitem"
          aria-disabled={!!it.disabled}
          onClick={(e)=>{ e.stopPropagation(); if (!it.disabled) it.onClick() }}
        >
          {it.label}
        </div>
      ))}
    </div>
  )
}

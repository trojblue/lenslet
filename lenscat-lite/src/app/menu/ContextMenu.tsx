import React from 'react'

export type MenuItem = { label: string; danger?: boolean; disabled?: boolean; onClick: () => void }

export default function ContextMenu({ x, y, items }:{ x:number; y:number; items: MenuItem[] }){
  return (
    <div className="ctx" role="menu" style={{ left: x, top: y }} onClick={e=> e.stopPropagation()}>
      {items.map((it, idx) => (
        <div
          key={idx}
          className={`ctx-item${it.danger?' ctx-danger':''}${it.disabled?' disabled':''}`}
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



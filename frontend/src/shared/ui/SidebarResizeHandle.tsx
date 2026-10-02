import type { KeyboardEvent, PointerEvent } from 'react'

export type SidebarResizeControl = {
  width: number
  min: number
  max: number
  onKeyDown: (event: KeyboardEvent<HTMLDivElement>) => void
}

export default function SidebarResizeHandle({ className, label, onPointerDown, control }: {
  className: string
  label: string
  onPointerDown?: (event: PointerEvent<HTMLDivElement>) => void
  control?: SidebarResizeControl
}) {
  return <div
    className={className}
    onPointerDown={onPointerDown}
    onKeyDown={control?.onKeyDown}
    role="separator"
    aria-label={label}
    aria-orientation="vertical"
    aria-valuemin={control?.min}
    aria-valuemax={control?.max}
    aria-valuenow={control?.width}
    aria-valuetext={control ? `${Math.round(control.width)} pixels` : undefined}
    tabIndex={control ? 0 : undefined}
    title={`${label}: use Left and Right arrow keys; Shift for larger steps`}
  />
}

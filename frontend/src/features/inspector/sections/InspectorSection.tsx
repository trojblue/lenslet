import React, { useEffect, useState, type CSSProperties } from 'react'
import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'

interface InspectorSectionProps {
  title: string
  open: boolean
  onToggle: () => void
  sortableId?: string
  sortableEnabled?: boolean
  actions?: React.ReactNode
  children: React.ReactNode
  contentClassName?: string
}

export function InspectorSection({
  title,
  open,
  onToggle,
  sortableId,
  sortableEnabled = false,
  actions,
  children,
  contentClassName,
}: InspectorSectionProps): JSX.Element {
  const [renderBody, setRenderBody] = useState(open)
  const [bodyState, setBodyState] = useState(open ? 'open' : 'closed')
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({
    id: sortableId ?? `inspector-section-${title}`,
    disabled: !sortableEnabled,
  })
  const sectionStyle: CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
  }

  useEffect(() => {
    if (open) {
      setRenderBody(true)
      const id = window.requestAnimationFrame(() => setBodyState('open'))
      return () => window.cancelAnimationFrame(id)
    }
    setBodyState('closing')
    const timeoutId = window.setTimeout(() => {
      setRenderBody(false)
      setBodyState('closed')
    }, 140)
    return () => window.clearTimeout(timeoutId)
  }, [open])

  return (
    <div
      ref={setNodeRef}
      style={sectionStyle}
      className={`border-b border-border/60 ${isDragging ? 'opacity-70' : ''}`}
      data-inspector-section-id={sortableId ?? undefined}
    >
      <div className="flex items-center justify-between gap-2 px-3 py-2.5">
        <div className="flex items-center gap-1 min-w-0">
          {sortableEnabled && (
            <button
              type="button"
              className="inline-flex h-6 w-6 items-center justify-center rounded-md border border-transparent text-muted hover:border-border/60 hover:text-text cursor-grab active:cursor-grabbing"
              aria-label={`Reorder ${title}`}
              title={`Reorder ${title}`}
              {...attributes}
              {...listeners}
            >
              <svg
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M9 6h.01" />
                <path d="M9 12h.01" />
                <path d="M9 18h.01" />
                <path d="M15 6h.01" />
                <path d="M15 12h.01" />
                <path d="M15 18h.01" />
              </svg>
            </button>
          )}
          <button
            type="button"
            onClick={onToggle}
            aria-expanded={open}
            className="flex min-w-0 items-center gap-2 inspector-section-title hover:text-text transition-colors"
          >
            <svg
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className={`transition-transform ${open ? 'rotate-90' : ''}`}
              aria-hidden="true"
            >
              <path d="m9 18 6-6-6-6" />
            </svg>
            <span>{title}</span>
          </button>
        </div>
        <div className="shrink-0">{actions}</div>
      </div>
      {renderBody && (
        <div className="inspector-section-body" data-state={bodyState} aria-hidden={!open}>
          <div className={contentClassName ?? 'px-3 pb-3'}>
            {children}
          </div>
        </div>
      )}
    </div>
  )
}

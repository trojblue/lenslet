import React, { useId, useRef, type CSSProperties } from 'react'
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
  minHeightPx?: number
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
  minHeightPx,
}: InspectorSectionProps): JSX.Element {
  const bodyId = useId()
  const toggleRef = useRef<HTMLButtonElement>(null)
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
    minHeight: minHeightPx,
  }

  return (
    <div
      ref={setNodeRef}
      style={sectionStyle}
      className={`border-b border-border/60 ${isDragging ? 'opacity-70' : ''}`}
      data-inspector-section-id={sortableId ?? undefined}
    >
      <div className="inspector-section-header flex items-center justify-between gap-2 px-3 py-2.5">
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
            ref={toggleRef}
            type="button"
            onClick={onToggle}
            aria-expanded={open}
            aria-controls={bodyId}
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
              className={`inspector-section-chevron ${open ? 'rotate-90' : ''}`}
              aria-hidden="true"
            >
              <path d="m9 18 6-6-6-6" />
            </svg>
            <span className="truncate">{title}</span>
          </button>
        </div>
        {actions && <div className="inspector-section-actions shrink-0">{actions}</div>}
      </div>
      <div
        id={bodyId}
        className="inspector-section-body"
        data-state={open ? 'open' : 'closed'}
        aria-hidden={!open}
        ref={(element) => {
          if (!element) return
          if (!open && element.contains(document.activeElement)) toggleRef.current?.focus()
          element.toggleAttribute('inert', !open)
        }}
      >
        <div className="inspector-section-body-clip">
          <div className={`relative ${contentClassName ?? 'px-3 pb-3'}`}>
            {children}
          </div>
        </div>
      </div>
    </div>
  )
}

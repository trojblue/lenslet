import React, { useMemo, useState } from 'react'
import { DropdownMenu } from '../../../shared/ui/Dropdown'
import type { FieldDefinition, FieldId } from './FieldRegistry'

interface FieldPickerProps {
  fields: FieldDefinition[]
  metricKeys: string[]
  onSelect: (fieldId: FieldId) => void
  label?: string
  buttonClassName?: string
}

export default function FieldPicker({
  fields,
  metricKeys,
  onSelect,
  label = 'Add condition',
  buttonClassName = 'btn btn-sm',
}: FieldPickerProps) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return fields
    return fields.filter((field) => field.label.toLowerCase().includes(q))
  }, [fields, query])

  const grouped = useMemo(() => groupFields(filtered), [filtered])

  return (
    <DropdownMenu
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) setQuery('')
      }}
      panelClassName="w-[260px] p-2"
      trigger={(
        <button type="button" className={buttonClassName}>
          + {label}
        </button>
      )}
    >
      <div className="space-y-2">
        <input
          className="h-8 w-full rounded-lg px-2.5 border border-border bg-surface text-text"
          placeholder="Search fields"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <div className="max-h-[220px] overflow-auto">
          {grouped.length === 0 ? (
            <div className="text-xs text-muted px-2 py-2">No matches.</div>
          ) : (
            grouped.map((group) => (
              <div key={group.label} className="mb-1.5">
                <div className="dropdown-label">{group.label}</div>
                {group.fields.map((field) => {
                  const disabled = field.isDisabled?.(metricKeys) ?? false
                  return (
                    <button
                      key={field.id}
                      className={`dropdown-item ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
                      disabled={disabled}
                      onClick={() => {
                        if (disabled) return
                        onSelect(field.id)
                        setOpen(false)
                        setQuery('')
                      }}
                    >
                      {field.label}
                    </button>
                  )
                })}
              </div>
            ))
          )}
        </div>
      </div>
    </DropdownMenu>
  )
}

function groupFields(fields: FieldDefinition[]) {
  const grouped = new Map<string, FieldDefinition[]>()
  for (const field of fields) {
    const list = grouped.get(field.category) ?? []
    list.push(field)
    grouped.set(field.category, list)
  }
  return Array.from(grouped.entries()).map(([label, items]) => ({ label, fields: items }))
}

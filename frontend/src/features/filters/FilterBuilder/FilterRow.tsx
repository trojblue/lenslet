import React from 'react'
import {
  FieldDefinition,
  FieldId,
  FilterRowState,
  createRowState,
} from './FieldRegistry'

const STAR_VALUES = [5, 4, 3, 2, 1, 0]

interface FilterRowProps {
  row: FilterRowState
  field: FieldDefinition
  fields: FieldDefinition[]
  metricKeys: string[]
  onChange: (row: FilterRowState) => void
  onRemove: () => void
}

export default function FilterRow({
  row,
  field,
  fields,
  metricKeys,
  onChange,
  onRemove,
}: FilterRowProps) {
  const groupedFields = groupFields(fields)

  const handleFieldChange = (fieldId: FieldId) => {
    onChange(createRowState(fieldId, metricKeys, row.id))
  }

  const handleOperatorChange = (opId: string) => {
    onChange({ ...row, opId: opId as FilterRowState['opId'] })
  }

  const renderValueEditor = () => {
    switch (field.valueKind) {
      case 'text': {
        const value = row.value.kind === 'text' ? row.value.value : ''
        return (
          <input
            className="h-8 w-full rounded-lg px-2.5 border border-border bg-surface text-text"
            value={value}
            placeholder="Value"
            onChange={(e) => onChange({ ...row, value: { kind: 'text', value: e.target.value } })}
          />
        )
      }
      case 'stars': {
        const values = row.value.kind === 'stars' ? row.value.values : []
        const toggle = (v: number) => {
          const next = new Set(values)
          if (next.has(v)) {
            next.delete(v)
          } else {
            next.add(v)
          }
          const ordered = Array.from(next).sort((a, b) => b - a)
          onChange({ ...row, value: { kind: 'stars', values: ordered } })
        }
        return (
          <div className="flex flex-wrap gap-1">
            {STAR_VALUES.map((v) => {
              const active = values.includes(v)
              return (
                <button
                  key={`star-${row.id}-${v}`}
                  type="button"
                  className={`h-7 min-w-[32px] px-2 rounded border text-[11px] flex items-center justify-center transition-colors ${
                    active
                      ? 'bg-accent-muted text-star-active border-border'
                      : 'bg-surface text-text border-border/70 hover:bg-surface-hover'
                  }`}
                  onClick={() => toggle(v)}
                  aria-pressed={active}
                >
                  {v === 0 ? 'None' : `${v}★`}
                </button>
              )
            })}
          </div>
        )
      }
      case 'date': {
        const from = row.value.kind === 'date' ? row.value.from ?? '' : ''
        const to = row.value.kind === 'date' ? row.value.to ?? '' : ''
        return (
          <div className="grid grid-cols-2 gap-2">
            <input
              type="date"
              className="h-8 w-full rounded-lg px-2.5 border border-border bg-surface text-text"
              value={from}
              onChange={(e) => onChange({
                ...row,
                value: { kind: 'date', from: e.target.value || undefined, to: row.value.kind === 'date' ? row.value.to : undefined },
              })}
            />
            <input
              type="date"
              className="h-8 w-full rounded-lg px-2.5 border border-border bg-surface text-text"
              value={to}
              onChange={(e) => onChange({
                ...row,
                value: { kind: 'date', from: row.value.kind === 'date' ? row.value.from : undefined, to: e.target.value || undefined },
              })}
            />
          </div>
        )
      }
      case 'compare': {
        const value = row.value.kind === 'compare' ? row.value.value : undefined
        return (
          <input
            type="number"
            className="h-8 w-full rounded-lg px-2.5 border border-border bg-surface text-text"
            value={value ?? ''}
            min={0}
            placeholder="Value"
            onChange={(e) => {
              const raw = e.target.value
              if (!raw) {
                onChange({ ...row, value: { kind: 'compare', value: undefined } })
                return
              }
              const num = Number(raw)
              if (!Number.isFinite(num)) return
              onChange({ ...row, value: { kind: 'compare', value: num } })
            }}
          />
        )
      }
      case 'metric': {
        const metricValue = row.value.kind === 'metric'
          ? row.value
          : { kind: 'metric', key: metricKeys[0] ?? '', min: undefined, max: undefined }
        return (
          <div className="flex flex-col gap-2">
            {metricKeys.length > 0 ? (
              <select
                className="h-8 w-full rounded-lg px-2.5 border border-border bg-surface text-text"
                value={metricValue.key}
                onChange={(e) => onChange({
                  ...row,
                  value: { ...metricValue, key: e.target.value },
                })}
              >
                {metricKeys.map((key) => (
                  <option key={key} value={key}>{key}</option>
                ))}
              </select>
            ) : (
              <input
                className="h-8 w-full rounded-lg px-2.5 border border-border bg-surface text-text"
                value={metricValue.key}
                placeholder="Metric key"
                onChange={(e) => onChange({
                  ...row,
                  value: { ...metricValue, key: e.target.value },
                })}
              />
            )}
            <div className="grid grid-cols-2 gap-2">
              <input
                type="number"
                className="h-8 w-full rounded-lg px-2.5 border border-border bg-surface text-text"
                value={metricValue.min ?? ''}
                placeholder="Min"
                onChange={(e) => {
                  const raw = e.target.value
                  const min = raw ? Number(raw) : undefined
                  if (raw && !Number.isFinite(min)) return
                  onChange({
                    ...row,
                    value: { ...metricValue, min },
                  })
                }}
              />
              <input
                type="number"
                className="h-8 w-full rounded-lg px-2.5 border border-border bg-surface text-text"
                value={metricValue.max ?? ''}
                placeholder="Max"
                onChange={(e) => {
                  const raw = e.target.value
                  const max = raw ? Number(raw) : undefined
                  if (raw && !Number.isFinite(max)) return
                  onChange({
                    ...row,
                    value: { ...metricValue, max },
                  })
                }}
              />
            </div>
          </div>
        )
      }
      default:
        return null
    }
  }

  return (
    <div className="grid grid-cols-[170px_140px_1fr_auto] gap-2 items-start">
      <select
        className="h-8 w-full rounded-lg px-2.5 border border-border bg-surface text-text"
        value={row.fieldId}
        onChange={(e) => handleFieldChange(e.target.value as FieldId)}
      >
        {groupedFields.map((group) => (
          <optgroup key={group.label} label={group.label}>
            {group.fields.map((opt) => (
              <option
                key={opt.id}
                value={opt.id}
                disabled={opt.isDisabled?.(metricKeys) && opt.id !== row.fieldId}
              >
                {opt.label}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
      <select
        className="h-8 w-full rounded-lg px-2.5 border border-border bg-surface text-text"
        value={row.opId}
        onChange={(e) => handleOperatorChange(e.target.value)}
        disabled={field.operators.length <= 1}
      >
        {field.operators.map((op) => (
          <option key={`${row.id}-${op.id}`} value={op.id}>{op.label}</option>
        ))}
      </select>
      <div className="min-w-0">{renderValueEditor()}</div>
      <button
        type="button"
        className="btn btn-icon h-8 w-8"
        onClick={onRemove}
        aria-label="Remove condition"
        title="Remove"
      >
        ×
      </button>
    </div>
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

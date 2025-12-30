import React from 'react'
import type { FieldDefinition, FieldId, FilterGroupState, FilterRowState, MatchMode } from './FieldRegistry'
import { createRowState } from './FieldRegistry'
import FieldPicker from './FieldPicker'
import FilterRow from './FilterRow'

interface FilterGroupProps {
  group: FilterGroupState
  index: number
  totalGroups: number
  fields: FieldDefinition[]
  metricKeys: string[]
  onChange: (group: FilterGroupState) => void
  onRemove?: () => void
}

export default function FilterGroup({
  group,
  index,
  totalGroups,
  fields,
  metricKeys,
  onChange,
  onRemove,
}: FilterGroupProps) {
  const handleModeChange = (mode: MatchMode) => {
    onChange({ ...group, mode })
  }

  const addRow = (fieldId: FieldId) => {
    onChange({
      ...group,
      rows: [...group.rows, createRowState(fieldId, metricKeys)],
    })
  }

  const updateRow = (rowId: string, nextRow: FilterRowState) => {
    onChange({
      ...group,
      rows: group.rows.map((row) => (row.id === rowId ? nextRow : row)),
    })
  }

  const removeRow = (rowId: string) => {
    onChange({
      ...group,
      rows: group.rows.filter((row) => row.id !== rowId),
    })
  }

  return (
    <div className="rounded-xl border border-border bg-panel p-3 space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-xs uppercase tracking-wide text-muted">
          Group {index + 1}
          {totalGroups > 1 ? ' (AND)' : ''}
        </div>
        <div className="flex items-center gap-2">
          <select
            className="h-7 rounded-lg px-2 border border-border bg-surface text-text text-xs"
            value={group.mode}
            onChange={(e) => handleModeChange(e.target.value as MatchMode)}
          >
            <option value="all">All</option>
            <option value="any">Any</option>
          </select>
          {totalGroups > 1 && onRemove && (
            <button
              type="button"
              className="btn btn-sm"
              onClick={onRemove}
            >
              Remove group
            </button>
          )}
        </div>
      </div>

      <div className="space-y-2">
        {group.rows.map((row) => {
          const field = fields.find((f) => f.id === row.fieldId) ?? fields[0]
          return (
            <FilterRow
              key={row.id}
              row={row}
              field={field}
              fields={fields}
              metricKeys={metricKeys}
              onChange={(nextRow) => updateRow(row.id, nextRow)}
              onRemove={() => removeRow(row.id)}
            />
          )
        })}
      </div>

      <FieldPicker
        fields={fields}
        metricKeys={metricKeys}
        onSelect={addRow}
        label="Add condition"
        buttonClassName="btn btn-sm"
      />
    </div>
  )
}

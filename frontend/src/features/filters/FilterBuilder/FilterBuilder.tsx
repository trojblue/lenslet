import React, { useEffect, useMemo, useRef, useState } from 'react'
import type { FilterAST, FilterClause, FilterExpr, FilterNode } from '../../../lib/types'
import {
  MatchMode,
  FilterGroupState,
  FilterRowState,
  FieldId,
  clauseToRowState,
  createGroupState,
  createRowState,
  getFieldDefinitions,
  rowToClause,
} from './FieldRegistry'
import FieldPicker from './FieldPicker'
import FilterGroup from './FilterGroup'

interface FilterBuilderProps {
  filters: FilterAST
  metricKeys: string[]
  onChange: (filters: FilterAST) => void
  onReset?: () => void
  resultCount?: number
}

export default function FilterBuilder({
  filters,
  metricKeys,
  onChange,
  onReset,
  resultCount,
}: FilterBuilderProps) {
  const fields = useMemo(() => getFieldDefinitions(metricKeys), [metricKeys])
  const [groups, setGroups] = useState<FilterGroupState[]>(() => astToGroups(filters, metricKeys))
  const lastEmitted = useRef<string>('')

  const filtersKey = useMemo(() => JSON.stringify(filters), [filters])

  useEffect(() => {
    if (lastEmitted.current === filtersKey) return
    setGroups(astToGroups(filters, metricKeys))
  }, [filtersKey, metricKeys])

  const emitGroups = (nextGroups: FilterGroupState[]) => {
    setGroups(nextGroups)
    const nextAst = groupsToAst(nextGroups)
    const nextKey = JSON.stringify(nextAst)
    if (nextKey === filtersKey) return
    lastEmitted.current = nextKey
    onChange(nextAst)
  }

  const totalRows = groups.reduce((acc, group) => acc + group.rows.length, 0)

  const headerMode: MatchMode = groups[0]?.mode ?? 'all'

  const updateAllGroupModes = (mode: MatchMode) => {
    if (!groups.length) {
      emitGroups([createGroupState(mode)])
      return
    }
    emitGroups(groups.map((group) => ({ ...group, mode })))
  }

  const addGroup = () => {
    emitGroups([...groups, createGroupState(headerMode)])
  }

  const addCondition = (fieldId: FieldId) => {
    if (!groups.length) {
      const group = createGroupState(headerMode)
      group.rows.push(createRowState(fieldId, metricKeys))
      emitGroups([group])
      return
    }
    const nextGroups = [...groups]
    const target = { ...nextGroups[nextGroups.length - 1] }
    target.rows = [...target.rows, createRowState(fieldId, metricKeys)]
    nextGroups[nextGroups.length - 1] = target
    emitGroups(nextGroups)
  }

  const handleReset = () => {
    onReset?.()
    if (!onReset) {
      onChange({ all: [] })
    }
    setGroups([])
    lastEmitted.current = JSON.stringify({ all: [] })
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs uppercase tracking-wide text-muted">Match</span>
          <select
            className="h-8 rounded-lg px-2 border border-border bg-surface text-text text-xs"
            value={headerMode}
            onChange={(e) => updateAllGroupModes(e.target.value as MatchMode)}
          >
            <option value="all">All conditions</option>
            <option value="any">Any condition</option>
          </select>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="btn btn-sm"
            onClick={handleReset}
            disabled={groups.length === 0}
          >
            Reset
          </button>
        </div>
      </div>

      {totalRows === 0 ? (
        <div className="rounded-xl border border-dashed border-border bg-panel/50 p-4 text-center space-y-3">
          <div className="text-sm text-muted">No filters yet.</div>
          <div className="flex flex-wrap gap-2 justify-center">
            <FieldPicker
              fields={fields}
              metricKeys={metricKeys}
              onSelect={addCondition}
              label="Add condition"
            />
            <button type="button" className="btn btn-sm" onClick={() => addCondition('stars')}>Stars</button>
            <button type="button" className="btn btn-sm" onClick={() => addCondition('filename')}>Filename</button>
            <button type="button" className="btn btn-sm" onClick={() => addCondition('dateAdded')}>Date</button>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => addCondition('metric')}
              disabled={metricKeys.length === 0}
            >
              Metric
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {groups.map((group, idx) => (
            <FilterGroup
              key={group.id}
              group={group}
              index={idx}
              totalGroups={groups.length}
              fields={fields}
              metricKeys={metricKeys}
              onChange={(nextGroup) => {
                const nextGroups = groups.map((g) => (g.id === group.id ? nextGroup : g))
                emitGroups(nextGroups)
              }}
              onRemove={groups.length > 1
                ? () => emitGroups(groups.filter((g) => g.id !== group.id))
                : undefined}
            />
          ))}
          <div className="flex items-center gap-2">
            <FieldPicker
              fields={fields}
              metricKeys={metricKeys}
              onSelect={addCondition}
              label="Add condition"
            />
            <button type="button" className="btn btn-sm" onClick={addGroup}>Add group</button>
          </div>
        </div>
      )}

      {typeof resultCount === 'number' && (
        <div className="text-xs text-muted">
          Found {resultCount} item{resultCount === 1 ? '' : 's'}
        </div>
      )}
    </div>
  )
}

function astToGroups(filters: FilterAST, metricKeys: string[]): FilterGroupState[] {
  const mode = isAllExpr(filters) ? 'all' : 'any'
  const nodes = getExprNodes(filters)
  if (!nodes.length) return []

  const allGroups = mode === 'all' && nodes.every((node) => isFilterExpr(node))
  if (allGroups) {
    return nodes.map((node) => {
      const expr = node as FilterExpr
      const groupMode = isAllExpr(expr) ? 'all' : 'any'
      const clauses = getExprNodes(expr).filter((child): child is FilterClause => !isFilterExpr(child))
      const rows = clauses
        .map((clause) => clauseToRowState(clause, metricKeys))
        .filter((row): row is Omit<FilterRowState, 'id'> => Boolean(row))
        .map((row) => ({
          ...createRowState(row.fieldId, metricKeys),
          opId: row.opId,
          value: row.value,
        }))
      return { ...createGroupState(groupMode), rows }
    })
  }

  const clauses = nodes.filter((child): child is FilterClause => !isFilterExpr(child))
  const rows = clauses
    .map((clause) => clauseToRowState(clause, metricKeys))
    .filter((row): row is Omit<FilterRowState, 'id'> => Boolean(row))
    .map((row) => ({
      ...createRowState(row.fieldId, metricKeys),
      opId: row.opId,
      value: row.value,
    }))

  if (!rows.length) return []
  return [{ ...createGroupState(mode), rows }]
}

function groupsToAst(groups: FilterGroupState[]): FilterAST {
  if (!groups.length) return { all: [] }

  const groupClauses = groups
    .map((group) => {
      const clauses = group.rows
        .map((row) => rowToClause(row, metricKeys))
        .filter((clause): clause is FilterClause => Boolean(clause))
      if (!clauses.length) return null
      return group.mode === 'all' ? { all: clauses } : { any: clauses }
    })
    .filter((group): group is FilterExpr => Boolean(group))

  if (!groupClauses.length) return { all: [] }
  if (groupClauses.length === 1) {
    return groupClauses[0]
  }
  return { all: groupClauses }
}

function isFilterExpr(node: FilterNode): node is FilterExpr {
  return typeof node === 'object' && node != null && ('all' in node || 'any' in node)
}

function isAllExpr(expr: FilterExpr): expr is { all: FilterNode[] } {
  return 'all' in expr
}

function getExprNodes(expr: FilterExpr): FilterNode[] {
  return isAllExpr(expr) ? expr.all : expr.any
}

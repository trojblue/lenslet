import React from 'react'
import type {
  CompareMetadataColumn,
  CompareMetadataMatrixResult,
} from '../model/metadataCompare'
import type { InspectorWidgetId } from '../model/inspectorWidgetOrder'
import { InspectorSection } from './InspectorSection'

type CompareMetaState = 'idle' | 'loading' | 'loaded' | 'error'

interface CompareMetadataSectionProps {
  open: boolean
  onToggle: () => void
  compareMetaState: CompareMetaState
  compareMetaError: string | null
  compareColumns: CompareMetadataColumn[]
  compareIncludePilInfo: boolean
  onToggleCompareIncludePilInfo: () => void
  onReload: () => void
  compareMatrix: CompareMetadataMatrixResult | null
  compareSelectionTruncatedCount: number
  sortableId?: InspectorWidgetId
  sortableEnabled?: boolean
}

interface CompareMatrixTableProps {
  matrix: CompareMetadataMatrixResult
}

const CompareMatrixTable = React.memo(function CompareMatrixTable({
  matrix,
}: CompareMatrixTableProps): JSX.Element {
  if (matrix.rows.length === 0) {
    return <div className="text-muted">No differences found.</div>
  }

  return (
    <div className="space-y-2">
      <div className="overflow-x-auto rounded border border-border/60 bg-surface-inset/40">
        <table className="min-w-full border-separate border-spacing-0 text-[11px]">
          <thead>
            <tr>
              <th className="sticky left-0 z-10 min-w-[180px] border-b border-r border-border/60 bg-surface px-2 py-1 text-left text-[10px] uppercase tracking-wide text-muted">
                Path
              </th>
              {matrix.columns.map((column, idx) => (
                <th
                  key={column.path}
                  className="min-w-[170px] border-b border-border/60 bg-surface px-2 py-1 text-left text-[10px] uppercase tracking-wide text-muted"
                  title={column.path}
                >
                  {`#${idx + 1} ${column.label}`}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.rows.map((row) => (
              <tr key={row.key}>
                <th
                  scope="row"
                  className="sticky left-0 z-[1] border-b border-r border-border/60 bg-panel px-2 py-1 text-left font-normal text-muted break-all"
                  title={row.key}
                >
                  {row.key}
                </th>
                {row.values.map((value, valueIdx) => (
                  <td
                    key={`${row.key}-${valueIdx}`}
                    className="border-b border-border/60 px-2 py-1 align-top"
                  >
                    <div className={value === '—' ? 'text-muted italic' : 'whitespace-pre-wrap break-words'}>
                      {value}
                    </div>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {matrix.truncatedRowCount > 0 && (
        <div className="text-[11px] text-muted">
          +
          {matrix.truncatedRowCount}
          {' '}
          more rows not shown.
        </div>
      )}
    </div>
  )
})

CompareMatrixTable.displayName = 'CompareMatrixTable'

function CompareMetadataSectionComponent({
  open,
  onToggle,
  compareMetaState,
  compareMetaError,
  compareColumns,
  compareIncludePilInfo,
  onToggleCompareIncludePilInfo,
  onReload,
  compareMatrix,
  compareSelectionTruncatedCount,
  sortableId,
  sortableEnabled = false,
}: CompareMetadataSectionProps): JSX.Element {
  const compareMetaLoaded = compareMetaState === 'loaded'

  return (
    <InspectorSection
      title="Compare Metadata"
      open={open}
      onToggle={onToggle}
      sortableId={sortableId}
      sortableEnabled={sortableEnabled}
      actions={(
        <div className="flex items-center gap-2 text-xs">
          <button
            className="px-2 py-1 bg-transparent text-muted border border-border/60 rounded-md disabled:opacity-60 hover:border-border hover:text-text transition-colors"
            onClick={onReload}
            disabled={compareMetaState === 'loading'}
          >
            {compareMetaState === 'loading' ? 'Loading…' : 'Reload'}
          </button>
          <button
            className="px-2 py-1 bg-transparent text-muted border border-border/60 rounded-md disabled:opacity-60 hover:border-border hover:text-text transition-colors"
            onClick={onToggleCompareIncludePilInfo}
            disabled={!compareMetaLoaded}
          >
            {compareIncludePilInfo ? 'Hide PIL info' : 'Include PIL info'}
          </button>
        </div>
      )}
    >
      <div className="space-y-2 text-[11px]">
        <div className="flex flex-wrap items-center gap-2 text-muted">
          <span>
            Comparing
            {' '}
            {compareColumns.length}
            {' '}
            images.
          </span>
          {compareSelectionTruncatedCount > 0 && (
            <span>
              +
              {compareSelectionTruncatedCount}
              {' '}
              not shown.
            </span>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {compareColumns.map((column, idx) => (
            <span
              key={column.path}
              className="rounded border border-border/60 bg-surface-inset px-2 py-0.5 text-[11px] text-muted"
              title={column.path}
            >
              {`#${idx + 1} ${column.label}`}
            </span>
          ))}
        </div>

        {compareMetaState === 'loading' && (
          <div className="text-muted">Loading metadata…</div>
        )}
        {compareMetaState === 'error' && compareMetaError && (
          <div className="text-danger break-words">{compareMetaError}</div>
        )}

        {compareMetaLoaded && compareMatrix && (
          <div className="space-y-2">
            <div className="text-muted">
              {compareMatrix.summary.differingRows}
              {' '}
              differing rows
              {' '}
              ·
              {' '}
              {compareMatrix.summary.missingValues}
              {' '}
              missing values
            </div>
            <CompareMatrixTable matrix={compareMatrix} />
          </div>
        )}
      </div>
    </InspectorSection>
  )
}

export const CompareMetadataSection = React.memo(CompareMetadataSectionComponent)

CompareMetadataSection.displayName = 'CompareMetadataSection'

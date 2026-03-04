import React from 'react'
import type {
  CompareMetadataColumn,
  CompareMetadataMatrixResult,
} from '../model/metadataCompare'
import type { InspectorWidgetId } from '../model/inspectorWidgetOrder'
import { InspectorSection } from './InspectorSection'

type CompareMetaState = 'idle' | 'loading' | 'loaded' | 'error'
const PATH_COLUMN_WIDTH_PX = 120
const COMPARE_VALUE_COLUMN_WIDTH_PX = 110
const OMITTED_PATH_SEGMENT_RE = /^found_text_chunks\[(?:\d+|i)\]$/
const COMPARE_INTERACTIVE_ATTR_VALUE = 'true'
const COMPARE_COPY_BUTTON_CLASS = 'inspector-scroll-value inline-flex max-w-full rounded px-1 text-left underline-offset-2 transition-colors hover:bg-surface/80 hover:text-text hover:underline hover:decoration-dotted focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-border-strong cursor-pointer'
const SECTION_ACTION_BUTTON_CLASS = 'px-2 py-1 bg-transparent text-muted border border-border/60 rounded-md disabled:opacity-60 hover:border-border hover:text-text transition-colors'

function isInteractiveCompareTarget(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false
  return target.closest(`[data-compare-copy-interactive="${COMPARE_INTERACTIVE_ATTR_VALUE}"]`) !== null
}

function toDisplayPathLabel(pathKey: string): string {
  const segments = pathKey
    .split('.')
    .map((segment) => segment.trim())
    .filter((segment) => segment.length > 0 && !OMITTED_PATH_SEGMENT_RE.test(segment) && segment !== 'text')
  return segments.length > 0 ? segments.join('.') : pathKey
}

interface CompareMetadataSectionProps {
  open: boolean
  onToggle: () => void
  compareMetaState: CompareMetaState
  compareMetaError: string | null
  compareColumns: CompareMetadataColumn[]
  compareIncludePilInfo: boolean
  onToggleCompareIncludePilInfo: () => void
  onReload: () => void
  compareCopiedPath: string | null
  onCopyCompareValue: (pathLabel: string, copyText: string) => void
  compareMatrix: CompareMetadataMatrixResult | null
  compareSelectionTruncatedCount: number
  sortableId?: InspectorWidgetId
  sortableEnabled?: boolean
}

interface CompareMatrixTableProps {
  matrix: CompareMetadataMatrixResult
  compareCopiedPath: string | null
  onCopyCompareValue: (pathLabel: string, copyText: string) => void
}

const CompareMatrixTable = React.memo(function CompareMatrixTable({
  matrix,
  compareCopiedPath,
  onCopyCompareValue,
}: CompareMatrixTableProps): JSX.Element {
  const topScrollRef = React.useRef<HTMLDivElement | null>(null)
  const bodyScrollRef = React.useRef<HTMLDivElement | null>(null)
  const scrollSyncSourceRef = React.useRef<'top' | 'body' | null>(null)
  const panStateRef = React.useRef<{ active: boolean; startX: number; startScrollLeft: number; moved: boolean }>({
    active: false,
    startX: 0,
    startScrollLeft: 0,
    moved: false,
  })
  const suppressClickRef = React.useRef(false)
  const [topScrollWidth, setTopScrollWidth] = React.useState(0)
  const [isPanning, setIsPanning] = React.useState(false)

  const updateTopScrollWidth = React.useCallback(() => {
    setTopScrollWidth(bodyScrollRef.current?.scrollWidth ?? 0)
  }, [])

  React.useEffect(() => {
    updateTopScrollWidth()
    const bodyScroll = bodyScrollRef.current
    if (!bodyScroll || typeof ResizeObserver === 'undefined') return undefined
    const table = bodyScroll.querySelector('table')
    const observer = new ResizeObserver(() => {
      updateTopScrollWidth()
    })
    observer.observe(bodyScroll)
    if (table) observer.observe(table)
    return () => observer.disconnect()
  }, [matrix.columns.length, matrix.rows.length, updateTopScrollWidth])

  const handleTopScroll = React.useCallback(() => {
    const topScroll = topScrollRef.current
    const bodyScroll = bodyScrollRef.current
    if (!topScroll || !bodyScroll) return
    if (scrollSyncSourceRef.current === 'body') {
      scrollSyncSourceRef.current = null
      return
    }
    scrollSyncSourceRef.current = 'top'
    bodyScroll.scrollLeft = topScroll.scrollLeft
  }, [])

  const handleBodyScroll = React.useCallback(() => {
    const topScroll = topScrollRef.current
    const bodyScroll = bodyScrollRef.current
    if (!topScroll || !bodyScroll) return
    if (scrollSyncSourceRef.current === 'top') {
      scrollSyncSourceRef.current = null
      return
    }
    scrollSyncSourceRef.current = 'body'
    topScroll.scrollLeft = bodyScroll.scrollLeft
  }, [])

  const endPan = React.useCallback(() => {
    if (!panStateRef.current.active) return
    if (panStateRef.current.moved) {
      suppressClickRef.current = true
    }
    panStateRef.current.active = false
    setIsPanning(false)
  }, [])

  const handlePointerDown = React.useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    if (event.pointerType !== 'mouse' || event.button !== 0) return
    const bodyScroll = bodyScrollRef.current
    if (!bodyScroll) return
    if (bodyScroll.scrollWidth <= bodyScroll.clientWidth) return
    if (isInteractiveCompareTarget(event.target)) return
    panStateRef.current = {
      active: true,
      startX: event.clientX,
      startScrollLeft: bodyScroll.scrollLeft,
      moved: false,
    }
    setIsPanning(true)
    bodyScroll.setPointerCapture(event.pointerId)
  }, [])

  const handlePointerMove = React.useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    if (!panStateRef.current.active) return
    const bodyScroll = bodyScrollRef.current
    if (!bodyScroll) return
    const deltaX = event.clientX - panStateRef.current.startX
    if (Math.abs(deltaX) >= 3) {
      panStateRef.current.moved = true
    }
    bodyScroll.scrollLeft = panStateRef.current.startScrollLeft - deltaX
    event.preventDefault()
  }, [])

  const releaseBodyPointerCapture = React.useCallback((pointerId: number) => {
    const bodyScroll = bodyScrollRef.current
    if (bodyScroll && bodyScroll.hasPointerCapture(pointerId)) {
      bodyScroll.releasePointerCapture(pointerId)
    }
  }, [])

  const handlePointerUp = React.useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    releaseBodyPointerCapture(event.pointerId)
    endPan()
  }, [endPan, releaseBodyPointerCapture])

  const handlePointerCancel = React.useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    releaseBodyPointerCapture(event.pointerId)
    endPan()
  }, [endPan, releaseBodyPointerCapture])

  const handleClickCapture = React.useCallback((event: React.MouseEvent<HTMLDivElement>) => {
    if (!suppressClickRef.current) return
    suppressClickRef.current = false
    event.preventDefault()
    event.stopPropagation()
  }, [])

  if (matrix.rows.length === 0) {
    return <div className="text-muted">No differences found.</div>
  }

  return (
    <div className="space-y-2">
      <div
        ref={topScrollRef}
        className="scrollbar-thin overflow-x-auto overflow-y-hidden rounded border border-border/60 bg-surface-inset/20"
        onScroll={handleTopScroll}
      >
        <div style={{ width: topScrollWidth, height: 1 }} />
      </div>
      <div
        ref={bodyScrollRef}
        className={`relative scrollbar-thin overflow-x-auto rounded border border-border/60 bg-surface-inset/40 ${isPanning ? 'cursor-grabbing' : 'cursor-grab'}`}
        onScroll={handleBodyScroll}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerCancel}
        onClickCapture={handleClickCapture}
      >
        {compareCopiedPath && (
          <div className="ui-json-key-toast">
            Copied value:
            {' '}
            {compareCopiedPath}
          </div>
        )}
        <table className="w-max min-w-full table-fixed border-separate border-spacing-0 text-[11px]">
          <colgroup>
            <col style={{ width: PATH_COLUMN_WIDTH_PX }} />
            {matrix.columns.map((column) => (
              <col key={column.path} style={{ width: COMPARE_VALUE_COLUMN_WIDTH_PX }} />
            ))}
          </colgroup>
          <thead>
            <tr>
              <th className="sticky left-0 z-10 border-b border-r border-border/60 bg-surface px-2 py-1 text-left text-[10px] uppercase tracking-wide text-muted">
                Path
              </th>
              {matrix.columns.map((column, idx) => (
                <th
                  key={column.path}
                  className="border-b border-border/60 bg-surface px-2 py-1 text-left text-[10px] uppercase tracking-wide text-muted"
                  title={column.path}
                >
                  {`#${idx + 1} ${column.label}`}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.rows.map((row) => {
              const displayKey = toDisplayPathLabel(row.key)
              return (
                <tr key={row.key}>
                  <th
                    scope="row"
                    className="sticky left-0 z-[1] border-b border-r border-border/60 bg-panel px-2 py-1 text-left font-normal text-muted"
                    title={row.key}
                  >
                    <button
                      type="button"
                      data-compare-copy-interactive={COMPARE_INTERACTIVE_ATTR_VALUE}
                      className={COMPARE_COPY_BUTTON_CLASS}
                      onClick={() => onCopyCompareValue(displayKey, row.key)}
                      title="Click to copy path"
                    >
                      {displayKey}
                    </button>
                  </th>
                  {row.values.map((value, valueIdx) => (
                    <td
                      key={`${row.key}-${valueIdx}`}
                      className="border-b border-border/60 px-2 py-1 align-top"
                    >
                      <button
                        type="button"
                        data-compare-copy-interactive={COMPARE_INTERACTIVE_ATTR_VALUE}
                        className={COMPARE_COPY_BUTTON_CLASS}
                        onClick={() => {
                          const column = matrix.columns[valueIdx]
                          const pathLabel = column
                            ? `${displayKey} · #${valueIdx + 1} ${column.label}`
                            : `${displayKey} · #${valueIdx + 1}`
                          onCopyCompareValue(pathLabel, value)
                        }}
                        title="Click to copy value"
                      >
                        <span className={value === '—' ? 'text-muted italic' : ''}>
                          {value}
                        </span>
                      </button>
                    </td>
                  ))}
                </tr>
              )
            })}
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
  compareCopiedPath,
  onCopyCompareValue,
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
            className={SECTION_ACTION_BUTTON_CLASS}
            onClick={onReload}
            disabled={compareMetaState === 'loading'}
          >
            {compareMetaState === 'loading' ? 'Loading…' : 'Reload'}
          </button>
          <button
            className={SECTION_ACTION_BUTTON_CLASS}
            onClick={onToggleCompareIncludePilInfo}
            disabled={!compareMetaLoaded}
          >
            {compareIncludePilInfo ? 'Hide PIL info' : 'Include PIL info'}
          </button>
        </div>
      )}
    >
      <div className="space-y-2 text-[11px]">
        {compareMetaState === 'loading' && (
          <div className="text-muted">Loading metadata…</div>
        )}
        {compareMetaState === 'error' && compareMetaError && (
          <div className="text-danger break-words">{compareMetaError}</div>
        )}

        {compareMetaLoaded && compareMatrix && (
          <div className="space-y-2">
            <CompareMatrixTable
              matrix={compareMatrix}
              compareCopiedPath={compareCopiedPath}
              onCopyCompareValue={onCopyCompareValue}
            />
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
                  className="max-w-[50%] truncate rounded border border-border/60 bg-surface-inset px-2 py-0.5 text-[11px] text-muted"
                  title={column.path}
                >
                  {`#${idx + 1} ${column.label}`}
                </span>
              ))}
            </div>
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
          </div>
        )}
      </div>
    </InspectorSection>
  )
}

export const CompareMetadataSection = React.memo(CompareMetadataSectionComponent)

CompareMetadataSection.displayName = 'CompareMetadataSection'

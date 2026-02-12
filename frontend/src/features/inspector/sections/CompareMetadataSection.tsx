import React from 'react'
import type { CompareMetadataDiffResult, JsonRenderNode, MetadataPathSegment } from '../model/metadataCompare'
import { JsonRenderCode } from './JsonRenderCode'
import { InspectorSection } from './InspectorSection'

type CompareMetaState = 'idle' | 'loading' | 'loaded' | 'error'

interface CompareMetadataSectionProps {
  open: boolean
  onToggle: () => void
  compareMetaState: CompareMetaState
  compareMetaError: string | null
  compareLabelA: string
  compareLabelB: string
  compareIncludePilInfo: boolean
  onToggleCompareIncludePilInfo: () => void
  onReload: () => void
  compareDiff: CompareMetadataDiffResult | null
  compareHasPilInfoA: boolean
  compareHasPilInfoB: boolean
  compareShowPilInfoA: boolean
  compareShowPilInfoB: boolean
  onToggleCompareShowPilInfoA: () => void
  onToggleCompareShowPilInfoB: () => void
  compareMetaCopied: 'A' | 'B' | null
  onCopyCompareMetadata: (side: 'A' | 'B') => void
  compareValueCopiedPathA: string | null
  compareValueCopiedPathB: string | null
  compareDisplayNodeA: JsonRenderNode | null
  compareDisplayNodeB: JsonRenderNode | null
  compareMetaContent: string
  onCompareMetaPathCopyA: (path: MetadataPathSegment[]) => void
  onCompareMetaPathCopyB: (path: MetadataPathSegment[]) => void
  compareExportLabelsText: string
  onCompareExportLabelsTextChange: (value: string) => void
  compareExportEmbedMetadata: boolean
  onCompareExportEmbedMetadataChange: (checked: boolean) => void
  compareExportBusy: boolean
  compareReady: boolean
  compareExportMode: 'normal' | 'reverse' | null
  onComparisonExport: (reverseOrder: boolean) => void
  compareExportError: string | null
}

interface CompareDiffTableProps {
  compareDiff: CompareMetadataDiffResult
}

interface CompareMetadataPaneProps {
  side: 'A' | 'B'
  compareMetaLoaded: boolean
  hasPilInfo: boolean
  showPilInfo: boolean
  onToggleShowPilInfo: () => void
  copied: boolean
  onCopy: () => void
  copiedPath: string | null
  displayNode: JsonRenderNode | null
  compareMetaContent: string
  onMetaPathCopy: (path: MetadataPathSegment[]) => void
}

const CompareDiffTable = React.memo(function CompareDiffTable({
  compareDiff,
}: CompareDiffTableProps): JSX.Element {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-muted">
        <span>
          {compareDiff.different}
          {' '}
          different
          {' '}
          ·
          {' '}
          {compareDiff.onlyA}
          {' '}
          only A
          {' '}
          ·
          {' '}
          {compareDiff.onlyB}
          {' '}
          only B
        </span>
        <span className="text-[10px] uppercase tracking-wide">Deep paths</span>
      </div>
      {compareDiff.entries.length === 0 ? (
        <div className="text-muted">No differences found.</div>
      ) : (
        <div className="space-y-2">
          <div className="grid grid-cols-[minmax(80px,_1fr)_minmax(0,_1fr)_minmax(0,_1fr)] gap-2 text-[10px] uppercase tracking-wide text-muted">
            <div>Path</div>
            <div>A</div>
            <div>B</div>
          </div>
          {compareDiff.entries.map((entry) => (
            <div
              key={entry.key}
              className="grid grid-cols-[minmax(80px,_1fr)_minmax(0,_1fr)_minmax(0,_1fr)] gap-2"
            >
              <div className="text-[11px] text-muted font-mono break-all">{entry.key}</div>
              <div className="text-[11px] font-mono bg-surface-inset border border-border/60 rounded px-2 py-1 whitespace-pre-wrap break-words max-h-32 overflow-auto">
                {entry.aText}
              </div>
              <div className="text-[11px] font-mono bg-surface-inset border border-border/60 rounded px-2 py-1 whitespace-pre-wrap break-words max-h-32 overflow-auto">
                {entry.bText}
              </div>
            </div>
          ))}
          {compareDiff.truncatedCount > 0 && (
            <div className="text-muted text-[11px]">
              +
              {compareDiff.truncatedCount}
              {' '}
              more differences not shown.
            </div>
          )}
        </div>
      )}
    </div>
  )
})

CompareDiffTable.displayName = 'CompareDiffTable'

const CompareMetadataPane = React.memo(function CompareMetadataPane({
  side,
  compareMetaLoaded,
  hasPilInfo,
  showPilInfo,
  onToggleShowPilInfo,
  copied,
  onCopy,
  copiedPath,
  displayNode,
  compareMetaContent,
  onMetaPathCopy,
}: CompareMetadataPaneProps): JSX.Element {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="text-[10px] uppercase tracking-wide text-muted">
          Metadata
          {' '}
          {side}
        </div>
        <div className="flex items-center gap-2 text-xs">
          {hasPilInfo && (
            <button
              className="px-2 py-1 bg-transparent text-muted border border-border/60 rounded-md disabled:opacity-60 hover:border-border hover:text-text transition-colors"
              onClick={onToggleShowPilInfo}
              disabled={!compareMetaLoaded}
            >
              {showPilInfo ? 'Hide PIL info' : 'Show PIL info'}
            </button>
          )}
          <button
            className="px-2 py-1 bg-transparent text-muted border border-border/60 rounded-md disabled:opacity-60 hover:border-border hover:text-text transition-colors min-w-[70px]"
            onClick={onCopy}
            disabled={!compareMetaLoaded}
          >
            {copied ? 'Copied' : 'Copy'}
          </button>
        </div>
      </div>
      <div className="relative">
        {copiedPath && (
          <div className="ui-json-key-toast">
            Copied value:
            {' '}
            {copiedPath}
          </div>
        )}
        <pre
          className="ui-code-block ui-code-block-resizable h-40 overflow-auto whitespace-pre-wrap"
        >
          {compareMetaLoaded && displayNode ? (
            <JsonRenderCode node={displayNode} onPathClick={onMetaPathCopy} />
          ) : compareMetaContent}
        </pre>
      </div>
    </div>
  )
})

CompareMetadataPane.displayName = 'CompareMetadataPane'

function CompareMetadataSectionComponent({
  open,
  onToggle,
  compareMetaState,
  compareMetaError,
  compareLabelA,
  compareLabelB,
  compareIncludePilInfo,
  onToggleCompareIncludePilInfo,
  onReload,
  compareDiff,
  compareHasPilInfoA,
  compareHasPilInfoB,
  compareShowPilInfoA,
  compareShowPilInfoB,
  onToggleCompareShowPilInfoA,
  onToggleCompareShowPilInfoB,
  compareMetaCopied,
  onCopyCompareMetadata,
  compareValueCopiedPathA,
  compareValueCopiedPathB,
  compareDisplayNodeA,
  compareDisplayNodeB,
  compareMetaContent,
  onCompareMetaPathCopyA,
  onCompareMetaPathCopyB,
  compareExportLabelsText,
  onCompareExportLabelsTextChange,
  compareExportEmbedMetadata,
  onCompareExportEmbedMetadataChange,
  compareExportBusy,
  compareReady,
  compareExportMode,
  onComparisonExport,
  compareExportError,
}: CompareMetadataSectionProps): JSX.Element {
  const compareMetaLoaded = compareMetaState === 'loaded'

  return (
    <InspectorSection
      title="Compare Metadata"
      open={open}
      onToggle={onToggle}
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
        <div className="grid grid-cols-2 gap-2 text-[11px] text-muted">
          <div>
            <div className="uppercase tracking-wide text-[10px]">A</div>
            <div className="text-text break-all" title={compareLabelA}>
              {compareLabelA}
            </div>
          </div>
          <div>
            <div className="uppercase tracking-wide text-[10px]">B</div>
            <div className="text-text break-all" title={compareLabelB}>
              {compareLabelB}
            </div>
          </div>
        </div>

        {compareMetaState === 'loading' && (
          <div className="text-muted">Loading metadata…</div>
        )}
        {compareMetaState === 'error' && compareMetaError && (
          <div className="text-danger break-words">{compareMetaError}</div>
        )}

        {compareMetaLoaded && compareDiff && <CompareDiffTable compareDiff={compareDiff} />}

        <div className="grid gap-3 pt-2">
          <CompareMetadataPane
            side="A"
            compareMetaLoaded={compareMetaLoaded}
            hasPilInfo={compareHasPilInfoA}
            showPilInfo={compareShowPilInfoA}
            onToggleShowPilInfo={onToggleCompareShowPilInfoA}
            copied={compareMetaCopied === 'A'}
            onCopy={() => onCopyCompareMetadata('A')}
            copiedPath={compareValueCopiedPathA}
            displayNode={compareDisplayNodeA}
            compareMetaContent={compareMetaContent}
            onMetaPathCopy={onCompareMetaPathCopyA}
          />
          <CompareMetadataPane
            side="B"
            compareMetaLoaded={compareMetaLoaded}
            hasPilInfo={compareHasPilInfoB}
            showPilInfo={compareShowPilInfoB}
            onToggleShowPilInfo={onToggleCompareShowPilInfoB}
            copied={compareMetaCopied === 'B'}
            onCopy={() => onCopyCompareMetadata('B')}
            copiedPath={compareValueCopiedPathB}
            displayNode={compareDisplayNodeB}
            compareMetaContent={compareMetaContent}
            onMetaPathCopy={onCompareMetaPathCopyB}
          />
        </div>

        <div className="space-y-2 rounded-md border border-border/60 bg-surface-inset/40 p-3">
          <div className="text-[10px] uppercase tracking-wide text-muted">Export Comparison</div>
          <textarea
            className="ui-textarea inspector-input w-full h-20 scrollbar-thin"
            placeholder={'Label for A\nLabel for B'}
            value={compareExportLabelsText}
            onChange={(e) => onCompareExportLabelsTextChange(e.target.value)}
            disabled={compareExportBusy}
            aria-label="Comparison export labels"
          />
          <label className="inline-flex items-center gap-2 text-[11px] text-muted">
            <input
              type="checkbox"
              checked={compareExportEmbedMetadata}
              onChange={(e) => onCompareExportEmbedMetadataChange(e.target.checked)}
              disabled={compareExportBusy}
            />
            <span>Embed metadata</span>
          </label>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => onComparisonExport(false)}
              disabled={!compareReady || compareExportBusy}
            >
              {compareExportMode === 'normal' ? 'Exporting…' : 'Export comparison'}
            </button>
            <button
              type="button"
              className="btn btn-sm btn-ghost"
              onClick={() => onComparisonExport(true)}
              disabled={!compareReady || compareExportBusy}
            >
              {compareExportMode === 'reverse' ? 'Exporting…' : 'Export (reverse order)'}
            </button>
          </div>
          {compareExportError && (
            <div className="text-danger break-words">{compareExportError}</div>
          )}
        </div>
      </div>
    </InspectorSection>
  )
}

export const CompareMetadataSection = React.memo(CompareMetadataSectionComponent)

CompareMetadataSection.displayName = 'CompareMetadataSection'

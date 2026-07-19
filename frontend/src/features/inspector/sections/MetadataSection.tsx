import React from 'react'
import type { JsonRenderNode, MetadataPathSegment } from '../model/metadataCompare'
import type { InspectorWidgetId } from '../model/inspectorWidgetOrder'
import { JsonRenderCode } from './JsonRenderCode'
import { InspectorSection } from './InspectorSection'

interface MetadataSectionProps {
  open: boolean
  onToggle: () => void
  metadataLoading: boolean
  metadataActionLabel: string
  metadataActionAriaLabel: string
  onMetadataAction: () => void
  metadataActionDisabled: boolean
  hasPilInfo: boolean
  showPilInfo: boolean
  onToggleShowPilInfo: () => void
  metaValueCopiedPath: string | null
  metaHeightClass: string
  metaLoaded: boolean
  metaDisplayNode: JsonRenderNode | null
  metaContent: string
  metaError: string | null
  onMetaPathCopy: (path: MetadataPathSegment[]) => void
  transitionStatusVisible?: boolean
  sortableId?: InspectorWidgetId
  sortableEnabled?: boolean
}

function MetadataSectionComponent({
  open,
  onToggle,
  metadataLoading,
  metadataActionLabel,
  metadataActionAriaLabel,
  onMetadataAction,
  metadataActionDisabled,
  hasPilInfo,
  showPilInfo,
  onToggleShowPilInfo,
  metaValueCopiedPath,
  metaHeightClass,
  metaLoaded,
  metaDisplayNode,
  metaContent,
  metaError,
  onMetaPathCopy,
  transitionStatusVisible = false,
  sortableId,
  sortableEnabled = false,
}: MetadataSectionProps): JSX.Element {
  const metadataActions = (
    <div className="flex items-center gap-2 text-xs">
      <button
        className={`px-2 py-1 bg-transparent text-muted border border-border/60 rounded-md disabled:opacity-60 hover:border-border hover:text-text transition-colors ${metaLoaded && hasPilInfo ? '' : 'invisible'}`}
        onClick={onToggleShowPilInfo}
        disabled={!metaLoaded || !hasPilInfo}
        aria-hidden={!metaLoaded || !hasPilInfo}
      >
        {showPilInfo ? 'Hide PIL info' : 'Show PIL info'}
      </button>
      <button
        className="px-2 py-1 bg-transparent text-muted border border-border/60 rounded-md disabled:opacity-60 hover:border-border hover:text-text transition-colors min-w-[78px]"
        onClick={onMetadataAction}
        disabled={metadataActionDisabled || metadataLoading}
        aria-label={metadataActionAriaLabel}
      >
        {metadataActionLabel}
      </button>
    </div>
  )

  return (
    <InspectorSection
      title="Metadata"
      open={open}
      onToggle={onToggle}
      sortableId={sortableId}
      sortableEnabled={sortableEnabled}
      actions={metadataActions}
    >
      <div className="relative">
        <div
          className={`absolute right-2 top-2 z-10 rounded bg-surface px-1.5 py-0.5 text-[11px] text-muted ${transitionStatusVisible ? '' : 'invisible'}`}
          role="status"
        >
          {transitionStatusVisible ? 'Loading metadata…' : ''}
        </div>
        {metaValueCopiedPath && (
          <div className="ui-json-key-toast">
            Copied value:
            {' '}
            {metaValueCopiedPath}
          </div>
        )}
        <pre
          className={`ui-code-block ui-code-block-resizable ${metaHeightClass} overflow-auto whitespace-pre-wrap`}
        >
          {metaLoaded ? (
            metaDisplayNode ? (
              <JsonRenderCode node={metaDisplayNode} onPathClick={onMetaPathCopy} />
            ) : <span className="font-sans text-[12px]">{metaContent}</span>
          ) : <span className="font-sans text-[12px]">{metaContent}</span>}
        </pre>
        <div
          className={`pointer-events-none absolute bottom-1 left-2 right-2 truncate rounded bg-surface px-1 text-[11px] text-danger ${metaError ? '' : 'invisible'}`}
          role="status"
          title={metaError ?? undefined}
        >
          {metaError ?? ''}
        </div>
      </div>
    </InspectorSection>
  )
}

export const MetadataSection = React.memo(MetadataSectionComponent)

MetadataSection.displayName = 'MetadataSection'

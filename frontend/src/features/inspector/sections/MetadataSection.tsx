import React from 'react'
import type { JsonRenderNode, MetadataPathSegment } from '../model/metadataCompare'
import { JsonRenderCode } from './JsonRenderCode'
import { InspectorSection } from './InspectorSection'

interface MetadataSectionProps {
  open: boolean
  onToggle: () => void
  metadataLoading: boolean
  metadataActionLabel: string
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
}

function MetadataSectionComponent({
  open,
  onToggle,
  metadataLoading,
  metadataActionLabel,
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
}: MetadataSectionProps): JSX.Element {
  const metadataActions = (
    <div className="flex items-center gap-2 text-xs">
      {metaLoaded && hasPilInfo && (
        <button
          className="px-2 py-1 bg-transparent text-muted border border-border/60 rounded-md disabled:opacity-60 hover:border-border hover:text-text transition-colors"
          onClick={onToggleShowPilInfo}
          disabled={!metaLoaded}
        >
          {showPilInfo ? 'Hide PIL info' : 'Show PIL info'}
        </button>
      )}
      <button
        className="px-2 py-1 bg-transparent text-muted border border-border/60 rounded-md disabled:opacity-60 hover:border-border hover:text-text transition-colors min-w-[78px]"
        onClick={onMetadataAction}
        disabled={metadataActionDisabled || metadataLoading}
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
      actions={metadataActions}
    >
      <div className="relative">
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
            ) : metaContent
          ) : metaContent}
        </pre>
      </div>
      {metaError && <div className="text-[11px] text-danger mt-1 break-words">{metaError}</div>}
    </InspectorSection>
  )
}

export const MetadataSection = React.memo(MetadataSectionComponent)

MetadataSection.displayName = 'MetadataSection'

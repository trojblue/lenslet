import { Fragment, type ComponentProps, type JSX } from 'react'
import { fmtBytes } from '../../../lib/util'
import type { InspectorWidgetId } from '../model/inspectorWidgetOrder'
import { InspectorSection } from './InspectorSection'
import { SelectionActionsSection } from './SelectionActionsSection'
import { SelectionExportSection } from './SelectionExportSection'

interface OverviewSectionProps {
  open: boolean
  onToggle: () => void
  multi: boolean
  selectedCount: number
  totalSize: number
  filename: string
  viewerCompareActive: boolean
  metadataCompareActive: boolean
  metadataCompareAvailable: boolean
  onOpenCompare?: () => void
  onToggleMetadataCompare?: () => void
  compareExportLabelsText: string
  onCompareExportLabelsTextChange: (value: string) => void
  compareExportEmbedMetadata: boolean
  onCompareExportEmbedMetadataChange: (checked: boolean) => void
  compareExportReverseOrder: boolean
  onCompareExportReverseOrderChange: (checked: boolean) => void
  compareExportHighQualityGif: boolean
  onCompareExportHighQualityGifChange: (checked: boolean) => void
  compareExportBusy: boolean
  compareExportMode: 'png' | 'gif' | null
  onComparisonExport: (outputFormat: 'png' | 'gif') => void
  compareExportError: string | null
  onFindSimilar?: () => void
  canFindSimilar: boolean
  findSimilarDisabledReason: string | null
  sortableId?: InspectorWidgetId
  sortableEnabled?: boolean
}

type OverviewWidgetId = 'selectionActions' | 'selectionExport'

interface OverviewWidgetContext {
  viewerCompareActive: boolean
  selectionActionsProps: ComponentProps<typeof SelectionActionsSection>
  selectionExportProps: ComponentProps<typeof SelectionExportSection>
}

interface OverviewWidgetDefinition {
  id: OverviewWidgetId
  isVisible: (ctx: OverviewWidgetContext) => boolean
  render: (ctx: OverviewWidgetContext) => JSX.Element
}

const OVERVIEW_WIDGETS: readonly OverviewWidgetDefinition[] = [
  {
    id: 'selectionActions',
    isVisible: () => true,
    render: ({ selectionActionsProps }) => <SelectionActionsSection {...selectionActionsProps} />,
  },
  {
    id: 'selectionExport',
    isVisible: ({ viewerCompareActive }) => !viewerCompareActive,
    render: ({ selectionExportProps }) => <SelectionExportSection {...selectionExportProps} />,
  },
]

export function OverviewSection({
  open,
  onToggle,
  multi,
  selectedCount,
  totalSize,
  filename,
  viewerCompareActive,
  metadataCompareActive,
  metadataCompareAvailable,
  onOpenCompare,
  onToggleMetadataCompare,
  compareExportLabelsText,
  onCompareExportLabelsTextChange,
  compareExportEmbedMetadata,
  onCompareExportEmbedMetadataChange,
  compareExportReverseOrder,
  onCompareExportReverseOrderChange,
  compareExportHighQualityGif,
  onCompareExportHighQualityGifChange,
  compareExportBusy,
  compareExportMode,
  onComparisonExport,
  compareExportError,
  onFindSimilar,
  canFindSimilar,
  findSimilarDisabledReason,
  sortableId,
  sortableEnabled = false,
}: OverviewSectionProps): JSX.Element {
  const widgetContext: OverviewWidgetContext = {
    viewerCompareActive,
    selectionActionsProps: {
      selectedCount,
      viewerCompareActive,
      metadataCompareActive,
      metadataCompareAvailable,
      onOpenCompare,
      onToggleMetadataCompare,
    },
    selectionExportProps: {
      selectedCount,
      compareExportLabelsText,
      onCompareExportLabelsTextChange,
      compareExportEmbedMetadata,
      onCompareExportEmbedMetadataChange,
      compareExportReverseOrder,
      onCompareExportReverseOrderChange,
      compareExportHighQualityGif,
      onCompareExportHighQualityGifChange,
      compareExportBusy,
      compareExportMode,
      onComparisonExport,
      compareExportError,
    },
  }

  return (
    <InspectorSection
      title={multi ? 'Selection' : 'Item'}
      open={open}
      onToggle={onToggle}
      sortableId={sortableId}
      sortableEnabled={sortableEnabled}
      contentClassName="px-3 pb-3 space-y-2"
      actions={onFindSimilar && (
        <button
          type="button"
          className="btn btn-sm"
          onClick={onFindSimilar}
          disabled={!canFindSimilar}
          title={findSimilarDisabledReason ?? 'Find similar'}
        >
          Find similar
        </button>
      )}
    >
      {multi ? (
        <div className="space-y-2">
          <div className="grid grid-cols-2 gap-2">
            <div className="inspector-field">
              <div className="inspector-field-label">Selected</div>
              <div className="inspector-field-value">{selectedCount} files</div>
            </div>
            <div className="inspector-field">
              <div className="inspector-field-label">Total size</div>
              <div className="inspector-field-value">{fmtBytes(totalSize)}</div>
            </div>
          </div>
          {OVERVIEW_WIDGETS.filter((widget) => widget.isVisible(widgetContext)).map((widget) => (
            <Fragment key={widget.id}>{widget.render(widgetContext)}</Fragment>
          ))}
        </div>
      ) : (
        <div className="inspector-field">
          <div className="inspector-field-label">Filename</div>
          <div className="inspector-field-value break-all" title={filename}>
            {filename}
          </div>
        </div>
      )}
      {findSimilarDisabledReason && (
        <div className="text-[11px] text-muted">{findSimilarDisabledReason}</div>
      )}
    </InspectorSection>
  )
}

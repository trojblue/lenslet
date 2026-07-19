import DerivedScoreCard from './components/DerivedScoreCard'
import type {
  BrowseFacetsPayload,
  BrowseFacetFields,
  BrowseItemPayload,
  DerivedMetricSpec,
  MetricDisplayNames,
} from '../../lib/types'
import type { DerivedMetricEvaluation } from './model/derivedMetric'
import type {
  FacetFieldQueryStates,
  FacetQueryState,
} from './model/facetPresentation'

interface DerivedScorePanelProps {
  active?: boolean
  items: BrowseItemPayload[]
  metricKeys: string[]
  categoricalKeys: string[]
  metricDisplayNames?: MetricDisplayNames | null
  facets?: BrowseFacetsPayload | null
  facetsState?: FacetQueryState
  facetFieldStates?: FacetFieldQueryStates
  populationItemsComplete?: boolean
  presentationResetKey?: string
  draftResetKey?: string
  derivedMetric: DerivedMetricEvaluation
  backendAuthoritative?: boolean
  derivedRankDisabledReason?: string | null
  onApplyDerivedMetric: (spec: DerivedMetricSpec | null) => void
  onRankByDerivedMetric: (spec: DerivedMetricSpec) => void
  onFacetFieldsChange?: (fields: BrowseFacetFields) => void
}

export default function DerivedScorePanel({
  active = true,
  items,
  metricKeys,
  categoricalKeys,
  metricDisplayNames,
  facets = null,
  facetsState = 'settled',
  facetFieldStates,
  populationItemsComplete = true,
  presentationResetKey = 'default',
  draftResetKey = 'default',
  derivedMetric,
  backendAuthoritative = false,
  derivedRankDisabledReason,
  onApplyDerivedMetric,
  onRankByDerivedMetric,
  onFacetFieldsChange,
}: DerivedScorePanelProps): JSX.Element {
  return (
    <div className="h-full flex flex-col gap-3 p-3 overflow-auto scrollbar-thin">
      <DerivedScoreCard
        active={active}
        items={items}
        metricKeys={metricKeys}
        categoricalKeys={categoricalKeys}
        metricDisplayNames={metricDisplayNames}
        facets={facets}
        facetsState={facetsState}
        facetFieldStates={facetFieldStates}
        populationItemsComplete={populationItemsComplete}
        presentationResetKey={presentationResetKey}
        draftResetKey={draftResetKey}
        derivedMetric={derivedMetric}
        backendAuthoritative={backendAuthoritative}
        rankDisabledReason={derivedRankDisabledReason}
        onApplyDerivedMetric={onApplyDerivedMetric}
        onRankByDerivedMetric={onRankByDerivedMetric}
        onFacetFieldsChange={onFacetFieldsChange}
      />
    </div>
  )
}

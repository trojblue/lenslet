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
  items: BrowseItemPayload[]
  metricKeys: string[]
  categoricalKeys: string[]
  metricDisplayNames?: MetricDisplayNames | null
  facets?: BrowseFacetsPayload | null
  facetsState?: FacetQueryState
  facetFieldStates?: FacetFieldQueryStates
  populationItemsComplete?: boolean
  derivedMetric: DerivedMetricEvaluation
  backendAuthoritative?: boolean
  derivedRankDisabledReason?: string | null
  onApplyDerivedMetric: (spec: DerivedMetricSpec | null) => void
  onRankByDerivedMetric: (spec: DerivedMetricSpec) => void
  onFacetFieldsChange?: (fields: BrowseFacetFields) => void
}

export default function DerivedScorePanel({
  items,
  metricKeys,
  categoricalKeys,
  metricDisplayNames,
  facets = null,
  facetsState = 'settled',
  facetFieldStates,
  populationItemsComplete = true,
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
        items={items}
        metricKeys={metricKeys}
        categoricalKeys={categoricalKeys}
        metricDisplayNames={metricDisplayNames}
        facets={facets}
        facetsState={facetsState}
        facetFieldStates={facetFieldStates}
        populationItemsComplete={populationItemsComplete}
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

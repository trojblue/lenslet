import DerivedScoreCard from './components/DerivedScoreCard'
import type {
  BrowseFacetsPayload,
  BrowseFacetFields,
  BrowseItemPayload,
  DerivedMetricSpec,
  MetricDisplayNames,
} from '../../lib/types'
import type { DerivedMetricEvaluation } from './model/derivedMetric'

interface DerivedScorePanelProps {
  items: BrowseItemPayload[]
  metricKeys: string[]
  categoricalKeys: string[]
  metricDisplayNames?: MetricDisplayNames | null
  facets?: BrowseFacetsPayload | null
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
        categoricalValuesByKey={categoricalValuesFromFacets(facets, categoricalKeys)}
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

function categoricalValuesFromFacets(
  facets: BrowseFacetsPayload | null,
  categoricalKeys: readonly string[],
): Map<string, string[]> | undefined {
  if (!facets) return undefined
  return new Map(categoricalKeys.map((key) => [
    key,
    (facets.categoricals[key]?.values ?? []).map((entry) => entry.value),
  ]))
}

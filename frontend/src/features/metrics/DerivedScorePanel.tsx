import DerivedScoreCard from './components/DerivedScoreCard'
import type {
  BrowseFacetsPayload,
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
  derivedRankDisabledReason?: string | null
  onApplyDerivedMetric: (spec: DerivedMetricSpec | null) => void
  onRankByDerivedMetric: (spec: DerivedMetricSpec) => void
}

export default function DerivedScorePanel({
  items,
  metricKeys,
  categoricalKeys,
  metricDisplayNames,
  facets = null,
  derivedMetric,
  derivedRankDisabledReason,
  onApplyDerivedMetric,
  onRankByDerivedMetric,
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
        rankDisabledReason={derivedRankDisabledReason}
        onApplyDerivedMetric={onApplyDerivedMetric}
        onRankByDerivedMetric={onRankByDerivedMetric}
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

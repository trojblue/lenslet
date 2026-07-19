import type { BrowseFacetFields } from '../../../lib/types'

export type FacetDemandKind = 'metric' | 'categorical'

type FacetBatchOwner = {
  resetKey: string | null
  schemaKey: string | null
  schemaRevision: number | null
  keys: string[]
}

export type MetricsFacetDemandOwner = {
  metric: {
    showAll: boolean
    batch: FacetBatchOwner
  }
  categorical: {
    showAll: boolean
    selectedKey: string | null
    batch: FacetBatchOwner
  }
}

export type MetricsFacetDemand = {
  metric: {
    showAll: boolean
    schemaRevision: number
    visibleKeys: string[]
  }
  categorical: {
    showAll: boolean
    schemaRevision: number
    selectedKey: string | null
    visibleKeys: string[]
  }
}

export type MetricsFacetDemandAction =
  | { type: 'select-categorical'; key: string }
  | { type: 'set-show-all'; kind: FacetDemandKind; showAll: boolean }
  | {
      type: 'set-visible-keys'
      kind: FacetDemandKind
      schemaKey: string
      schemaRevision: number
      keys: string[]
    }

export const INITIAL_METRICS_FACET_DEMAND_OWNER: MetricsFacetDemandOwner = {
  metric: {
    showAll: false,
    batch: { resetKey: null, schemaKey: null, schemaRevision: null, keys: [] },
  },
  categorical: {
    showAll: false,
    selectedKey: null,
    batch: { resetKey: null, schemaKey: null, schemaRevision: null, keys: [] },
  },
}

export function alignedFacetBatchKeys(
  keys: readonly string[],
  visibleIndices: readonly number[],
  batchSize = 24,
): string[] {
  if (!visibleIndices.length) return []
  const safeBatchSize = Math.max(1, Math.floor(batchSize))
  const batches = new Set(visibleIndices.map((index) => (
    Math.floor(index / safeBatchSize) * safeBatchSize
  )))
  return Array.from(batches)
    .sort((a, b) => a - b)
    .flatMap((start) => keys.slice(start, start + safeBatchSize))
}

export function initialFacetBatchKeys(
  keys: readonly string[],
  batchSize = 24,
): string[] {
  return keys.slice(0, Math.max(1, Math.floor(batchSize)))
}

export function facetSchemaKey(keys: readonly string[]): string {
  return JSON.stringify(keys)
}

export function resolveVisibleFacetBatch(
  keys: readonly string[],
  retainedKeys: readonly string[],
  compatible: boolean,
  batchSize = 24,
): string[] {
  return compatible
    && retainedKeys.length > 0
    && retainedKeys.every((key) => keys.includes(key))
    ? [...retainedKeys]
    : initialFacetBatchKeys(keys, batchSize)
}

export function resolveMetricsFacetDemand(
  owner: MetricsFacetDemandOwner,
  resetKey: string,
  metricKeys: readonly string[],
  categoricalKeys: readonly string[],
  schemaRevisions: { metric: number; categorical: number } = { metric: 0, categorical: 0 },
): MetricsFacetDemand {
  const selectedCategorical = owner.categorical.selectedKey
  return {
    metric: {
      showAll: owner.metric.showAll,
      schemaRevision: schemaRevisions.metric,
      visibleKeys: resolveVisibleFacetBatch(
        metricKeys,
        owner.metric.batch.keys,
        owner.metric.batch.resetKey === resetKey
          && owner.metric.batch.schemaKey === facetSchemaKey(metricKeys)
          && owner.metric.batch.schemaRevision === schemaRevisions.metric,
      ),
    },
    categorical: {
      showAll: owner.categorical.showAll,
      schemaRevision: schemaRevisions.categorical,
      selectedKey: selectedCategorical && categoricalKeys.includes(selectedCategorical)
        ? selectedCategorical
        : categoricalKeys[0] ?? null,
      visibleKeys: resolveVisibleFacetBatch(
        categoricalKeys,
        owner.categorical.batch.keys,
        owner.categorical.batch.resetKey === resetKey
          && owner.categorical.batch.schemaKey === facetSchemaKey(categoricalKeys)
          && owner.categorical.batch.schemaRevision === schemaRevisions.categorical,
      ),
    },
  }
}

export function resolveMetricsFacetFields(
  demand: MetricsFacetDemand,
  selectedMetric: string | undefined,
  metricKeys: readonly string[],
  categoricalKeys: readonly string[],
): BrowseFacetFields {
  const activeMetric = selectedMetric && metricKeys.includes(selectedMetric)
    ? selectedMetric
    : metricKeys[0]
  const activeCategorical = demand.categorical.selectedKey
    && categoricalKeys.includes(demand.categorical.selectedKey)
    ? demand.categorical.selectedKey
    : categoricalKeys[0]
  return {
    metric_keys: demand.metric.showAll
      ? demand.metric.visibleKeys
      : activeMetric ? [activeMetric] : [],
    categorical_keys: demand.categorical.showAll
      ? demand.categorical.visibleKeys
      : activeCategorical ? [activeCategorical] : [],
  }
}

export function updateMetricsFacetDemandOwner(
  owner: MetricsFacetDemandOwner,
  action: MetricsFacetDemandAction,
  resetKey: string,
): MetricsFacetDemandOwner {
  if (action.type === 'select-categorical') {
    if (owner.categorical.selectedKey === action.key) return owner
    return {
      ...owner,
      categorical: { ...owner.categorical, selectedKey: action.key },
    }
  }
  if (action.type === 'set-show-all') {
    if (owner[action.kind].showAll === action.showAll) return owner
    return action.kind === 'metric'
      ? { ...owner, metric: { ...owner.metric, showAll: action.showAll } }
      : { ...owner, categorical: { ...owner.categorical, showAll: action.showAll } }
  }
  const batch = owner[action.kind].batch
  if (
    batch.resetKey === resetKey
    && batch.schemaKey === action.schemaKey
    && batch.schemaRevision === action.schemaRevision
    && equalKeys(batch.keys, action.keys)
  ) return owner
  return action.kind === 'metric'
    ? {
        ...owner,
        metric: {
          ...owner.metric,
          batch: {
            resetKey,
            schemaKey: action.schemaKey,
            schemaRevision: action.schemaRevision,
            keys: [...action.keys],
          },
        },
      }
    : {
        ...owner,
        categorical: {
          ...owner.categorical,
          batch: {
            resetKey,
            schemaKey: action.schemaKey,
            schemaRevision: action.schemaRevision,
            keys: [...action.keys],
          },
        },
      }
}

function equalKeys(left: readonly string[], right: readonly string[]): boolean {
  return left.length === right.length && left.every((key, index) => key === right[index])
}

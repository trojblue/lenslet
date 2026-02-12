import type { FilterAST, FilterClause } from '../../lib/types'
import { formatDateRange, formatRange, formatStarValues } from '../utils/appShellHelpers'

export type FilterChip = {
  id: string
  label: string
  onRemove: () => void
}

export type FilterChipActions = {
  clearStars: () => void
  clearStarsNotIn: () => void
  clearNameContains: () => void
  clearNameNotContains: () => void
  clearCommentsContains: () => void
  clearCommentsNotContains: () => void
  clearUrlContains: () => void
  clearUrlNotContains: () => void
  clearDateRange: () => void
  clearWidthCompare: () => void
  clearHeightCompare: () => void
  clearMetricRange: (key: string) => void
}

type FilterChipTemplate = {
  id: string
  label: string
}

type FilterClauseKey =
  | 'stars'
  | 'starsIn'
  | 'starsNotIn'
  | 'nameContains'
  | 'nameNotContains'
  | 'commentsContains'
  | 'commentsNotContains'
  | 'urlContains'
  | 'urlNotContains'
  | 'dateRange'
  | 'widthCompare'
  | 'heightCompare'
  | 'metricRange'

type FilterClauseByKey<K extends FilterClauseKey> = Extract<FilterClause, Record<K, unknown>>

type FilterChipRegistryEntry<K extends FilterClauseKey> = {
  read: (clause: FilterClauseByKey<K>) => FilterChipTemplate | null
  clear: (clause: FilterClauseByKey<K>, actions: FilterChipActions) => void
}

const FILTER_CHIP_REGISTRY: { [K in FilterClauseKey]: FilterChipRegistryEntry<K> } = {
  stars: {
    read: (clause) => {
      const stars = clause.stars || []
      if (!stars.length) return null
      return {
        id: 'stars',
        label: `Rating in: ${formatStarValues(stars)}`,
      }
    },
    clear: (_clause, actions) => actions.clearStars(),
  },
  starsIn: {
    read: (clause) => {
      const stars = clause.starsIn.values || []
      if (!stars.length) return null
      return {
        id: 'stars-in',
        label: `Rating in: ${formatStarValues(stars)}`,
      }
    },
    clear: (_clause, actions) => actions.clearStars(),
  },
  starsNotIn: {
    read: (clause) => {
      const stars = clause.starsNotIn.values || []
      if (!stars.length) return null
      return {
        id: 'stars-not-in',
        label: `Rating not in: ${formatStarValues(stars)}`,
      }
    },
    clear: (_clause, actions) => actions.clearStarsNotIn(),
  },
  nameContains: {
    read: (clause) => {
      const value = clause.nameContains.value?.trim()
      if (!value) return null
      return {
        id: 'name-contains',
        label: `Filename contains: ${value}`,
      }
    },
    clear: (_clause, actions) => actions.clearNameContains(),
  },
  nameNotContains: {
    read: (clause) => {
      const value = clause.nameNotContains.value?.trim()
      if (!value) return null
      return {
        id: 'name-not-contains',
        label: `Filename not: ${value}`,
      }
    },
    clear: (_clause, actions) => actions.clearNameNotContains(),
  },
  commentsContains: {
    read: (clause) => {
      const value = clause.commentsContains.value?.trim()
      if (!value) return null
      return {
        id: 'comments-contains',
        label: `Comments contain: ${value}`,
      }
    },
    clear: (_clause, actions) => actions.clearCommentsContains(),
  },
  commentsNotContains: {
    read: (clause) => {
      const value = clause.commentsNotContains.value?.trim()
      if (!value) return null
      return {
        id: 'comments-not-contains',
        label: `Comments not: ${value}`,
      }
    },
    clear: (_clause, actions) => actions.clearCommentsNotContains(),
  },
  urlContains: {
    read: (clause) => {
      const value = clause.urlContains.value?.trim()
      if (!value) return null
      return {
        id: 'url-contains',
        label: `URL contains: ${value}`,
      }
    },
    clear: (_clause, actions) => actions.clearUrlContains(),
  },
  urlNotContains: {
    read: (clause) => {
      const value = clause.urlNotContains.value?.trim()
      if (!value) return null
      return {
        id: 'url-not-contains',
        label: `URL not: ${value}`,
      }
    },
    clear: (_clause, actions) => actions.clearUrlNotContains(),
  },
  dateRange: {
    read: (clause) => {
      const { from, to } = clause.dateRange
      if (!from && !to) return null
      return {
        id: 'date-range',
        label: `Date: ${formatDateRange(from, to)}`,
      }
    },
    clear: (_clause, actions) => actions.clearDateRange(),
  },
  widthCompare: {
    read: (clause) => ({
      id: 'width-compare',
      label: `Width ${clause.widthCompare.op} ${clause.widthCompare.value}`,
    }),
    clear: (_clause, actions) => actions.clearWidthCompare(),
  },
  heightCompare: {
    read: (clause) => ({
      id: 'height-compare',
      label: `Height ${clause.heightCompare.op} ${clause.heightCompare.value}`,
    }),
    clear: (_clause, actions) => actions.clearHeightCompare(),
  },
  metricRange: {
    read: (clause) => ({
      id: `metric:${clause.metricRange.key}`,
      label: `${clause.metricRange.key}: ${formatRange(clause.metricRange.min, clause.metricRange.max)}`,
    }),
    clear: (clause, actions) => actions.clearMetricRange(clause.metricRange.key),
  },
}

function visitFilterClause(
  clause: FilterClause,
  visit: <K extends FilterClauseKey>(key: K, typedClause: FilterClauseByKey<K>) => void
): void {
  if ('stars' in clause) return visit('stars', clause)
  if ('starsIn' in clause) return visit('starsIn', clause)
  if ('starsNotIn' in clause) return visit('starsNotIn', clause)
  if ('nameContains' in clause) return visit('nameContains', clause)
  if ('nameNotContains' in clause) return visit('nameNotContains', clause)
  if ('commentsContains' in clause) return visit('commentsContains', clause)
  if ('commentsNotContains' in clause) return visit('commentsNotContains', clause)
  if ('urlContains' in clause) return visit('urlContains', clause)
  if ('urlNotContains' in clause) return visit('urlNotContains', clause)
  if ('dateRange' in clause) return visit('dateRange', clause)
  if ('widthCompare' in clause) return visit('widthCompare', clause)
  if ('heightCompare' in clause) return visit('heightCompare', clause)
  if ('metricRange' in clause) return visit('metricRange', clause)
}

export function buildFilterChips(filters: FilterAST, actions: FilterChipActions): FilterChip[] {
  const chips: FilterChip[] = []
  for (const clause of filters.and) {
    visitFilterClause(clause, (key, typedClause) => {
      const entry = FILTER_CHIP_REGISTRY[key]
      const template = entry.read(typedClause)
      if (!template) return
      chips.push({
        id: template.id,
        label: template.label,
        onRemove: () => entry.clear(typedClause, actions),
      })
    })
  }
  return chips
}

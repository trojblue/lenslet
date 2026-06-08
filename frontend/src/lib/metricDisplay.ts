import type { MetricDisplayNames } from './types'

export function getMetricDisplayName(
  key: string,
  displayNames?: MetricDisplayNames | null,
): string {
  const label = displayNames?.[key]?.trim()
  return label || key
}

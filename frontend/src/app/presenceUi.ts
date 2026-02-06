import type { SyncIndicatorState } from '../shared/ui/SyncIndicator'

export type IndicatorStateOptions = {
  isOffline: boolean
  isUnstable: boolean
  recentEditActive: boolean
  editingCount: number
}

export function deriveIndicatorState(options: IndicatorStateOptions): SyncIndicatorState {
  if (options.isOffline) return 'offline'
  if (options.isUnstable) return 'unstable'
  if (options.recentEditActive) return 'recent'
  if (Number.isFinite(options.editingCount) && options.editingCount > 0) return 'editing'
  return 'live'
}

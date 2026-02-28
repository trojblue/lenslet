import type { HealthResponse } from '../../lib/types'

export type AppMode = 'browse' | 'ranking'

export function deriveAppModeFromHealth(health: HealthResponse | null | undefined): AppMode {
  return health?.mode === 'ranking' ? 'ranking' : 'browse'
}


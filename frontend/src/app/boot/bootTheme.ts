import type { AppMode } from '../model/appMode'
import { loadWorkspaceThemePreset } from '../../theme/storage'
import { applyThemePreset } from '../../theme/runtime'
import type { BootHealthState } from './bootHealth'

export type AppBootState = {
  mode: AppMode
  loading: boolean
  error: string | null
}

export function applyThemeFromBootHealth(bootHealth: BootHealthState): void {
  const themePreset = loadWorkspaceThemePreset(bootHealth.workspaceId, bootHealth.healthMode)
  applyThemePreset(themePreset)
}

export function commitBootHealth(
  bootHealth: BootHealthState,
  applyTheme: (bootHealth: BootHealthState) => void,
  setBootState: (state: AppBootState) => void,
): void {
  if (bootHealth.mode !== 'ranking') {
    applyTheme(bootHealth)
  }
  setBootState({
    mode: bootHealth.mode,
    loading: false,
    error: bootHealth.error,
  })
}

import type { LaunchSessionPayload } from '../../lib/types'

export function resolveLensletDocumentTitle(launchSession?: LaunchSessionPayload | null): string {
  const label = launchSession?.title_label?.trim()
  return label ? `Lenslet · ${label}` : 'Lenslet'
}

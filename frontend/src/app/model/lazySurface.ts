export const LAZY_SURFACE_LOADING_COPY_DELAY_MS = 800
export const BOOT_LOADING_COPY_DELAY_MS = 800

export function lazySurfaceMessage(
  message: string,
  busy: boolean,
  loadingCopyVisible: boolean,
): string {
  return !busy || loadingCopyVisible ? message : '\u00a0'
}

import {
  MENU_VIEWPORT_MARGIN_PX,
  clampMenuPosition,
  type ViewportBounds,
} from '../../../lib/menuPosition'

export const HOVER_PREVIEW_VIEWPORT_WIDTH_RATIO = 0.8
export const HOVER_PREVIEW_VIEWPORT_HEIGHT_RATIO = 0.8
export const HOVER_PREVIEW_MIN_WIDTH_PX = 120
export const HOVER_PREVIEW_MIN_HEIGHT_PX = 90

export interface HoverPreviewRequest {
  promise: Promise<Blob>
  abort?: () => void
}

export type HoverPreviewFetcher = (path: string) => HoverPreviewRequest

export interface HoverPreviewRuntime {
  createObjectURL: (blob: Blob) => string
  revokeObjectURL: (url: string) => void
}

export interface HoverPreviewCallbacks {
  onReady: (result: { path: string; url: string }) => void
}

export interface HoverPreviewSurfaceSize {
  width: number
  height: number
}

export interface HoverPreviewPositionInput {
  surfaceSize: HoverPreviewSurfaceSize
  viewport: ViewportBounds
  margin?: number
}

function clampSize(value: number, min: number, max: number): number {
  if (max < min) return Math.max(1, max)
  return Math.min(max, Math.max(min, value))
}

export function getHoverPreviewSurfaceSize(
  viewport: ViewportBounds,
  margin = MENU_VIEWPORT_MARGIN_PX,
): HoverPreviewSurfaceSize {
  const availableWidth = Math.max(1, viewport.width - margin * 2)
  const availableHeight = Math.max(1, viewport.height - margin * 2)
  const targetWidth = Math.round(viewport.width * HOVER_PREVIEW_VIEWPORT_WIDTH_RATIO)
  const targetHeight = Math.round(viewport.height * HOVER_PREVIEW_VIEWPORT_HEIGHT_RATIO)
  return {
    width: clampSize(targetWidth, HOVER_PREVIEW_MIN_WIDTH_PX, availableWidth),
    height: clampSize(targetHeight, HOVER_PREVIEW_MIN_HEIGHT_PX, availableHeight),
  }
}

export function getHoverPreviewPosition({
  surfaceSize,
  viewport,
  margin = MENU_VIEWPORT_MARGIN_PX,
}: HoverPreviewPositionInput): { x: number; y: number } {
  const x = viewport.left + (viewport.width - surfaceSize.width) / 2
  const y = viewport.top + (viewport.height - surfaceSize.height) / 2
  return clampMenuPosition({
    x,
    y,
    menuWidth: surfaceSize.width,
    menuHeight: surfaceSize.height,
    viewport,
    margin,
  })
}

export class HoverPreviewRequestController {
  private requestToken = 0
  private activeAbort: (() => void) | null = null
  private activeUrl: string | null = null

  constructor(
    private readonly fetcher: HoverPreviewFetcher,
    private readonly runtime: HoverPreviewRuntime,
    private readonly callbacks: HoverPreviewCallbacks,
  ) {}

  begin(path: string): void {
    this.cancelRequest()
    const token = this.requestToken + 1
    this.requestToken = token

    const request = this.fetcher(path)
    this.activeAbort = request.abort ?? null
    request.promise
      .then((blob) => {
        if (token !== this.requestToken) return
        this.activeAbort = null
        const nextUrl = this.runtime.createObjectURL(blob)
        this.revokeActiveUrl()
        this.activeUrl = nextUrl
        this.callbacks.onReady({ path, url: nextUrl })
      })
      .catch(() => {
        if (token === this.requestToken) {
          this.activeAbort = null
        }
      })
  }

  clear(): void {
    this.cancelRequest()
    this.revokeActiveUrl()
  }

  private cancelRequest(): void {
    this.requestToken += 1
    const abort = this.activeAbort
    this.activeAbort = null
    if (!abort) return
    try {
      abort()
    } catch {
      // Ignore abort errors. The stale-token guard owns visible state.
    }
  }

  private revokeActiveUrl(): void {
    const url = this.activeUrl
    this.activeUrl = null
    if (!url) return
    try {
      this.runtime.revokeObjectURL(url)
    } catch {
      // Ignore browser URL cleanup errors.
    }
  }
}

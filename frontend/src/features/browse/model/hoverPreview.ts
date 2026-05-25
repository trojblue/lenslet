import {
  MENU_VIEWPORT_MARGIN_PX,
  clampMenuPosition,
  type AnchorRectLike,
  type ViewportBounds,
} from '../../../lib/menuPosition'

export const HOVER_PREVIEW_OFFSET_PX = 12
export const HOVER_PREVIEW_MAX_WIDTH_PX = 360
export const HOVER_PREVIEW_MAX_HEIGHT_PX = 280
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
  anchorRect: AnchorRectLike
  surfaceSize: HoverPreviewSurfaceSize
  viewport: ViewportBounds
  margin?: number
  offset?: number
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
  return {
    width: clampSize(HOVER_PREVIEW_MAX_WIDTH_PX, HOVER_PREVIEW_MIN_WIDTH_PX, availableWidth),
    height: clampSize(HOVER_PREVIEW_MAX_HEIGHT_PX, HOVER_PREVIEW_MIN_HEIGHT_PX, availableHeight),
  }
}

export function getHoverPreviewPosition({
  anchorRect,
  surfaceSize,
  viewport,
  margin = MENU_VIEWPORT_MARGIN_PX,
  offset = HOVER_PREVIEW_OFFSET_PX,
}: HoverPreviewPositionInput): { x: number; y: number } {
  const preferLeft = anchorRect.right + offset + surfaceSize.width + margin > viewport.right
  const preferAbove = anchorRect.bottom + offset + surfaceSize.height + margin > viewport.bottom
  const x = preferLeft
    ? anchorRect.left - surfaceSize.width - offset
    : anchorRect.right + offset
  const y = preferAbove
    ? anchorRect.top - surfaceSize.height - offset
    : anchorRect.bottom + offset

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

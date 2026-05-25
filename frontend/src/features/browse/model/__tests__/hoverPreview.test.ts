import { describe, expect, it, vi } from 'vitest'
import {
  HOVER_PREVIEW_MAX_HEIGHT_PX,
  HOVER_PREVIEW_MAX_WIDTH_PX,
  HoverPreviewRequestController,
  getHoverPreviewPosition,
  getHoverPreviewSurfaceSize,
  type HoverPreviewRequest,
} from '../hoverPreview'

function deferredBlob(): HoverPreviewRequest & { resolve: (blob: Blob) => void; reject: (error: unknown) => void } {
  let resolve!: (blob: Blob) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<Blob>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, abort: vi.fn(), resolve, reject }
}

describe('hover preview positioning', () => {
  it('keeps the preview surface inside visible viewport bounds', () => {
    const viewport = { left: 20, top: 50, width: 320, height: 240, right: 340, bottom: 290 }
    const surfaceSize = getHoverPreviewSurfaceSize(viewport)
    const pos = getHoverPreviewPosition({
      anchorRect: { left: 310, right: 336, top: 260, bottom: 286 },
      surfaceSize,
      viewport,
    })

    expect(pos.x).toBeGreaterThanOrEqual(viewport.left + 8)
    expect(pos.y).toBeGreaterThanOrEqual(viewport.top + 8)
    expect(pos.x + surfaceSize.width).toBeLessThanOrEqual(viewport.right - 8)
    expect(pos.y + surfaceSize.height).toBeLessThanOrEqual(viewport.bottom - 8)
  })

  it('caps preview size to the visible viewport', () => {
    const large = getHoverPreviewSurfaceSize({ left: 0, top: 0, width: 1200, height: 900, right: 1200, bottom: 900 })
    const small = getHoverPreviewSurfaceSize({ left: 0, top: 0, width: 180, height: 140, right: 180, bottom: 140 })

    expect(large).toEqual({ width: HOVER_PREVIEW_MAX_WIDTH_PX, height: HOVER_PREVIEW_MAX_HEIGHT_PX })
    expect(small.width).toBe(164)
    expect(small.height).toBe(124)
  })
})

describe('HoverPreviewRequestController', () => {
  it('aborts the previous request when a new preview begins', () => {
    const first = deferredBlob()
    const second = deferredBlob()
    const controller = new HoverPreviewRequestController(
      vi.fn()
        .mockReturnValueOnce(first)
        .mockReturnValueOnce(second),
      { createObjectURL: vi.fn(), revokeObjectURL: vi.fn() },
      { onReady: vi.fn() },
    )

    controller.begin('/a.jpg')
    controller.begin('/b.jpg')

    expect(first.abort).toHaveBeenCalledTimes(1)
  })

  it('ignores stale responses after a newer request starts', async () => {
    const first = deferredBlob()
    const second = deferredBlob()
    const onReady = vi.fn()
    const controller = new HoverPreviewRequestController(
      vi.fn()
        .mockReturnValueOnce(first)
        .mockReturnValueOnce(second),
      {
        createObjectURL: vi.fn((blob: Blob) => `blob:${blob.size}`),
        revokeObjectURL: vi.fn(),
      },
      { onReady },
    )

    controller.begin('/a.jpg')
    controller.begin('/b.jpg')
    first.resolve(new Blob(['stale']))
    await Promise.resolve()
    second.resolve(new Blob(['fresh']))
    await Promise.resolve()

    expect(onReady).toHaveBeenCalledTimes(1)
    expect(onReady).toHaveBeenCalledWith({ path: '/b.jpg', url: 'blob:5' })
  })

  it('revokes object URLs when replacing or clearing previews', async () => {
    const first = deferredBlob()
    const second = deferredBlob()
    const revokeObjectURL = vi.fn()
    const controller = new HoverPreviewRequestController(
      vi.fn()
        .mockReturnValueOnce(first)
        .mockReturnValueOnce(second),
      {
        createObjectURL: vi.fn()
          .mockReturnValueOnce('blob:first')
          .mockReturnValueOnce('blob:second'),
        revokeObjectURL,
      },
      { onReady: vi.fn() },
    )

    controller.begin('/a.jpg')
    first.resolve(new Blob(['a']))
    await Promise.resolve()
    controller.begin('/b.jpg')
    second.resolve(new Blob(['b']))
    await Promise.resolve()
    controller.clear()

    expect(revokeObjectURL).toHaveBeenNthCalledWith(1, 'blob:first')
    expect(revokeObjectURL).toHaveBeenNthCalledWith(2, 'blob:second')
  })
})

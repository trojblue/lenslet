import { describe, expect, it, vi } from 'vitest'
import {
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
  it('centers the restored large preview surface inside visible viewport bounds', () => {
    const viewport = { left: 20, top: 50, width: 320, height: 240, right: 340, bottom: 290 }
    const surfaceSize = getHoverPreviewSurfaceSize(viewport)
    const pos = getHoverPreviewPosition({
      surfaceSize,
      viewport,
    })

    expect(pos.x).toBeCloseTo(52)
    expect(pos.y).toBeCloseTo(74)
    expect(pos.x + surfaceSize.width).toBeLessThanOrEqual(viewport.right - 8)
    expect(pos.y + surfaceSize.height).toBeLessThanOrEqual(viewport.bottom - 8)
  })

  it('sizes the preview near 80vw and 80vh while respecting small viewports', () => {
    const large = getHoverPreviewSurfaceSize({ left: 0, top: 0, width: 1200, height: 900, right: 1200, bottom: 900 })
    const small = getHoverPreviewSurfaceSize({ left: 0, top: 0, width: 180, height: 140, right: 180, bottom: 140 })

    expect(large).toEqual({ width: 960, height: 720 })
    expect(small).toEqual({ width: 144, height: 112 })
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

  it('keeps fast replacement output when the previous request resolves late', async () => {
    const first = deferredBlob()
    const second = deferredBlob()
    const onReady = vi.fn()
    const createObjectURL = vi.fn().mockReturnValue('blob:fresh')
    const revokeObjectURL = vi.fn()
    const controller = new HoverPreviewRequestController(
      vi.fn()
        .mockReturnValueOnce(first)
        .mockReturnValueOnce(second),
      { createObjectURL, revokeObjectURL },
      { onReady },
    )

    controller.begin('/a.jpg')
    controller.begin('/b.jpg')
    second.resolve(new Blob(['fresh']))
    await Promise.resolve()
    first.resolve(new Blob(['stale-delayed']))
    await Promise.resolve()

    expect(first.abort).toHaveBeenCalledTimes(1)
    expect(createObjectURL).toHaveBeenCalledTimes(1)
    expect(onReady).toHaveBeenCalledTimes(1)
    expect(onReady).toHaveBeenCalledWith({ path: '/b.jpg', url: 'blob:fresh' })
    expect(revokeObjectURL).not.toHaveBeenCalled()
  })

  it('aborts and ignores the current request when cleared before it resolves', async () => {
    const first = deferredBlob()
    const createObjectURL = vi.fn()
    const onReady = vi.fn()
    const controller = new HoverPreviewRequestController(
      vi.fn().mockReturnValueOnce(first),
      { createObjectURL, revokeObjectURL: vi.fn() },
      { onReady },
    )

    controller.begin('/a.jpg')
    controller.clear()
    first.resolve(new Blob(['late']))
    await Promise.resolve()

    expect(first.abort).toHaveBeenCalledTimes(1)
    expect(createObjectURL).not.toHaveBeenCalled()
    expect(onReady).not.toHaveBeenCalled()
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

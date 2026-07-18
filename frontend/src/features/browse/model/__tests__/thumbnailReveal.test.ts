import { describe, expect, it, vi } from 'vitest'
import { decodeThumbnailBeforeReveal } from '../thumbnailReveal'

describe('cold thumbnail reveal', () => {
  it('waits for browser decode before resolving', async () => {
    let finishDecode!: () => void
    const decode = vi.fn(() => new Promise<void>((resolve) => {
      finishDecode = resolve
    }))
    let revealed = false
    const pending = decodeThumbnailBeforeReveal({ decode }).then(() => {
      revealed = true
    })

    await Promise.resolve()
    expect(revealed).toBe(false)
    finishDecode()
    await pending
    expect(revealed).toBe(true)
    expect(decode).toHaveBeenCalledOnce()
  })
})

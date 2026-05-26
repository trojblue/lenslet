type FrameCallback = (time: number) => void

type FrameSchedulerOptions = {
  requestFrame: (callback: FrameCallback) => number | null
  cancelFrame: (frameId: number) => void
}

export type LatestFrameScheduler = {
  schedule: (callback: () => void) => void
  cancel: () => void
  hasPending: () => boolean
}

export function createLatestFrameScheduler(options: FrameSchedulerOptions): LatestFrameScheduler {
  let frameId: number | null = null
  let latestCallback: (() => void) | null = null

  const run = () => {
    frameId = null
    const callback = latestCallback
    latestCallback = null
    callback?.()
  }

  return {
    schedule(callback: () => void) {
      latestCallback = callback
      if (frameId !== null) return
      const nextFrameId = options.requestFrame(run)
      if (nextFrameId === null) {
        run()
        return
      }
      frameId = nextFrameId
    },
    cancel() {
      if (frameId !== null) {
        options.cancelFrame(frameId)
      }
      frameId = null
      latestCallback = null
    },
    hasPending() {
      return frameId !== null || latestCallback !== null
    },
  }
}

export function createBrowserFrameScheduler(): LatestFrameScheduler {
  return createLatestFrameScheduler({
    requestFrame(callback) {
      if (typeof window === 'undefined' || typeof window.requestAnimationFrame !== 'function') {
        return null
      }
      return window.requestAnimationFrame(callback)
    },
    cancelFrame(frameId) {
      if (typeof window === 'undefined' || typeof window.cancelAnimationFrame !== 'function') return
      window.cancelAnimationFrame(frameId)
    },
  })
}

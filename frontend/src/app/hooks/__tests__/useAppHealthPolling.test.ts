import { describe, expect, it } from 'vitest'
import { createLatestHealthRequestGuard } from '../useAppHealthPolling'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((complete) => {
    resolve = complete
  })
  return { promise, resolve }
}

describe('health request ordering', () => {
  it('rejects an older response that finishes after a source transition', async () => {
    const guard = createLatestHealthRequestGuard()
    const initial = deferred<'current'>()
    const transitioned = deferred<'restart-required'>()
    const applied: string[] = []
    const run = async (response: Promise<string>) => {
      const request = guard.begin()
      const state = await response
      if (guard.isCurrent(request)) applied.push(state)
    }

    const initialRun = run(initial.promise)
    const transitionedRun = run(transitioned.promise)
    transitioned.resolve('restart-required')
    await transitionedRun
    initial.resolve('current')
    await initialRun

    expect(applied).toEqual(['restart-required'])
  })
})

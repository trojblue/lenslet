import { describe, expect, it, vi } from 'vitest'
import { loadMoveDestinationPaths } from '../hooks/useAppActions'

describe('move target loading', () => {
  it('uses a single folder-path request and normalizes the returned paths', async () => {
    const getFolderPaths = vi.fn().mockResolvedValue({
      paths: ['/shots/day-2', 'shots/day-1', '/', '/shots/day-2'],
    })

    await expect(loadMoveDestinationPaths(getFolderPaths)).resolves.toEqual([
      '/',
      '/shots/day-1',
      '/shots/day-2',
    ])
    expect(getFolderPaths).toHaveBeenCalledTimes(1)
  })
})

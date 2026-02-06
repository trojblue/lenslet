import { describe, expect, it } from 'vitest'
import {
  MAX_COMPARE_FILE_PREFETCH,
  MAX_VIEWER_FILE_PREFETCH,
  getCompareFilePrefetchPaths,
  getViewerFilePrefetchPaths,
} from '../prefetchPolicy'

describe('full-file prefetch policy', () => {
  it('prefetches bounded viewer neighbors only', () => {
    const paths = ['/a.jpg', '/b.jpg', '/c.jpg', '/d.jpg', '/e.jpg', '/f.jpg']
    const targets = getViewerFilePrefetchPaths(paths, '/d.jpg')

    expect(targets).toEqual(['/b.jpg', '/c.jpg', '/e.jpg', '/f.jpg'])
    expect(targets).toHaveLength(MAX_VIEWER_FILE_PREFETCH)
    expect(targets).not.toContain('/d.jpg')
  })

  it('clamps viewer prefetch at list edges', () => {
    const paths = ['/a.jpg', '/b.jpg', '/c.jpg']
    const targets = getViewerFilePrefetchPaths(paths, '/a.jpg')

    expect(targets).toEqual(['/b.jpg', '/c.jpg'])
    expect(targets.length).toBeLessThanOrEqual(MAX_VIEWER_FILE_PREFETCH)
  })

  it('prefetches bounded compare window around the active pair', () => {
    const paths = ['/a.jpg', '/b.jpg', '/c.jpg', '/d.jpg', '/e.jpg', '/f.jpg', '/g.jpg']
    const targets = getCompareFilePrefetchPaths(paths, 2)

    expect(targets).toEqual(['/a.jpg', '/b.jpg', '/c.jpg', '/d.jpg', '/e.jpg', '/f.jpg'])
    expect(targets).toHaveLength(MAX_COMPARE_FILE_PREFETCH)
    expect(targets).toContain('/c.jpg')
    expect(targets).toContain('/d.jpg')
  })

  it('disables compare prefetch when fewer than two items are selected', () => {
    expect(getCompareFilePrefetchPaths([], 0)).toEqual([])
    expect(getCompareFilePrefetchPaths(['/a.jpg'], 0)).toEqual([])
  })
})

import { describe, expect, it } from 'vitest'
import { buildBoardState, moveImageToRank } from '../board'
import {
  buildInitialSaveSeqByInstance,
  buildInitialSessions,
  canNavigateNext,
  canNavigatePrev,
  clampInstanceIndex,
  computeDurationMs,
} from '../session'
import type { RankingDatasetResponse, RankingExportEntry } from '../../types'

function makeDataset(): RankingDatasetResponse {
  return {
    dataset_path: '/tmp/ranking_dataset.json',
    instance_count: 2,
    instances: [
      {
        instance_id: 'one',
        instance_index: 0,
        max_ranks: 2,
        images: [
          { image_id: '0', source_path: 'a.jpg', url: '/rank/image?instance_id=one&image_id=0' },
          { image_id: '1', source_path: 'b.jpg', url: '/rank/image?instance_id=one&image_id=1' },
        ],
      },
      {
        instance_id: 'two',
        instance_index: 1,
        max_ranks: 2,
        images: [
          { image_id: '0', source_path: 'c.jpg', url: '/rank/image?instance_id=two&image_id=0' },
          { image_id: '1', source_path: 'd.jpg', url: '/rank/image?instance_id=two&image_id=1' },
        ],
      },
    ],
  }
}

describe('ranking session model contracts', () => {
  it('hydrates sessions from export payload and preserves saved board layout', () => {
    const exported: RankingExportEntry[] = [
      {
        instance_id: 'one',
        final_ranks: [['1'], ['0']],
        started_at: '2026-02-28T05:10:00.000Z',
      },
    ]

    const sessions = buildInitialSessions(makeDataset(), exported)

    expect(sessions.one.board.rankColumns[0]).toEqual(['1'])
    expect(sessions.one.board.rankColumns[1]).toEqual(['0'])
    expect(sessions.one.board.unranked).toEqual([])
    expect(sessions.one.startedAt).toBe('2026-02-28T05:10:00.000Z')
    expect(sessions.two.board.unranked).toEqual(['0', '1'])
  })


  it('hydrates latest non-negative save sequence per instance', () => {
    const exported: RankingExportEntry[] = [
      { instance_id: 'one', save_seq: 2 },
      { instance_id: 'one', save_seq: 1 },
      { instance_id: 'two', save_seq: 4 },
      { instance_id: 'two', save_seq: -1 },
      { instance_id: 'two' },
      { instance_id: 'one', save_seq: 7 },
    ]

    expect(buildInitialSaveSeqByInstance(exported)).toEqual({
      one: 7,
      two: 4,
    })
  })

  it('sanitizes malformed export fields during hydration', () => {
    const exported: RankingExportEntry[] = [
      {
        instance_id: 'one',
        final_ranks: [['0'], ['0'], []],
        started_at: 'not-a-timestamp',
      },
    ]

    const sessions = buildInitialSessions(makeDataset(), exported)

    expect(sessions.one.board.rankColumns[0]).toEqual(['0'])
    expect(sessions.one.board.unranked).toEqual(['1'])
    expect(sessions.one.startedAt).toBeNull()
  })

  it('enforces navigation guards from completion state and list bounds', () => {
    const incomplete = buildBoardState(['0', '1'], 2, null)
    const partialComplete = moveImageToRank(incomplete, '0', 0)
    const complete = moveImageToRank(partialComplete, '1', 1)

    const session = {
      board: complete,
      startedAt: null,
      saveStatus: 'idle' as const,
      saveError: null,
    }
    const incompleteSession = { ...session, board: incomplete }

    expect(canNavigatePrev(0)).toBe(false)
    expect(canNavigatePrev(1)).toBe(true)
    expect(canNavigateNext(0, 2, incompleteSession)).toBe(false)
    expect(canNavigateNext(0, 2, session)).toBe(true)
    expect(canNavigateNext(1, 2, session)).toBe(false)
  })

  it('clamps resume index and computes non-negative duration', () => {
    expect(clampInstanceIndex(-3, 2)).toBe(0)
    expect(clampInstanceIndex(0, 2)).toBe(0)
    expect(clampInstanceIndex(4, 2)).toBe(1)

    expect(computeDurationMs('1970-01-01T00:00:02.000Z', 4_200)).toBe(2_200)
    expect(computeDurationMs('1970-01-01T00:00:04.000Z', 3_000)).toBe(0)
    expect(computeDurationMs('invalid', 3_000)).toBe(0)
  })
})

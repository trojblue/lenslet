import { buildBoardState, isBoardComplete, type RankingBoardState } from './board'
import { sanitizeSaveSeq } from './saveSeq'
import type {
  RankingDatasetResponse,
  RankingExportEntry,
} from '../types'

export type SaveStatus = 'idle' | 'saving' | 'saved' | 'error'

export type InstanceSession = {
  board: RankingBoardState
  startedAt: string | null
  latestIssuedSeq: number
  latestAckSeq: number
  saveStatus: SaveStatus
  saveError: string | null
}

export function clampInstanceIndex(index: number, total: number): number {
  if (total <= 0) return 0
  if (index < 0) return 0
  if (index >= total) return total - 1
  return index
}

export function canNavigatePrev(index: number): boolean {
  return index > 0
}

export function canNavigateNext(
  currentIndex: number,
  totalInstances: number,
  session: InstanceSession | null | undefined,
): boolean {
  if (!session) return false
  if (currentIndex >= totalInstances - 1) return false
  return isBoardComplete(session.board)
}

export function isValidIsoTimestamp(value: unknown): value is string {
  if (typeof value !== 'string') return false
  const parsed = Date.parse(value)
  return Number.isFinite(parsed)
}

export function normalizeSavedRanks(entry: RankingExportEntry | undefined): string[][] | null {
  const raw = entry?.final_ranks
  if (!Array.isArray(raw)) return null
  const groups: string[][] = []
  for (const group of raw) {
    if (!Array.isArray(group)) continue
    const valid = group.filter((value): value is string => typeof value === 'string')
    if (valid.length > 0) {
      groups.push(valid)
    }
  }
  return groups
}

export function buildInitialSessions(
  dataset: RankingDatasetResponse,
  exported: RankingExportEntry[],
): Record<string, InstanceSession> {
  const exportedById = new Map<string, RankingExportEntry>()
  for (const entry of exported) {
    if (!entry || typeof entry.instance_id !== 'string') continue
    exportedById.set(entry.instance_id, entry)
  }

  const sessions: Record<string, InstanceSession> = {}
  for (const instance of dataset.instances) {
    const imageIds = instance.images.map((image) => image.image_id)
    const saved = exportedById.get(instance.instance_id)
    const board = buildBoardState(
      imageIds,
      instance.max_ranks,
      normalizeSavedRanks(saved),
    )
    const startedAt = isValidIsoTimestamp(saved?.started_at) ? saved.started_at : null
    const seq = sanitizeSaveSeq(saved?.save_seq)
    sessions[instance.instance_id] = {
      board,
      startedAt,
      latestIssuedSeq: seq,
      latestAckSeq: seq,
      saveStatus: 'idle',
      saveError: null,
    }
  }
  return sessions
}

export function computeDurationMs(startedAt: string, nowMs: number = Date.now()): number {
  const startMs = Date.parse(startedAt)
  if (!Number.isFinite(startMs)) return 0
  return Math.max(0, Math.trunc(nowMs - startMs))
}

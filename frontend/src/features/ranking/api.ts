import { BASE } from '../../api/base'
import { fetchJSON } from '../../lib/fetcher'
import type {
  RankingDatasetResponse,
  RankingExportResponse,
  RankingProgressResponse,
  RankingSaveRequest,
  RankingSaveResponse,
} from './types'

const RANK_BASE = `${BASE}/rank`

export const rankingApi = {
  getDataset: (): Promise<RankingDatasetResponse> => {
    return fetchJSON<RankingDatasetResponse>(`${RANK_BASE}/dataset`).promise
  },

  getProgress: (): Promise<RankingProgressResponse> => {
    return fetchJSON<RankingProgressResponse>(`${RANK_BASE}/progress`).promise
  },

  exportLatest: (completedOnly = false): Promise<RankingExportResponse> => {
    const suffix = completedOnly ? '?completed_only=true' : ''
    return fetchJSON<RankingExportResponse>(`${RANK_BASE}/export${suffix}`).promise
  },

  save: (payload: RankingSaveRequest): Promise<RankingSaveResponse> => {
    return fetchJSON<RankingSaveResponse>(`${RANK_BASE}/save`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).promise
  },
}

import { apiUrl } from '../../api/base'
import { fetchJSON } from '../../lib/fetcher'
import type {
  RankingDatasetResponse,
  RankingExportResponse,
  RankingProgressResponse,
  RankingSaveRequest,
  RankingSaveResponse,
} from './types'

function rankUrl(path: string): string {
  return apiUrl(`/rank${path}`)
}

export const rankingApi = {
  getDataset: (): Promise<RankingDatasetResponse> => {
    return fetchJSON<RankingDatasetResponse>(rankUrl('/dataset')).promise
  },

  getProgress: (): Promise<RankingProgressResponse> => {
    return fetchJSON<RankingProgressResponse>(rankUrl('/progress')).promise
  },

  exportLatest: (completedOnly = false): Promise<RankingExportResponse> => {
    const suffix = completedOnly ? '?completed_only=true' : ''
    return fetchJSON<RankingExportResponse>(rankUrl(`/export${suffix}`)).promise
  },

  save: (payload: RankingSaveRequest): Promise<RankingSaveResponse> => {
    return fetchJSON<RankingSaveResponse>(rankUrl('/save'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).promise
  },
}

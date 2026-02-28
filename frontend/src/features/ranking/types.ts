export type RankingImage = {
  image_id: string
  source_path: string
  url: string
}

export type RankingInstance = {
  instance_id: string
  instance_index: number
  max_ranks: number
  images: RankingImage[]
}

export type RankingDatasetResponse = {
  dataset_path: string
  instance_count: number
  instances: RankingInstance[]
}

export type RankingProgressResponse = {
  completed_instance_ids: string[]
  last_completed_instance_index: number | null
  resume_instance_index: number
  total_instances: number
}

export type RankingSaveRequest = {
  instance_id: string
  final_ranks: string[][]
  started_at?: string
  submitted_at?: string
  duration_ms?: number
  completed?: boolean
  save_seq?: number
}

export type RankingSaveResponse = {
  ok: boolean
  instance_id: string
  instance_index: number
  completed: boolean
}

export type RankingExportEntry = {
  instance_id: string
  instance_index?: number
  final_ranks?: string[][]
  completed?: boolean
  started_at?: string
  submitted_at?: string
  duration_ms?: number
  save_seq?: number
}

export type RankingExportResponse = {
  dataset_path: string
  results_path: string
  count: number
  results: RankingExportEntry[]
}

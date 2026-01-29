import { useMutation, useQuery } from '@tanstack/react-query'
import { api } from './client'
import type { EmbeddingsResponse, EmbeddingSearchRequest, EmbeddingSearchResponse } from '../lib/types'

export const embeddingsQueryKey = () => ['embeddings'] as const

export function useEmbeddings() {
  return useQuery<EmbeddingsResponse>({
    queryKey: embeddingsQueryKey(),
    queryFn: () => api.getEmbeddings(),
    staleTime: 60_000,
    gcTime: 5 * 60_000,
    retry: 1,
    refetchOnWindowFocus: false,
  })
}

export function useEmbeddingSearch() {
  return useMutation<EmbeddingSearchResponse, Error, EmbeddingSearchRequest>({
    mutationFn: (body) => api.searchEmbeddings(body),
  })
}

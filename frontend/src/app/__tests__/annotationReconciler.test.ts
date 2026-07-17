import { QueryClient, QueryObserver } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'
import type { QueryDependencyManifest } from '../../lib/types'
import {
  AnnotationReconciler,
  mutationAffectsDependencyManifest,
} from '../model/appShellStateSync'

const QUERY_KEY = ['folder-query', 'active'] as const
const FACET_KEY = ['folder-facets', 'active'] as const

function manifest(fields: string[]): QueryDependencyManifest {
  return {
    fields,
    metric_keys: [],
    categorical_keys: [],
    unknown: false,
  }
}

function activateQuery(
  queryClient: QueryClient,
  queryKey: readonly unknown[],
  dependencyManifest: QueryDependencyManifest,
): () => void {
  const data = { dependency_manifest: dependencyManifest }
  const observer = new QueryObserver(queryClient, {
    queryKey,
    queryFn: async () => data,
    initialData: data,
    staleTime: Infinity,
  })
  return observer.subscribe(() => undefined)
}

function projection(mutationId: string) {
  return {
    mutationId,
    changedFields: ['star'],
    item: { path: '/shots/a.jpg', star: 1 as const },
  }
}

describe('AnnotationReconciler', () => {
  it('projects an irrelevant star change without query or facet requests', async () => {
    const queryClient = new QueryClient()
    const stopQuery = activateQuery(queryClient, QUERY_KEY, manifest(['added_at']))
    const stopFacets = activateQuery(queryClient, FACET_KEY, manifest([]))
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    const project = vi.fn()
    const reconciler = new AnnotationReconciler(queryClient, project)

    expect(reconciler.accept(projection('patch-1'))).toBe(true)
    await reconciler.whenIdle()

    expect(project).toHaveBeenCalledTimes(1)
    expect(invalidate).not.toHaveBeenCalled()
    stopQuery()
    stopFacets()
  })

  it.each([
    ['response-first', ['patch-1', 'patch-1']],
    ['event-first', ['patch-1', 'patch-1']],
  ])('coalesces %s delivery into one logical mutation', async (_label, mutationIds) => {
    const queryClient = new QueryClient()
    const stopQuery = activateQuery(queryClient, QUERY_KEY, manifest(['star']))
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries').mockResolvedValue()
    const project = vi.fn()
    const reconciler = new AnnotationReconciler(queryClient, project)

    expect(reconciler.accept(projection(mutationIds[0]))).toBe(true)
    expect(reconciler.accept(projection(mutationIds[1]))).toBe(false)
    await reconciler.whenIdle()

    expect(project).toHaveBeenCalledTimes(1)
    expect(invalidate).toHaveBeenCalledTimes(1)
    stopQuery()
  })

  it('allows only one dirty trailing pass for a rapid relevant burst', async () => {
    const queryClient = new QueryClient()
    const stopQuery = activateQuery(queryClient, QUERY_KEY, manifest(['star']))
    const stopFacets = activateQuery(queryClient, FACET_KEY, manifest(['star']))
    const resolvers: Array<() => void> = []
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries').mockImplementation(() => (
      new Promise<void>((resolve) => resolvers.push(resolve))
    ))
    const reconciler = new AnnotationReconciler(queryClient, vi.fn())

    reconciler.accept(projection('patch-0'))
    for (let index = 1; index < 20; index += 1) {
      reconciler.accept(projection(`patch-${index}`))
    }
    expect(invalidate).toHaveBeenCalledTimes(2)

    resolvers.splice(0).forEach((resolve) => resolve())
    await vi.waitFor(() => {
      expect(invalidate).toHaveBeenCalledTimes(4)
    })
    resolvers.splice(0).forEach((resolve) => resolve())
    await reconciler.whenIdle()

    expect(reconciler.diagnostics().reconciliationPasses).toBe(2)
    stopQuery()
    stopFacets()
  })

  it('bounds seen mutation IDs by count and TTL', () => {
    const queryClient = new QueryClient()
    let now = 0
    const reconciler = new AnnotationReconciler(queryClient, vi.fn(), () => now)

    for (let index = 0; index < 600; index += 1) {
      reconciler.accept(projection(`patch-${index}`))
    }
    expect(reconciler.diagnostics().seenMutationIds).toBe(512)

    now = 10 * 60_000 + 1
    reconciler.accept(projection('patch-fresh'))
    expect(reconciler.diagnostics().seenMutationIds).toBe(1)
  })
})

describe('mutationAffectsDependencyManifest', () => {
  it('intersects field, metric, and categorical mutations and falls back for unknown manifests', () => {
    const dependencies: QueryDependencyManifest = {
      fields: ['notes'],
      metric_keys: ['quality'],
      categorical_keys: ['source'],
      unknown: false,
    }

    expect(mutationAffectsDependencyManifest(['star'], dependencies)).toBe(false)
    expect(mutationAffectsDependencyManifest(['notes'], dependencies)).toBe(true)
    expect(mutationAffectsDependencyManifest(['metric:quality'], dependencies)).toBe(true)
    expect(mutationAffectsDependencyManifest(['categorical:source'], dependencies)).toBe(true)
    expect(mutationAffectsDependencyManifest(['star'], { ...dependencies, unknown: true })).toBe(true)
    expect(mutationAffectsDependencyManifest(['star'], null)).toBe(true)
  })
})

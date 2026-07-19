import React, { useMemo, useRef, useState } from 'react'
import { flushSync } from 'react-dom'
import { alignedFacetBatchKeys, facetSchemaKey } from '../model/facetDemand'
import { usePrepaintEffect } from '../model/facetPresentation'

export {
  alignedFacetBatchKeys,
  initialFacetBatchKeys,
  resolveVisibleFacetBatch,
} from '../model/facetDemand'

interface VirtualFieldListProps {
  keys: readonly string[]
  estimateSize: number
  kind: 'metric' | 'categorical'
  schemaRevision: number
  active?: boolean
  onVisibleKeysChange?: (keys: string[]) => void
  renderCard: (key: string) => React.ReactNode
}

export default function VirtualFieldList({
  keys,
  estimateSize,
  kind,
  schemaRevision,
  active = true,
  onVisibleKeysChange,
  renderCard,
}: VirtualFieldListProps): JSX.Element {
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const schemaKey = facetSchemaKey(keys)
  const [ownedRange, setOwnedRange] = useState(() => ({
    schemaKey,
    schemaRevision,
    indices: virtualFieldViewportIndices(0, estimateSize, keys.length, estimateSize),
  }))
  const rangeCompatible = ownedRange.schemaKey === schemaKey
    && ownedRange.schemaRevision === schemaRevision
  const visibleIndices = useMemo(() => resolveVirtualFieldIndices(
    ownedRange.schemaKey,
    ownedRange.schemaRevision,
    ownedRange.indices,
    schemaKey,
    schemaRevision,
    keys.length,
    estimateSize,
  ), [
    estimateSize,
    keys.length,
    ownedRange.indices,
    ownedRange.schemaKey,
    ownedRange.schemaRevision,
    schemaKey,
    schemaRevision,
  ])
  usePrepaintEffect(() => {
    if (!rangeCompatible && scrollRef.current) scrollRef.current.scrollTop = 0
  })
  const stride = estimateSize + 12
  const totalSize = keys.length ? keys.length * stride - 12 : 0
  const renderedKeys = active ? visibleIndices.map((index) => keys[index]) : []

  const publishVisibleIndices = (indices: readonly number[]) => {
    flushSync(() => {
      const nextKeys = alignedFacetBatchKeys(keys, indices)
      if (nextKeys.length) onVisibleKeysChange?.(nextKeys)
      setOwnedRange((current) => (
        current.schemaKey === schemaKey
        && current.schemaRevision === schemaRevision
        && current.indices.length === indices.length
        && current.indices.every((index, offset) => index === indices[offset])
          ? current
          : { schemaKey, schemaRevision, indices: [...indices] }
      ))
    })
  }

  const handleScroll = (event: React.UIEvent<HTMLDivElement>) => {
    if (!active) return
    publishVisibleIndices(virtualFieldViewportIndices(
      event.currentTarget.scrollTop,
      event.currentTarget.clientHeight,
      keys.length,
      estimateSize,
    ))
  }

  const handleKeyboardScroll = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.target !== event.currentTarget) return
    const scrollTop = scrollRef.current?.scrollTop ?? 0
    const currentIndex = Math.min(
      keys.length - 1,
      Math.max(0, Math.floor(scrollTop / stride)),
    )
    const pageSize = Math.max(
      1,
      Math.floor((scrollRef.current?.clientHeight ?? estimateSize) / estimateSize),
    )
    const targetIndex = virtualFieldKeyboardTarget(
      event.key,
      currentIndex,
      keys.length,
      pageSize,
    )
    if (targetIndex == null) return
    event.preventDefault()
    const clientHeight = scrollRef.current?.clientHeight ?? estimateSize
    const targetScrollTop = event.key === 'End'
      ? Math.max(0, (targetIndex + 1) * stride - clientHeight)
      : targetIndex * stride
    publishVisibleIndices(virtualFieldViewportIndices(
      targetScrollTop,
      clientHeight,
      keys.length,
      estimateSize,
    ))
    if (scrollRef.current) scrollRef.current.scrollTop = targetScrollTop
  }

  return (
    <div
      ref={scrollRef}
      className="h-[min(55vh,36rem)] shrink-0 overflow-auto scrollbar-thin"
      data-virtual-field-list={kind}
      data-rendered-field-keys={JSON.stringify(renderedKeys)}
      role="region"
      aria-label={`All ${kind} fields`}
      tabIndex={0}
      onKeyDown={handleKeyboardScroll}
      onScroll={handleScroll}
    >
      <div
        className="relative w-full"
        style={{ height: `${totalSize}px` }}
      >
        {active && visibleIndices.map((index) => {
          const key = keys[index]
          return (
            <div
              key={key}
              data-index={index}
              data-virtual-field-card={kind}
              data-field-key={key}
              className="absolute left-0 top-0 w-full"
              style={{ transform: `translateY(${index * stride}px)` }}
            >
              {renderCard(key)}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export function virtualFieldKeyboardTarget(
  key: string,
  currentIndex: number,
  count: number,
  pageSize: number,
): number | null {
  if (count <= 0) return null
  const lastIndex = count - 1
  if (key === 'Home') return 0
  if (key === 'End') return lastIndex
  if (key === 'ArrowDown') return Math.min(lastIndex, currentIndex + 1)
  if (key === 'ArrowUp') return Math.max(0, currentIndex - 1)
  if (key === 'PageDown') return Math.min(lastIndex, currentIndex + Math.max(1, pageSize))
  if (key === 'PageUp') return Math.max(0, currentIndex - Math.max(1, pageSize))
  return null
}

export function virtualFieldViewportIndices(
  scrollTop: number,
  clientHeight: number,
  count: number,
  estimateSize: number,
  overscan = 4,
): number[] {
  if (count <= 0) return []
  const stride = estimateSize + 12
  const first = Math.max(0, Math.floor(scrollTop / stride) - overscan)
  const viewportBottom = scrollTop + Math.max(clientHeight, estimateSize)
  const last = Math.min(count - 1, Math.ceil(viewportBottom / stride) + overscan)
  return Array.from({ length: last - first + 1 }, (_, offset) => first + offset)
}

export function resolveVirtualFieldIndices(
  ownedSchemaKey: string,
  ownedSchemaRevision: number,
  ownedIndices: readonly number[],
  schemaKey: string,
  schemaRevision: number,
  count: number,
  estimateSize: number,
): number[] {
  const retained = ownedSchemaKey === schemaKey && ownedSchemaRevision === schemaRevision
    ? ownedIndices.filter((index) => index < count)
    : []
  return retained.length
    ? retained
    : virtualFieldViewportIndices(0, estimateSize, count, estimateSize)
}

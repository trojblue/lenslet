import { useVirtualizer } from '@tanstack/react-virtual'
import React, { useEffect, useMemo, useRef } from 'react'

interface VirtualFieldListProps {
  keys: readonly string[]
  estimateSize: number
  kind: 'metric' | 'categorical'
  onVisibleKeysChange?: (keys: string[]) => void
  renderCard: (key: string) => React.ReactNode
}

export default function VirtualFieldList({
  keys,
  estimateSize,
  kind,
  onVisibleKeysChange,
  renderCard,
}: VirtualFieldListProps): JSX.Element {
  const scrollRef = useRef<HTMLDivElement>(null)
  const virtualizer = useVirtualizer({
    count: keys.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => estimateSize,
    gap: 12,
    overscan: 4,
  })
  const virtualItems = virtualizer.getVirtualItems()
  const visibleKeys = useMemo(
    () => alignedFacetBatchKeys(keys, virtualItems.map((item) => item.index)),
    [keys, virtualItems],
  )
  const visibleToken = visibleKeys.join('\u0000')

  useEffect(() => {
    onVisibleKeysChange?.(visibleKeys)
  }, [onVisibleKeysChange, visibleToken]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleKeyboardScroll = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.target !== event.currentTarget) return
    const scrollTop = scrollRef.current?.scrollTop ?? 0
    const currentIndex = virtualItems.find((item) => item.end > scrollTop)?.index ?? 0
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
    virtualizer.scrollToIndex(targetIndex, {
      align: event.key === 'End' ? 'end' : 'start',
    })
  }

  return (
    <div
      ref={scrollRef}
      className="h-[min(55vh,36rem)] shrink-0 overflow-auto scrollbar-thin"
      data-virtual-field-list={kind}
      role="region"
      aria-label={`All ${kind} fields`}
      tabIndex={0}
      onKeyDown={handleKeyboardScroll}
    >
      <div
        className="relative w-full"
        style={{ height: `${virtualizer.getTotalSize()}px` }}
      >
        {virtualItems.map((virtualItem) => {
          const key = keys[virtualItem.index]
          return (
            <div
              key={key}
              data-index={virtualItem.index}
              data-virtual-field-card={kind}
              data-field-key={key}
              className="absolute left-0 top-0 w-full"
              style={{ transform: `translateY(${virtualItem.start}px)` }}
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

export function alignedFacetBatchKeys(
  keys: readonly string[],
  visibleIndices: readonly number[],
  batchSize = 24,
): string[] {
  if (!visibleIndices.length) return []
  const safeBatchSize = Math.max(1, Math.floor(batchSize))
  const batches = new Set(visibleIndices.map((index) => (
    Math.floor(index / safeBatchSize) * safeBatchSize
  )))
  return Array.from(batches)
    .sort((a, b) => a - b)
    .flatMap((start) => keys.slice(start, start + safeBatchSize))
}

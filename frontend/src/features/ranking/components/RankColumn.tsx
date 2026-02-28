import { useDroppable } from '@dnd-kit/core'
import {
  SortableContext,
  verticalListSortingStrategy,
  rectSortingStrategy,
} from '@dnd-kit/sortable'
import { ImageCard } from './ImageCard'
import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

interface RankColumnProps {
  id: string
  items: string[]
  imageLabels: Record<string, string>
  className?: string
}

export function RankColumn({ id, items, imageLabels, className }: RankColumnProps) {
  const { setNodeRef, isOver } = useDroppable({ id })
  const isUnassigned = id === 'unassigned'
  const strategy = isUnassigned ? rectSortingStrategy : verticalListSortingStrategy

  return (
    <div
      ref={setNodeRef}
      className={twMerge(
        clsx(
          'transition-all duration-300 rounded-xl',
          isOver && 'bg-zinc-100/80 ring-2 ring-zinc-200/60 ring-inset',
          className,
        ),
      )}
    >
      <SortableContext id={id} items={items} strategy={strategy}>
        {items.map((itemId) => (
          <ImageCard
            key={itemId}
            id={itemId}
            isUnassigned={isUnassigned}
            badgeLabel={imageLabels[itemId]}
          />
        ))}
      </SortableContext>
    </div>
  )
}

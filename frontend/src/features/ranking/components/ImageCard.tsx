import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'
import { Maximize2 } from 'lucide-react'
import { useContext } from 'react'
import { RankingContext } from '../RankingApp'

interface ImageCardProps {
  id: string
  isOverlay?: boolean
  isUnassigned?: boolean
  badgeLabel?: string
}

export function ImageCard({ id, isOverlay, isUnassigned, badgeLabel }: ImageCardProps) {
  const { getImageUrl, onEnlarge } = useContext(RankingContext)
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      data-image-id={id}
      tabIndex={0}
      className={twMerge(
        clsx(
          'relative group cursor-grab active:cursor-grabbing outline-none',
          'rounded-xl overflow-hidden border border-zinc-200/50 shadow-sm',
          'focus:border-zinc-900/40 focus:ring-2 focus:ring-zinc-900/30 focus:ring-offset-2',
          'transition-all duration-300 hover:shadow-md hover:-translate-y-0.5',
          isDragging && 'opacity-50 z-50 scale-105 shadow-xl border-zinc-300',
          isOverlay && 'opacity-100 scale-105 shadow-2xl rotate-2 cursor-grabbing',
        ),
      )}
    >
      <div
        className={twMerge(
          'aspect-square bg-zinc-100',
          isUnassigned
            ? 'w-40 sm:w-48 md:w-56 lg:w-64'
            : 'w-full sm:w-28 md:w-36 lg:w-44',
        )}
      >
        <img
          src={getImageUrl(id)}
          alt=""
          className="w-full h-full object-cover pointer-events-none"
          referrerPolicy="no-referrer"
          loading="lazy"
        />
      </div>

      <button
        onClick={(e) => {
          e.stopPropagation()
          onEnlarge(id)
        }}
        onPointerDown={(e) => e.stopPropagation()}
        className="absolute top-2 right-2 p-1.5 bg-black/20 backdrop-blur-md text-white rounded-lg opacity-0 group-hover:opacity-100 focus:opacity-100 transition-all duration-200 hover:bg-black/40 z-10"
        title="Enlarge (Enter)"
      >
        <Maximize2 className="w-4 h-4" />
      </button>

      {badgeLabel && (
        <div className="pointer-events-none absolute bottom-1.5 left-1.5 rounded bg-black/60 px-1.5 py-0.5 text-[10px] font-semibold tracking-wide text-white">
          {badgeLabel}
        </div>
      )}
    </div>
  )
}

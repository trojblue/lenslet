import { ChevronLeft, ChevronRight, Download } from 'lucide-react'
import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

interface HeaderProps {
  currentIndex: number
  totalInstances: number
  onPrev: () => void
  onNext: () => void
  onExport: () => void
  canProceed: boolean
  isFirst: boolean
  isLast: boolean
}

export function Header({
  currentIndex,
  totalInstances,
  onPrev,
  onNext,
  onExport,
  canProceed,
  isFirst,
  isLast,
}: HeaderProps) {
  return (
    <header className="flex items-center justify-between px-5 py-3 bg-white/80 backdrop-blur-md border-b border-zinc-200/60 sticky top-0 z-10">
      <div className="flex items-center gap-4">
        <h1 className="text-sm font-semibold text-zinc-900 tracking-tight hidden sm:block">
          Image Ranking
        </h1>
        <div className="text-xs font-mono text-zinc-500 bg-zinc-100/80 px-2.5 py-1 rounded-full border border-zinc-200/50">
          {currentIndex + 1} / {totalInstances}
        </div>
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={onPrev}
          disabled={isFirst}
          className={twMerge(
            clsx(
              'flex items-center gap-1 px-3.5 py-1.5 rounded-full text-xs font-medium transition-all duration-200 border',
              isFirst
                ? 'text-zinc-400 bg-zinc-50 border-transparent cursor-not-allowed'
                : 'text-zinc-700 bg-white border-zinc-200 hover:bg-zinc-50 hover:border-zinc-300 active:bg-zinc-100 shadow-sm',
            ),
          )}
        >
          <ChevronLeft className="w-3.5 h-3.5" />
          Prev (Q)
        </button>
        <button
          onClick={onNext}
          disabled={!canProceed}
          className={twMerge(
            clsx(
              'flex items-center gap-1 px-3.5 py-1.5 rounded-full text-xs font-medium transition-all duration-200 border',
              !canProceed
                ? 'text-zinc-400 bg-zinc-50 border-transparent cursor-not-allowed'
                : 'text-white bg-zinc-900 border-zinc-900 hover:bg-zinc-800 hover:border-zinc-800 active:bg-zinc-950 shadow-sm',
            ),
          )}
        >
          {isLast ? 'Finish' : 'Next (E)'}
          <ChevronRight className="w-3.5 h-3.5" />
        </button>
        <div className="w-px h-4 bg-zinc-200 mx-2 hidden sm:block" />
        <button
          onClick={onExport}
          className="hidden sm:flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs font-medium text-zinc-700 bg-white border border-zinc-200 hover:bg-zinc-50 hover:border-zinc-300 active:bg-zinc-100 transition-all duration-200 shadow-sm"
        >
          <Download className="w-3.5 h-3.5" />
          Export
        </button>
      </div>
    </header>
  )
}

import { useEffect, useRef, useState, useContext } from 'react'
import { X } from 'lucide-react'
import { RankingContext } from '../RankingApp'

interface LightboxProps {
  imageId: string
  imageIds: string[]
  onClose: () => void
  onRank: (id: string, rank: number) => void
  numRanks: number
}

export function Lightbox({ imageId, imageIds, onClose, onRank, numRanks }: LightboxProps) {
  const { getImageUrl } = useContext(RankingContext)
  const [currentIndex, setCurrentIndex] = useState(imageIds.indexOf(imageId))
  const [scale, setScale] = useState(1)
  const [pos, setPos] = useState({ x: 0, y: 0 })
  const isDragging = useRef(false)
  const lastPos = useRef({ x: 0, y: 0 })

  useEffect(() => {
    setCurrentIndex(imageIds.indexOf(imageId))
    setScale(1)
    setPos({ x: 0, y: 0 })
  }, [imageId, imageIds])

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' || e.key === 'Enter') {
        onClose()
        return
      }
      if (e.key.toLowerCase() === 'a') {
        setCurrentIndex((prev) => (prev > 0 ? prev - 1 : imageIds.length - 1))
        setScale(1)
        setPos({ x: 0, y: 0 })
      } else if (e.key.toLowerCase() === 'd') {
        setCurrentIndex((prev) => (prev < imageIds.length - 1 ? prev + 1 : 0))
        setScale(1)
        setPos({ x: 0, y: 0 })
      } else {
        const numKey = parseInt(e.key)
        if (!isNaN(numKey) && numKey >= 1 && numKey <= numRanks) {
          onRank(imageIds[currentIndex], numKey)
        }
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [currentIndex, imageIds, numRanks, onClose, onRank])

  const handleWheel = (e: React.WheelEvent) => {
    setScale((s) => Math.max(0.1, Math.min(s - e.deltaY * 0.005, 10)))
  }

  const handlePointerDown = (e: React.PointerEvent) => {
    isDragging.current = true
    lastPos.current = { x: e.clientX, y: e.clientY }
    ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
  }

  const handlePointerMove = (e: React.PointerEvent) => {
    if (!isDragging.current) return
    const dx = e.clientX - lastPos.current.x
    const dy = e.clientY - lastPos.current.y
    setPos((p) => ({ x: p.x + dx, y: p.y + dy }))
    lastPos.current = { x: e.clientX, y: e.clientY }
  }

  const handlePointerUp = (e: React.PointerEvent) => {
    isDragging.current = false
    ;(e.target as HTMLElement).releasePointerCapture(e.pointerId)
  }

  const currentImageId = imageIds[currentIndex]

  return (
    <div
      id="lightbox-container"
      className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/95 backdrop-blur-xl overflow-hidden touch-none"
    >
      <button
        onClick={onClose}
        className="absolute top-4 right-4 text-white z-50 p-2.5 bg-white/10 backdrop-blur-md rounded-full hover:bg-white/20 transition-all duration-200"
      >
        <X className="w-5 h-5" />
      </button>

      <div className="absolute top-4 left-4 text-white z-50 bg-white/10 backdrop-blur-md px-3.5 py-1.5 rounded-full font-mono text-sm border border-white/10 shadow-sm">
        {currentIndex + 1} / {imageIds.length}
      </div>

      <div className="absolute bottom-6 left-1/2 -translate-x-1/2 text-white/80 z-50 bg-zinc-900/80 backdrop-blur-md px-6 py-3 rounded-full text-sm text-center border border-white/10 shadow-2xl pointer-events-none hidden sm:block">
        <div className="flex items-center gap-5">
          <span>
            <kbd className="bg-white/20 px-1.5 py-0.5 rounded-md text-white font-sans font-medium text-xs shadow-sm shadow-black/20">
              A
            </kbd>{' '}
            /{' '}
            <kbd className="bg-white/20 px-1.5 py-0.5 rounded-md text-white font-sans font-medium text-xs shadow-sm shadow-black/20">
              D
            </kbd>{' '}
            navigate
          </span>
          <span>
            <kbd className="bg-white/20 px-1.5 py-0.5 rounded-md text-white font-sans font-medium text-xs shadow-sm shadow-black/20">
              1-{numRanks}
            </kbd>{' '}
            rank
          </span>
          <span>
            <kbd className="bg-white/20 px-1.5 py-0.5 rounded-md text-white font-sans font-medium text-xs shadow-sm shadow-black/20">
              Scroll
            </kbd>{' '}
            zoom
          </span>
          <span>
            <kbd className="bg-white/20 px-1.5 py-0.5 rounded-md text-white font-sans font-medium text-xs shadow-sm shadow-black/20">
              Drag
            </kbd>{' '}
            pan
          </span>
        </div>
      </div>

      <div
        className="w-full h-full flex items-center justify-center cursor-grab active:cursor-grabbing"
        onWheel={handleWheel}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
      >
        <img
          src={currentImageId ? getImageUrl(currentImageId) : ''}
          alt="Fullscreen"
          className="max-w-full max-h-full object-contain select-none shadow-2xl"
          style={{
            transform: `translate(${pos.x}px, ${pos.y}px) scale(${scale})`,
            transition: isDragging.current
              ? 'none'
              : 'transform 0.15s cubic-bezier(0.2, 0, 0, 1)',
          }}
          draggable={false}
        />
      </div>
    </div>
  )
}

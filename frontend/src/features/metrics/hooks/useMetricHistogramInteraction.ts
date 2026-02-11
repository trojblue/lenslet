import { useEffect, useRef, useState } from 'react'
import type {
  MutableRefObject,
  PointerEvent as ReactPointerEvent,
} from 'react'
import { clamp01, normalizeRange, type Range } from '../model/histogram'

export interface HistogramDomain {
  min: number
  max: number
}

interface PointerRect {
  left: number
  width: number
}

interface PointerUpOutcome {
  commitRange: Range | null
  shouldClear: boolean
}

interface UseMetricHistogramInteractionArgs {
  metricKey: string
  domain: HistogramDomain | null
  activeRange: Range | null
  onChangeRange: (range: Range | null) => void
}

interface UseMetricHistogramInteractionResult {
  svgRef: MutableRefObject<SVGSVGElement | null>
  hoverValue: number | null
  displayRange: Range | null
  onPointerDown: (event: ReactPointerEvent<SVGSVGElement>) => void
  onPointerMove: (event: ReactPointerEvent<SVGSVGElement>) => void
  onPointerUp: (event: ReactPointerEvent<SVGSVGElement>) => void
  onPointerLeave: () => void
}

export function histogramValueFromClientX(clientX: number, rect: PointerRect, domain: HistogramDomain): number {
  const t = clamp01((clientX - rect.left) / rect.width)
  return domain.min + (domain.max - domain.min) * t
}

export function didPointerDrag(startClientX: number | null, clientX: number, thresholdPx = 4): boolean {
  if (startClientX == null) return false
  return Math.abs(clientX - startClientX) >= thresholdPx
}

export function rangeFromDrag(startValue: number | null, value: number): Range {
  return normalizeRange(startValue ?? value, value)
}

export function resolvePointerUpOutcome(
  dragMoved: boolean,
  pointerValue: number | null,
  dragStartValue: number | null,
  activeRange: Range | null
): PointerUpOutcome {
  if (dragMoved && pointerValue != null) {
    return { commitRange: rangeFromDrag(dragStartValue, pointerValue), shouldClear: false }
  }
  return { commitRange: null, shouldClear: activeRange != null }
}

export function useMetricHistogramInteraction({
  metricKey,
  domain,
  activeRange,
  onChangeRange,
}: UseMetricHistogramInteractionArgs): UseMetricHistogramInteractionResult {
  const [dragRange, setDragRange] = useState<Range | null>(null)
  const [dragging, setDragging] = useState(false)
  const dragStartValueRef = useRef<number | null>(null)
  const dragStartClientXRef = useRef<number | null>(null)
  const dragMovedRef = useRef(false)
  const svgRef = useRef<SVGSVGElement | null>(null)
  const [hoverValue, setHoverValue] = useState<number | null>(null)

  const displayRange = dragRange ?? activeRange

  useEffect(() => {
    setHoverValue(null)
  }, [metricKey, domain?.min, domain?.max])

  const readPointerValue = (clientX: number): number | null => {
    if (!domain) return null
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect) return null
    return histogramValueFromClientX(clientX, { left: rect.left, width: rect.width }, domain)
  }

  const onPointerDown = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (!domain) return
    event.preventDefault()
    const value = readPointerValue(event.clientX)
    if (value == null) return
    setDragging(true)
    setDragRange(null)
    dragStartValueRef.current = value
    dragStartClientXRef.current = event.clientX
    dragMovedRef.current = false
    setHoverValue(value)
    svgRef.current?.setPointerCapture(event.pointerId)
  }

  const onPointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    const value = readPointerValue(event.clientX)
    if (value == null) {
      if (!dragging) setHoverValue(null)
      return
    }
    setHoverValue(value)
    if (!dragging) return
    if (!dragMovedRef.current && !didPointerDrag(dragStartClientXRef.current, event.clientX)) return
    dragMovedRef.current = true
    setDragRange(rangeFromDrag(dragStartValueRef.current, value))
  }

  const onPointerUp = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (!dragging) return
    setDragging(false)
    svgRef.current?.releasePointerCapture(event.pointerId)
    const value = readPointerValue(event.clientX)
    const outcome = resolvePointerUpOutcome(
      dragMovedRef.current,
      value,
      dragStartValueRef.current,
      activeRange
    )
    if (outcome.commitRange) {
      setHoverValue(value)
      onChangeRange(outcome.commitRange)
    } else if (outcome.shouldClear) {
      onChangeRange(null)
    }
    dragStartValueRef.current = null
    dragStartClientXRef.current = null
    dragMovedRef.current = false
    setTimeout(() => setDragRange(null), 0)
  }

  return {
    svgRef,
    hoverValue,
    displayRange,
    onPointerDown,
    onPointerMove,
    onPointerUp,
    onPointerLeave: () => setHoverValue(null),
  }
}

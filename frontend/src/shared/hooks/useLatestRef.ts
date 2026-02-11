import { useRef } from 'react'

/**
 * Keeps a stable ref object that always points at the latest value.
 * Useful for event listeners that should stay mounted while reading fresh state.
 */
export function useLatestRef<T>(value: T) {
  const ref = useRef(value)
  ref.current = value
  return ref
}

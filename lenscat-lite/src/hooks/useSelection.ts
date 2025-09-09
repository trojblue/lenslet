import { useState } from 'react'
export function useSelection() {
  const [selected, set] = useState<string | null>(null)
  return { selected, select: set }
}

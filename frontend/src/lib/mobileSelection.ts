export type PointerType = 'mouse' | 'touch' | 'pen' | 'unknown'

export interface TapOpenCheckInput {
  pointerType: string | null | undefined
  multiSelectMode: boolean
  isShift: boolean
  isToggle: boolean
  selectedPaths: readonly string[]
  path: string
}

export function isTouchLikePointer(pointerType: string | null | undefined): boolean {
  return pointerType === 'touch' || pointerType === 'pen'
}

export function shouldOpenOnTap(input: TapOpenCheckInput): boolean {
  if (input.multiSelectMode) return false
  if (input.isShift || input.isToggle) return false
  if (!isTouchLikePointer(input.pointerType)) return false
  return input.selectedPaths.length === 1 && input.selectedPaths[0] === input.path
}

export function toggleSelectedPath(paths: readonly string[], path: string): string[] {
  if (!paths.includes(path)) return [...paths, path]
  return paths.filter((value) => value !== path)
}

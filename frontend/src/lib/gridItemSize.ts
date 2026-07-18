export const GRID_ITEM_SIZE_CONTRACT = {
  min: 80,
  max: 500,
  step: 10,
} as const

export function clampGridItemSize(value: number): number {
  return Math.min(GRID_ITEM_SIZE_CONTRACT.max, Math.max(GRID_ITEM_SIZE_CONTRACT.min, value))
}

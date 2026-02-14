type GridLoadingState = {
  similarityActive: boolean
  searching: boolean
  itemCount: number
  isLoading: boolean
}

export function shouldShowGridLoading(state: GridLoadingState): boolean {
  return (
    !state.similarityActive
    && !state.searching
    && state.itemCount === 0
    && state.isLoading
  )
}

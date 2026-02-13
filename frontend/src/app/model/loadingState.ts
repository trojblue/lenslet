type GridHydrationLoadingState = {
  similarityActive: boolean
  searching: boolean
  itemCount: number
  isLoading: boolean
  browseHydrationPending: boolean
}

export function shouldShowGridHydrationLoading(state: GridHydrationLoadingState): boolean {
  return (
    !state.similarityActive
    && !state.searching
    && state.itemCount === 0
    && (state.isLoading || state.browseHydrationPending)
  )
}

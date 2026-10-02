export type GridLoadingState = {
  similarityActive: boolean
  searching: boolean
  itemCount: number
  isLoading: boolean
}

export type GridStatusInput = GridLoadingState & {
  isFetching?: boolean
  isError?: boolean
  unavailableReason?: string | null
  filteredCount?: number
  filtersActive?: boolean
}

export type GridStatusKind =
  | 'ready'
  | 'loading'
  | 'updating'
  | 'empty'
  | 'failed'
  | 'unsupported'

export type GridStatus = {
  kind: GridStatusKind
  title: string
  message: string
  showCentered: boolean
}

export function shouldShowGridLoading(state: GridLoadingState): boolean {
  return (
    !state.similarityActive
    && !state.searching
    && state.itemCount === 0
    && state.isLoading
  )
}

export function resolveGridStatus(state: GridStatusInput): GridStatus {
  if (state.unavailableReason) {
    return {
      kind: 'unsupported',
      title: 'Query unavailable',
      message: state.unavailableReason,
      showCentered: state.itemCount === 0,
    }
  }

  if (state.isError) {
    return {
      kind: 'failed',
      title: 'Query failed',
      message: 'Retry the current query.',
      showCentered: state.itemCount === 0,
    }
  }

  if (!state.similarityActive && state.itemCount === 0 && state.isLoading) {
    return {
      kind: 'loading',
      title: 'Loading gallery...',
      message: 'Preparing gallery...',
      showCentered: true,
    }
  }

  if (state.itemCount > 0 && state.isFetching) {
    return {
      kind: 'updating',
      title: 'Updating results...',
      message: 'Your current view stays visible while results update.',
      showCentered: false,
    }
  }

  if (state.itemCount === 0) {
    const filteredCount = state.filteredCount ?? 0
    const hasQuery = state.searching || state.filtersActive || state.similarityActive
    const title = filteredCount > 0
      ? 'No items loaded'
      : hasQuery ? 'No matching images' : 'This folder has no images'
    const message = state.similarityActive
      ? 'No images match this similarity query. Adjust the query or exit similarity.'
      : state.searching
        ? 'No filenames, tags, or notes match this search. Change or clear the search.'
        : state.filtersActive
          ? 'No images match these filters. Clear filters to see all images.'
          : 'Choose another folder to browse images.'
    return {
      kind: 'empty',
      title,
      message,
      showCentered: true,
    }
  }

  return {
    kind: 'ready',
    title: 'Ready',
    message: '',
    showCentered: false,
  }
}

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
      message: 'Showing the previous window until the backend response arrives.',
      showCentered: false,
    }
  }

  if (state.itemCount === 0) {
    const filteredCount = state.filteredCount ?? 0
    return {
      kind: 'empty',
      title: filteredCount === 0 ? 'No matching items' : 'No items loaded',
      message: state.searching
        ? 'No filenames, tags, or notes match this search.'
        : 'No images match the current filters.',
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

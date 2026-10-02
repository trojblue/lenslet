import type { FacetFieldState } from '../model/facetPresentation'

interface FacetStatusProps {
  state: FacetFieldState
  subject: 'field' | 'metric'
  onRetry?: () => void
}

export default function FacetStatus({ state, subject, onRetry }: FacetStatusProps) {
  const message = state === 'pending'
    ? `Loading values for this ${subject}…`
    : state === 'error'
      ? `Could not load values for this ${subject}.`
      : `No values found for this ${subject}.`
  return (
    <div className="flex flex-col items-center gap-2">
      <span>{message}</span>
      {state === 'error' && onRetry && (
        <button type="button" className="btn btn-xs" onClick={onRetry}>Retry values</button>
      )}
    </div>
  )
}

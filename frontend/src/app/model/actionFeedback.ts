export type ActionFeedback = {
  kind: 'status' | 'error'
  message: string
}

function errorMessage(error: unknown): string | null {
  if (error instanceof Error && error.message.trim()) return error.message.trim()
  if (typeof error === 'string' && error.trim()) return error.trim()
  return null
}

export function buildActionErrorMessage(action: string, error: unknown): string {
  const detail = errorMessage(error)
  if (!detail) return action
  if (detail === action) return action
  return `${action}: ${detail}`
}

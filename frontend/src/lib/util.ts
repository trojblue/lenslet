export function fmtBytes(n: number): string {
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let idx = 0
  let val = n
  while (val >= 1024 && idx < units.length - 1) {
    val /= 1024
    idx += 1
  }
  return `${val.toFixed(1)} ${units[idx]}`
}

export function safeJsonParse<T>(raw: string | null): T | null {
  if (!raw) return null
  try {
    return JSON.parse(raw) as T
  } catch {
    return null
  }
}

export function middleTruncate(value: string, max = 28): string {
  if (value.length <= max) return value
  const keep = Math.max(4, Math.floor((max - 1) / 2))
  return `${value.slice(0, keep)}…${value.slice(-keep)}`
}

const ABSOLUTE_TIME_FORMATTER = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
})

export function parseTimestampMs(value: string | null | undefined): number | null {
  if (!value) return null
  const parsed = Date.parse(value)
  if (!Number.isFinite(parsed)) return null
  return parsed
}

export function formatRelativeTime(timestampMs: number, nowMs = Date.now()): string {
  const diffMs = Math.max(0, nowMs - timestampMs)
  const seconds = Math.max(1, Math.floor(diffMs / 1000))
  if (seconds < 60) return `${seconds} second${seconds === 1 ? '' : 's'} ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? '' : 's'} ago`
  const hours = Math.floor(minutes / 60)
  return `${hours} hour${hours === 1 ? '' : 's'} ago`
}

export function formatAbsoluteTime(timestampMs: number): string {
  return ABSOLUTE_TIME_FORMATTER.format(new Date(timestampMs))
}

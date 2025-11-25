/**
 * Format a byte count as a human-readable string.
 * @param n - Number of bytes
 * @param decimals - Number of decimal places (default 1)
 */
export function fmtBytes(n: number, decimals: number = 1): string {
  if (!Number.isFinite(n) || n < 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024
    i++
  }
  return `${n.toFixed(decimals)} ${units[i]}`
}

/**
 * Truncate a string from the middle, preserving the file extension.
 * @param name - The string to truncate
 * @param max - Maximum length (default 28)
 */
export function middleTruncate(name: string, max: number = 28): string {
  if (typeof name !== 'string') return ''
  if (name.length <= max) return name
  
  const dot = name.lastIndexOf('.')
  const ext = dot > 0 ? name.slice(dot) : ''
  const base = dot > 0 ? name.slice(0, dot) : name
  
  // Account for extension length in the max
  const maxBase = max - ext.length
  if (base.length <= maxBase) return name
  
  const left = Math.ceil((maxBase - 1) / 2)
  const right = Math.floor((maxBase - 1) / 2)
  return base.slice(0, left) + '…' + base.slice(-right) + ext
}

/**
 * Clamp a number between min and max values.
 */
export function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}

/**
 * Debounce a function call.
 */
export function debounce<T extends (...args: unknown[]) => void>(
  fn: T,
  delayMs: number
): (...args: Parameters<T>) => void {
  let timeoutId: ReturnType<typeof setTimeout> | undefined
  return (...args: Parameters<T>) => {
    if (timeoutId) clearTimeout(timeoutId)
    timeoutId = setTimeout(() => fn(...args), delayMs)
  }
}

/**
 * Throttle a function to run at most once per interval.
 */
export function throttle<T extends (...args: unknown[]) => void>(
  fn: T,
  intervalMs: number
): (...args: Parameters<T>) => void {
  let lastCall = 0
  let timeoutId: ReturnType<typeof setTimeout> | undefined
  
  return (...args: Parameters<T>) => {
    const now = Date.now()
    const remaining = intervalMs - (now - lastCall)
    
    if (remaining <= 0) {
      if (timeoutId) {
        clearTimeout(timeoutId)
        timeoutId = undefined
      }
      lastCall = now
      fn(...args)
    } else if (!timeoutId) {
      timeoutId = setTimeout(() => {
        lastCall = Date.now()
        timeoutId = undefined
        fn(...args)
      }, remaining)
    }
  }
}

/**
 * Create a stable ID from a path for use in DOM elements.
 */
export function pathToId(path: string): string {
  return `cell-${encodeURIComponent(path)}`
}

/**
 * Check if two arrays have the same items (shallow comparison).
 */
export function arraysEqual<T>(a: T[], b: T[]): boolean {
  if (a.length !== b.length) return false
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return false
  }
  return true
}

/**
 * Safely parse JSON, returning undefined on failure.
 */
export function safeJsonParse<T>(str: string): T | undefined {
  try {
    return JSON.parse(str) as T
  } catch {
    return undefined
  }
}

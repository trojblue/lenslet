type InspectorStoredValue<T> = {
  value: T
  rewriteValue?: string
}

function getInspectorStorage(): Storage | null {
  if (typeof window === 'undefined') return null
  try {
    return window.localStorage
  } catch {
    return null
  }
}

export function readInspectorStoredValue<T>(
  key: string,
  parse: (raw: string | null) => InspectorStoredValue<T>,
  fallback: T,
): T {
  const storage = getInspectorStorage()
  if (!storage) return fallback
  try {
    const parsed = parse(storage.getItem(key))
    if (parsed.rewriteValue !== undefined) {
      storage.setItem(key, parsed.rewriteValue)
    }
    return parsed.value
  } catch {
    return fallback
  }
}

export function writeInspectorStoredValue(key: string, value: string): void {
  const storage = getInspectorStorage()
  if (!storage) return
  try {
    storage.setItem(key, value)
  } catch {
    // Ignore persistence errors.
  }
}

export function writeInspectorStoredJson(key: string, value: unknown): void {
  writeInspectorStoredValue(key, JSON.stringify(value))
}

export function parseInspectorStoredBool(raw: string | null, fallback: boolean): boolean {
  if (raw === '1' || raw === 'true') return true
  if (raw === '0' || raw === 'false') return false
  return fallback
}

export function readInspectorStoredBool(key: string, fallback: boolean): boolean {
  return readInspectorStoredValue(
    key,
    (raw) => ({ value: parseInspectorStoredBool(raw, fallback) }),
    fallback,
  )
}

export function writeInspectorStoredBool(key: string, value: boolean): void {
  writeInspectorStoredValue(key, value ? '1' : '0')
}

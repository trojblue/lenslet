export type BrowseEndpoint = 'folders' | 'thumb' | 'file'

type EndpointCounts = Record<BrowseEndpoint, number>

export type BrowseRequestBudgetSnapshot = {
  limits: EndpointCounts
  inflight: EndpointCounts
  queued: EndpointCounts
  peakInflight: EndpointCounts
  updatedAtMs: number
}

export type BrowseHotpathSnapshot = {
  firstGridItemLatencyMs: number | null
  firstGridItemPath: string | null
  firstThumbnailLatencyMs: number | null
  firstThumbnailPath: string | null
  requestBudget: BrowseRequestBudgetSnapshot | null
}

declare global {
  interface Window {
    __lensletBrowseHotpath?: BrowseHotpathSnapshot
  }
}

const MARKERS = {
  browseStart: (requestId: number) => `lenslet:browse:load:start:${requestId}`,
  browseComplete: (requestId: number) => `lenslet:browse:load:complete:${requestId}`,
  firstGrid: (requestId: number) => `lenslet:browse:first-grid:${requestId}`,
  firstGridLatency: (requestId: number) => `lenslet:browse:first-grid-latency:${requestId}`,
  firstThumb: (requestId: number) => `lenslet:browse:first-thumb:${requestId}`,
  firstThumbLatency: (requestId: number) => `lenslet:browse:first-thumb-latency:${requestId}`,
} as const

type TelemetryState = {
  activeRequestId: number | null
  activeLoadStartedAtMs: number | null
  firstGridItemLatencyMs: number | null
  firstGridItemPath: string | null
  firstThumbnailLatencyMs: number | null
  firstThumbnailPath: string | null
  requestBudget: BrowseRequestBudgetSnapshot | null
}

const telemetryState: TelemetryState = {
  activeRequestId: null,
  activeLoadStartedAtMs: null,
  firstGridItemLatencyMs: null,
  firstGridItemPath: null,
  firstThumbnailLatencyMs: null,
  firstThumbnailPath: null,
  requestBudget: null,
}

function nowMs(): number {
  if (typeof performance !== 'undefined' && typeof performance.now === 'function') {
    return performance.now()
  }
  return Date.now()
}

function mark(name: string): void {
  if (typeof performance === 'undefined' || typeof performance.mark !== 'function') return
  try {
    performance.mark(name)
  } catch {
    // Ignore marker errors when unsupported.
  }
}

function measure(name: string, start: string, end: string): void {
  if (typeof performance === 'undefined' || typeof performance.measure !== 'function') return
  try {
    performance.measure(name, start, end)
  } catch {
    // Ignore measure errors when markers are missing.
  }
}

function publish(): void {
  if (typeof window === 'undefined') return
  window.__lensletBrowseHotpath = getBrowseHotpathSnapshot()
}

export function getBrowseHotpathSnapshot(): BrowseHotpathSnapshot {
  return {
    firstGridItemLatencyMs: telemetryState.firstGridItemLatencyMs,
    firstGridItemPath: telemetryState.firstGridItemPath,
    firstThumbnailLatencyMs: telemetryState.firstThumbnailLatencyMs,
    firstThumbnailPath: telemetryState.firstThumbnailPath,
    requestBudget: telemetryState.requestBudget ? { ...telemetryState.requestBudget } : null,
  }
}

export function reportBrowseRequestBudget(snapshot: BrowseRequestBudgetSnapshot): void {
  telemetryState.requestBudget = { ...snapshot }
  publish()
}

type BrowseLoadInput = {
  requestId: number
  path: string
}

export function startBrowseLoad(input: BrowseLoadInput): void {
  telemetryState.activeRequestId = input.requestId
  telemetryState.activeLoadStartedAtMs = nowMs()
  telemetryState.firstGridItemLatencyMs = null
  telemetryState.firstGridItemPath = null
  telemetryState.firstThumbnailLatencyMs = null
  telemetryState.firstThumbnailPath = null
  mark(MARKERS.browseStart(input.requestId))
  publish()
}

export function completeBrowseLoad(requestId: number): void {
  if (telemetryState.activeRequestId !== requestId) return
  mark(MARKERS.browseComplete(requestId))
  publish()
}

export function markFirstGridItemVisible(path: string): void {
  const requestId = telemetryState.activeRequestId
  const startMs = telemetryState.activeLoadStartedAtMs
  if (requestId == null || startMs == null) return
  if (telemetryState.firstGridItemLatencyMs != null) return
  const latency = Math.max(0, nowMs() - startMs)
  telemetryState.firstGridItemLatencyMs = Math.round(latency)
  telemetryState.firstGridItemPath = path
  const endMarker = MARKERS.firstGrid(requestId)
  mark(endMarker)
  measure(MARKERS.firstGridLatency(requestId), MARKERS.browseStart(requestId), endMarker)
  publish()
}

export function markFirstThumbnailRendered(path: string): void {
  const requestId = telemetryState.activeRequestId
  const startMs = telemetryState.activeLoadStartedAtMs
  if (requestId == null || startMs == null) return
  if (telemetryState.firstThumbnailLatencyMs != null) return
  const latency = Math.max(0, nowMs() - startMs)
  telemetryState.firstThumbnailLatencyMs = Math.round(latency)
  telemetryState.firstThumbnailPath = path
  const endMarker = MARKERS.firstThumb(requestId)
  mark(endMarker)
  measure(MARKERS.firstThumbLatency(requestId), MARKERS.browseStart(requestId), endMarker)
  publish()
}

export function resetBrowseHotpathForTests(): void {
  telemetryState.activeRequestId = null
  telemetryState.activeLoadStartedAtMs = null
  telemetryState.firstGridItemLatencyMs = null
  telemetryState.firstGridItemPath = null
  telemetryState.firstThumbnailLatencyMs = null
  telemetryState.firstThumbnailPath = null
  telemetryState.requestBudget = null
  publish()
}

publish()

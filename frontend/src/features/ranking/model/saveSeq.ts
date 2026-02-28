export function sanitizeSaveSeq(value: unknown): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 0
  const whole = Math.trunc(value)
  return whole < 0 ? 0 : whole
}

export function nextSaveSeq(current: number): number {
  return sanitizeSaveSeq(current) + 1
}

export function isStaleSaveResponse(responseSeq: number, latestIssuedSeq: number): boolean {
  return sanitizeSaveSeq(responseSeq) < sanitizeSaveSeq(latestIssuedSeq)
}


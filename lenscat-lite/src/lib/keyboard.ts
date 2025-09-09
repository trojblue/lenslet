type Handler = (e: KeyboardEvent) => void
export function onKey(key: string, handler: Handler) {
  const h = (e: KeyboardEvent) => { if (e.key === key) handler(e) }
  window.addEventListener('keydown', h)
  return () => window.removeEventListener('keydown', h)
}

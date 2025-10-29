export const fmtBytes = (n: number) => {
  const u = ['B','KB','MB','GB']; let i = 0; while (n >= 1024 && i < u.length-1) { n/=1024; i++ } return `${n.toFixed(1)} ${u[i]}`
}

export const middleTruncate = (name: string, max: number = 28) => {
  if (typeof name !== 'string') return ''
  if (name.length <= max) return name
  const dot = name.lastIndexOf('.')
  const ext = dot > 0 ? name.slice(dot) : ''
  const base = dot > 0 ? name.slice(0, dot) : name
  if (base.length <= max) return name
  const left = Math.ceil((max - 1) / 2)
  const right = Math.floor((max - 1) / 2)
  return base.slice(0, left) + '…' + base.slice(-right) + ext
}

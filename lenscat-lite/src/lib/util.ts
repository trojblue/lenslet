export const fmtBytes = (n: number) => {
  const u = ['B','KB','MB','GB']; let i = 0; while (n >= 1024 && i < u.length-1) { n/=1024; i++ } return `${n.toFixed(1)} ${u[i]}`
}

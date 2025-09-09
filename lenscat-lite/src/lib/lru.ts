export class LRU<K, V> {
  private map = new Map<K, V>()
  constructor(private cap = 300) {}
  get(k: K) { const v = this.map.get(k); if (v) { this.map.delete(k); this.map.set(k, v) } return v }
  set(k: K, v: V) {
    if (this.map.has(k)) this.map.delete(k)
    this.map.set(k, v)
    if (this.map.size > this.cap) { const first = this.map.keys().next().value; this.map.delete(first) }
  }
}

export class LRU<K, V> {
  private readonly map = new Map<K, V>()
  private readonly capacity: number

  constructor(capacity: number = 300) {
    this.capacity = Math.max(1, capacity)
  }

  get(k: K): V | undefined {
    const v = this.map.get(k)
    if (v !== undefined) {
      this.map.delete(k)
      this.map.set(k, v)
    }
    return v
  }

  has(k: K): boolean {
    return this.map.has(k)
  }

  set(k: K, v: V): void {
    if (this.map.has(k)) {
      this.map.delete(k)
    }
    this.map.set(k, v)

    if (this.map.size > this.capacity) {
      const oldest = this.map.keys().next().value
      if (oldest !== undefined) {
        this.map.delete(oldest)
      }
    }
  }

  delete(k: K): boolean {
    return this.map.delete(k)
  }

  clear(): void {
    this.map.clear()
  }

  get size(): number {
    return this.map.size
  }
}

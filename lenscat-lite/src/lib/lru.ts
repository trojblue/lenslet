/**
 * Simple LRU (Least Recently Used) cache.
 * Entries are evicted when capacity is exceeded.
 */
export class LRU<K, V> {
  private readonly map = new Map<K, V>()
  private readonly capacity: number

  constructor(capacity: number = 300) {
    this.capacity = Math.max(1, capacity)
  }

  /**
   * Get a value by key, refreshing its LRU position.
   * Returns undefined if not found.
   */
  get(k: K): V | undefined {
    const v = this.map.get(k)
    if (v !== undefined) {
      // Refresh LRU position
      this.map.delete(k)
      this.map.set(k, v)
    }
    return v
  }

  /**
   * Check if a key exists in the cache.
   */
  has(k: K): boolean {
    return this.map.has(k)
  }

  /**
   * Set a value, evicting the oldest entry if at capacity.
   */
  set(k: K, v: V): void {
    if (this.map.has(k)) {
      this.map.delete(k)
    }
    this.map.set(k, v)
    
    // Evict oldest entry if over capacity
    if (this.map.size > this.capacity) {
      const oldest = this.map.keys().next().value
      if (oldest !== undefined) {
        this.map.delete(oldest)
      }
    }
  }

  /**
   * Delete a key from the cache.
   */
  delete(k: K): boolean {
    return this.map.delete(k)
  }

  /**
   * Clear all entries.
   */
  clear(): void {
    this.map.clear()
  }

  /**
   * Get the current size of the cache.
   */
  get size(): number {
    return this.map.size
  }
}

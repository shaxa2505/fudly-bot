/**
 * LRU (Least Recently Used) Cache implementation with TTL support
 *
 * Features:
 * - Automatic eviction of least recently used items when maxSize is reached
 * - TTL (Time To Live) for cache entries
 * - Move accessed items to end (most recently used)
 * - Memory efficient (removes expired items on access)
 *
 * @example
 * const cache = new LRUCache(100, 30000) // 100 items, 30s TTL
 * cache.set('key', { data: 'value' })
 * const value = cache.get('key')
 * cache.clear()
 */
export class LRUCache {
  constructor(maxSize = 100, ttl = 30000) {
    this.maxSize = maxSize
    this.ttl = ttl
    this.cache = new Map()
  }

  /**
   * Get item from cache
   * Returns null if not found or expired
   */
  get(key) {
    const item = this.cache.get(key)

    if (!item) {
      return null
    }

    // Check if expired
    if (Date.now() - item.timestamp > this.ttl) {
      this.cache.delete(key)
      return null
    }

    // Move to end (mark as recently used)
    this.cache.delete(key)
    this.cache.set(key, item)

    return item.data
  }

  /**
   * Set item in cache
   * Evicts oldest item if maxSize is reached
   */
  set(key, data) {
    // Delete if already exists (to re-add at end)
    if (this.cache.has(key)) {
      this.cache.delete(key)
    }

    // Evict oldest if at capacity
    if (this.cache.size >= this.maxSize) {
      const oldestKey = this.cache.keys().next().value
      this.cache.delete(oldestKey)
    }

    // Add new item
    this.cache.set(key, {
      data,
      timestamp: Date.now(),
    })
  }

  /**
   * Check if key exists and is not expired
   */
  has(key) {
    const item = this.cache.get(key)

    if (!item) {
      return false
    }

    // Check if expired
    if (Date.now() - item.timestamp > this.ttl) {
      this.cache.delete(key)
      return false
    }

    return true
  }

  /**
   * Delete item from cache
   */
  delete(key) {
    return this.cache.delete(key)
  }

  /**
   * Clear all items
   */
  clear() {
    this.cache.clear()
  }

  /**
   * Get cache size
   */
  get size() {
    return this.cache.size
  }

  /**
   * Get all keys (excluding expired)
   */
  keys() {
    const now = Date.now()
    const validKeys = []

    for (const [key, item] of this.cache.entries()) {
      if (now - item.timestamp <= this.ttl) {
        validKeys.push(key)
      } else {
        // Clean up expired entries
        this.cache.delete(key)
      }
    }

    return validKeys
  }

  /**
   * Get cache statistics
   */
  getStats() {
    const now = Date.now()
    let expired = 0
    let valid = 0

    for (const item of this.cache.values()) {
      if (now - item.timestamp > this.ttl) {
        expired++
      } else {
        valid++
      }
    }

    return {
      size: this.cache.size,
      maxSize: this.maxSize,
      valid,
      expired,
      ttl: this.ttl,
    }
  }

  /**
   * Clean expired entries
   * Useful to run periodically
   */
  cleanup() {
    const now = Date.now()
    let cleaned = 0

    for (const [key, item] of this.cache.entries()) {
      if (now - item.timestamp > this.ttl) {
        this.cache.delete(key)
        cleaned++
      }
    }

    return cleaned
  }
}

export default LRUCache

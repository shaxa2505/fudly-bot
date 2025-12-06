import { describe, it, expect, beforeEach } from 'vitest'
import { LRUCache } from './lruCache'

describe('LRUCache', () => {
  let cache

  beforeEach(() => {
    cache = new LRUCache(3, 1000) // 3 items max, 1s TTL
  })

  it('should store and retrieve items', () => {
    cache.set('key1', 'value1')
    expect(cache.get('key1')).toBe('value1')
  })

  it('should return null for non-existent keys', () => {
    expect(cache.get('nonexistent')).toBe(null)
  })

  it('should respect TTL and expire items', async () => {
    cache.set('key1', 'value1')
    expect(cache.get('key1')).toBe('value1')

    // Wait for TTL to expire
    await new Promise(resolve => setTimeout(resolve, 1100))

    expect(cache.get('key1')).toBe(null)
  })

  it('should evict oldest item when max size is reached', () => {
    cache.set('key1', 'value1')
    cache.set('key2', 'value2')
    cache.set('key3', 'value3')
    cache.set('key4', 'value4') // This should evict key1

    expect(cache.get('key1')).toBe(null) // Evicted
    expect(cache.get('key2')).toBe('value2')
    expect(cache.get('key3')).toBe('value3')
    expect(cache.get('key4')).toBe('value4')
  })

  it('should move accessed items to end (LRU)', () => {
    cache.set('key1', 'value1')
    cache.set('key2', 'value2')
    cache.set('key3', 'value3')

    // Access key1 (moves to end)
    cache.get('key1')

    // Add key4 (should evict key2, not key1)
    cache.set('key4', 'value4')

    expect(cache.get('key1')).toBe('value1') // Still exists
    expect(cache.get('key2')).toBe(null) // Evicted
    expect(cache.get('key3')).toBe('value3')
    expect(cache.get('key4')).toBe('value4')
  })

  it('should check if key exists', () => {
    cache.set('key1', 'value1')
    expect(cache.has('key1')).toBe(true)
    expect(cache.has('key2')).toBe(false)
  })

  it('should delete items', () => {
    cache.set('key1', 'value1')
    expect(cache.has('key1')).toBe(true)

    cache.delete('key1')
    expect(cache.has('key1')).toBe(false)
  })

  it('should clear all items', () => {
    cache.set('key1', 'value1')
    cache.set('key2', 'value2')
    expect(cache.size).toBe(2)

    cache.clear()
    expect(cache.size).toBe(0)
  })

  it('should return cache size', () => {
    expect(cache.size).toBe(0)
    cache.set('key1', 'value1')
    expect(cache.size).toBe(1)
    cache.set('key2', 'value2')
    expect(cache.size).toBe(2)
  })

  it('should return valid keys (excluding expired)', async () => {
    cache.set('key1', 'value1')
    cache.set('key2', 'value2')

    await new Promise(resolve => setTimeout(resolve, 1100)) // Wait for expiry

    cache.set('key3', 'value3') // Fresh key

    const keys = cache.keys()
    expect(keys).toEqual(['key3'])
  })

  it('should provide cache statistics', async () => {
    cache.set('key1', 'value1')
    cache.set('key2', 'value2')

    await new Promise(resolve => setTimeout(resolve, 1100))

    cache.set('key3', 'value3')

    const stats = cache.getStats()
    expect(stats.size).toBe(3)
    expect(stats.maxSize).toBe(3)
    expect(stats.valid).toBe(1)
    expect(stats.expired).toBe(2)
    expect(stats.ttl).toBe(1000)
  })

  it('should cleanup expired entries', async () => {
    cache.set('key1', 'value1')
    cache.set('key2', 'value2')

    await new Promise(resolve => setTimeout(resolve, 1100))

    cache.set('key3', 'value3')

    const cleaned = cache.cleanup()
    expect(cleaned).toBe(2)
    expect(cache.size).toBe(1)
  })

  it('should handle updating existing keys', () => {
    cache.set('key1', 'value1')
    cache.set('key1', 'value2') // Update

    expect(cache.get('key1')).toBe('value2')
    expect(cache.size).toBe(1) // Should not increase size
  })
})

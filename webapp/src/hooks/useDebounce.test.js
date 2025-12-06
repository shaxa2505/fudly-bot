import { describe, it, expect, beforeEach, vi } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useDebounce, useDebouncedCallback } from './useDebounce'

describe('useDebounce', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('should return initial value immediately', () => {
    const { result } = renderHook(() => useDebounce('initial', 500))
    expect(result.current).toBe('initial')
  })

  it('should debounce value changes', async () => {
    const { result, rerender } = renderHook(
      ({ value }) => useDebounce(value, 500),
      { initialProps: { value: 'initial' } }
    )

    expect(result.current).toBe('initial')

    // Change value
    rerender({ value: 'updated' })

    // Value should not update immediately
    expect(result.current).toBe('initial')

    // Fast forward time
    act(() => {
      vi.advanceTimersByTime(500)
    })

    // Value should update after delay
    expect(result.current).toBe('updated')
  })

  it('should cancel previous timeout on rapid changes', () => {
    const { result, rerender } = renderHook(
      ({ value }) => useDebounce(value, 500),
      { initialProps: { value: 'initial' } }
    )

    // Change value multiple times rapidly
    rerender({ value: 'change1' })
    act(() => { vi.advanceTimersByTime(100) })

    rerender({ value: 'change2' })
    act(() => { vi.advanceTimersByTime(100) })

    rerender({ value: 'change3' })
    act(() => { vi.advanceTimersByTime(100) })

    // Value should still be initial
    expect(result.current).toBe('initial')

    // Fast forward remaining time
    act(() => {
      vi.advanceTimersByTime(500)
    })

    // Should only have the last value
    expect(result.current).toBe('change3')
  })

  it('should use custom delay', () => {
    const { result, rerender } = renderHook(
      ({ value }) => useDebounce(value, 1000),
      { initialProps: { value: 'initial' } }
    )

    rerender({ value: 'updated' })

    act(() => {
      vi.advanceTimersByTime(500)
    })
    expect(result.current).toBe('initial')

    act(() => {
      vi.advanceTimersByTime(500)
    })
    expect(result.current).toBe('updated')
  })
})

describe('useDebouncedCallback', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('should debounce callback execution', () => {
    const callback = vi.fn()
    const { result } = renderHook(() => useDebouncedCallback(callback, 500))

    // Call multiple times
    act(() => {
      result.current('call1')
      result.current('call2')
      result.current('call3')
    })

    // Callback should not be called yet
    expect(callback).not.toHaveBeenCalled()

    // Fast forward time
    act(() => {
      vi.advanceTimersByTime(500)
    })

    // Should only be called once with last value
    expect(callback).toHaveBeenCalledTimes(1)
    expect(callback).toHaveBeenCalledWith('call3')
  })

  it('should cleanup timeout on unmount', () => {
    const callback = vi.fn()
    const { result, unmount } = renderHook(() =>
      useDebouncedCallback(callback, 500)
    )

    act(() => {
      result.current('test')
    })

    // Unmount before timeout
    unmount()

    act(() => {
      vi.advanceTimersByTime(500)
    })

    // Callback should not be called after unmount
    expect(callback).not.toHaveBeenCalled()
  })
})

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useAsyncOperation, useAsyncState } from './useAsyncOperation'
import * as sentry from '../utils/sentry'

// Mock Sentry
vi.mock('../utils/sentry', () => ({
  captureException: vi.fn(),
}))

// Mock Telegram WebApp
global.window.Telegram = {
  WebApp: {
    showPopup: vi.fn(),
  },
}

describe('useAsyncOperation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should handle successful async operation', async () => {
    const { result } = renderHook(() => useAsyncOperation())

    expect(result.current.loading).toBe(false)
    expect(result.current.error).toBe(null)
    expect(result.current.data).toBe(null)

    const mockAsyncFn = vi.fn().mockResolvedValue({ id: 1, name: 'Test' })

    let returnedData
    await act(async () => {
      returnedData = await result.current.execute(mockAsyncFn)
    })

    expect(mockAsyncFn).toHaveBeenCalledTimes(1)
    expect(result.current.loading).toBe(false)
    expect(result.current.error).toBe(null)
    expect(result.current.data).toEqual({ id: 1, name: 'Test' })
    expect(returnedData).toEqual({ id: 1, name: 'Test' })
  })

  it('should handle async operation error', async () => {
    const { result } = renderHook(() => useAsyncOperation())

    const mockError = new Error('Test error')
    const mockAsyncFn = vi.fn().mockRejectedValue(mockError)

    await act(async () => {
      try {
        await result.current.execute(mockAsyncFn)
      } catch (error) {
        // Expected to throw
      }
    })

    expect(result.current.loading).toBe(false)
    expect(result.current.error).toBe('Test error')
    expect(result.current.data).toBe(null)
    expect(sentry.captureException).toHaveBeenCalledWith(
      mockError,
      expect.objectContaining({ context: 'operation' })
    )
  })

  it('should call onSuccess callback', async () => {
    const { result } = renderHook(() => useAsyncOperation())

    const mockAsyncFn = vi.fn().mockResolvedValue({ id: 1 })
    const onSuccess = vi.fn()

    await act(async () => {
      await result.current.execute(mockAsyncFn, { onSuccess })
    })

    expect(onSuccess).toHaveBeenCalledWith({ id: 1 })
  })

  it('should call onError callback', async () => {
    const { result } = renderHook(() => useAsyncOperation())

    const mockError = new Error('Test error')
    const mockAsyncFn = vi.fn().mockRejectedValue(mockError)
    const onError = vi.fn()

    await act(async () => {
      try {
        await result.current.execute(mockAsyncFn, { onError })
      } catch (error) {
        // Expected
      }
    })

    expect(onError).toHaveBeenCalledWith(mockError)
  })

  it('should abort previous request when new one starts', async () => {
    const { result } = renderHook(() => useAsyncOperation())

    const mockAsyncFn1 = vi.fn(
      (signal) =>
        new Promise((resolve) => {
          setTimeout(() => {
            if (!signal.aborted) resolve({ id: 1 })
          }, 100)
        })
    )

    const mockAsyncFn2 = vi.fn().mockResolvedValue({ id: 2 })

    // Start first request
    act(() => {
      result.current.execute(mockAsyncFn1)
    })

    // Start second request immediately
    await act(async () => {
      await result.current.execute(mockAsyncFn2)
    })

    // Second request should complete
    expect(result.current.data).toEqual({ id: 2 })
  })

  it('should handle AbortError gracefully', async () => {
    const { result } = renderHook(() => useAsyncOperation())

    const abortError = new Error('Aborted')
    abortError.name = 'AbortError'
    const mockAsyncFn = vi.fn().mockRejectedValue(abortError)

    let returnedData
    await act(async () => {
      returnedData = await result.current.execute(mockAsyncFn)
    })

    // Should not set error state for abort errors
    expect(result.current.error).toBe(null)
    expect(returnedData).toBe(null)
    expect(sentry.captureException).not.toHaveBeenCalled()
  })

  it('should cancel operation manually', async () => {
    const { result } = renderHook(() => useAsyncOperation())

    const mockAsyncFn = vi.fn(
      (signal) =>
        new Promise((resolve) => {
          setTimeout(() => {
            if (!signal.aborted) resolve({ id: 1 })
          }, 100)
        })
    )

    act(() => {
      result.current.execute(mockAsyncFn)
    })

    // Cancel manually
    act(() => {
      result.current.cancel()
    })

    // Wait a bit
    await waitFor(() => {}, { timeout: 150 })

    // Data should still be null (operation was cancelled)
    expect(result.current.data).toBe(null)
  })
})

describe('useAsyncState', () => {
  it('should manage loading and error state', () => {
    const { result } = renderHook(() => useAsyncState())

    expect(result.current.loading).toBe(false)
    expect(result.current.error).toBe(null)

    act(() => {
      result.current.setLoading(true)
    })

    expect(result.current.loading).toBe(true)

    act(() => {
      result.current.setError('Test error')
    })

    expect(result.current.loading).toBe(false)
    expect(result.current.error).toBe('Test error')
    expect(sentry.captureException).toHaveBeenCalled()
  })

  it('should reset state', () => {
    const { result } = renderHook(() => useAsyncState())

    act(() => {
      result.current.setLoading(true)
      result.current.setError('Error')
    })

    act(() => {
      result.current.reset()
    })

    expect(result.current.loading).toBe(false)
    expect(result.current.error).toBe(null)
  })
})

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useLocalStorage, useLocalStorageMultiple } from './useLocalStorage'

describe('useLocalStorage', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
  })

  it('should return initial value when key does not exist', () => {
    const { result } = renderHook(() => useLocalStorage('test-key', 'initial'))
    expect(result.current[0]).toBe('initial')
  })

  it('should save value to localStorage', () => {
    const { result } = renderHook(() => useLocalStorage('test-key', 'initial'))

    act(() => {
      result.current[1]('new value')
    })

    expect(result.current[0]).toBe('new value')
    expect(localStorage.getItem('test-key')).toBe(JSON.stringify('new value'))
  })

  it('should load existing value from localStorage', () => {
    localStorage.setItem('test-key', JSON.stringify('existing'))

    const { result } = renderHook(() => useLocalStorage('test-key', 'initial'))

    expect(result.current[0]).toBe('existing')
  })

  it('should handle function updater', () => {
    const { result } = renderHook(() => useLocalStorage('test-key', 0))

    act(() => {
      result.current[1](prev => prev + 1)
    })

    expect(result.current[0]).toBe(1)
  })

  it('should remove value from localStorage', () => {
    const { result } = renderHook(() => useLocalStorage('test-key', 'initial'))

    act(() => {
      result.current[1]('saved')
    })

    expect(localStorage.getItem('test-key')).toBeTruthy()

    act(() => {
      result.current[2]() // removeValue
    })

    expect(result.current[0]).toBe('initial')
    expect(localStorage.getItem('test-key')).toBeNull()
  })

  it('should handle complex objects', () => {
    const { result } = renderHook(() => useLocalStorage('test-key', { count: 0 }))

    act(() => {
      result.current[1]({ count: 5, name: 'test' })
    })

    expect(result.current[0]).toEqual({ count: 5, name: 'test' })
    
    const stored = JSON.parse(localStorage.getItem('test-key'))
    expect(stored).toEqual({ count: 5, name: 'test' })
  })

  it('should handle parse errors gracefully', () => {
    localStorage.setItem('test-key', 'invalid json')

    const { result } = renderHook(() => useLocalStorage('test-key', 'fallback'))

    expect(result.current[0]).toBe('fallback')
  })
})

describe('useLocalStorageMultiple', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
  })

  it('should manage multiple keys', () => {
    const { result } = renderHook(() => 
      useLocalStorageMultiple({
        user: null,
        theme: 'light',
        language: 'uz',
      })
    )

    expect(result.current.user.value).toBeNull()
    expect(result.current.theme.value).toBe('light')
    expect(result.current.language.value).toBe('uz')
  })

  it('should update individual keys', () => {
    const { result } = renderHook(() => 
      useLocalStorageMultiple({
        user: null,
        theme: 'light',
      })
    )

    act(() => {
      result.current.user.set({ id: 1, name: 'John' })
      result.current.theme.set('dark')
    })

    expect(result.current.user.value).toEqual({ id: 1, name: 'John' })
    expect(result.current.theme.value).toBe('dark')
  })

  it('should clear all keys', () => {
    const { result } = renderHook(() => 
      useLocalStorageMultiple({
        key1: 'value1',
        key2: 'value2',
      })
    )

    act(() => {
      result.current.key1.set('updated1')
      result.current.key2.set('updated2')
    })

    act(() => {
      result.current.clear()
    })

    expect(result.current.key1.value).toBe('value1')
    expect(result.current.key2.value).toBe('value2')
    expect(localStorage.getItem('key1')).toBeNull()
    expect(localStorage.getItem('key2')).toBeNull()
  })
})

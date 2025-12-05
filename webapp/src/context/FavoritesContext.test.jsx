import { describe, it, expect, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { FavoritesProvider, useFavorites } from './FavoritesContext'

const wrapper = ({ children }) => (
  <FavoritesProvider>{children}</FavoritesProvider>
)

describe('FavoritesContext', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('starts with empty favorites', () => {
    const { result } = renderHook(() => useFavorites(), { wrapper })
    expect(result.current.favorites).toEqual([])
  })

  it('adds item to favorites', () => {
    const { result } = renderHook(() => useFavorites(), { wrapper })
    const item = { id: 1, title: 'Test Item' }

    act(() => {
      result.current.toggleFavorite(item)
    })

    expect(result.current.favorites).toHaveLength(1)
    expect(result.current.isFavorite(1)).toBe(true)
  })

  it('removes item from favorites', () => {
    const { result } = renderHook(() => useFavorites(), { wrapper })
    const item = { id: 1, title: 'Test Item' }

    act(() => {
      result.current.toggleFavorite(item)
    })
    expect(result.current.isFavorite(1)).toBe(true)

    act(() => {
      result.current.toggleFavorite(item)
    })
    expect(result.current.isFavorite(1)).toBe(false)
  })

  it('persists favorites to localStorage', () => {
    const { result } = renderHook(() => useFavorites(), { wrapper })
    const item = { id: 1, title: 'Test Item' }

    act(() => {
      result.current.toggleFavorite(item)
    })

    const stored = JSON.parse(localStorage.getItem('fudly_favorites') || '[]')
    expect(stored).toHaveLength(1)
    expect(stored[0].id).toBe(1)
  })
})

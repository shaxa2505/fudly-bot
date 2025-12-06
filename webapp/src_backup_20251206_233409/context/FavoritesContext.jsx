import { createContext, useContext, useState, useEffect, useCallback } from 'react'

const FavoritesContext = createContext(null)

const STORAGE_KEY = 'fudly_favorites'

export function FavoritesProvider({ children }) {
  const [favorites, setFavorites] = useState(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY)
      return saved ? JSON.parse(saved) : []
    } catch {
      return []
    }
  })

  // Save to localStorage whenever favorites change
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(favorites))
    } catch (error) {
      console.error('Failed to save favorites:', error)
    }
  }, [favorites])

  const addToFavorites = useCallback((offer) => {
    setFavorites(prev => {
      // Check if already in favorites
      if (prev.some(item => item.id === offer.id)) {
        return prev
      }
      return [...prev, offer]
    })

    // Haptic feedback
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light')
  }, [])

  const removeFromFavorites = useCallback((offerId) => {
    setFavorites(prev => prev.filter(item => item.id !== offerId))

    // Haptic feedback
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light')
  }, [])

  const toggleFavorite = useCallback((offer) => {
    setFavorites(prev => {
      const exists = prev.some(item => item.id === offer.id)
      if (exists) {
        return prev.filter(item => item.id !== offer.id)
      }
      return [...prev, offer]
    })

    // Haptic feedback
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light')
  }, [])

  const isFavorite = useCallback((offerId) => {
    return favorites.some(item => item.id === offerId)
  }, [favorites])

  const clearFavorites = useCallback(() => {
    setFavorites([])
  }, [])

  const value = {
    favorites,
    favoritesCount: favorites.length,
    addToFavorites,
    removeFromFavorites,
    toggleFavorite,
    isFavorite,
    clearFavorites,
    isEmpty: favorites.length === 0
  }

  return (
    <FavoritesContext.Provider value={value}>
      {children}
    </FavoritesContext.Provider>
  )
}

export function useFavorites() {
  const context = useContext(FavoritesContext)
  if (!context) {
    throw new Error('useFavorites must be used within FavoritesProvider')
  }
  return context
}

export default FavoritesContext

import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react'
import api, { getTelegramInitData } from '../api/client'

const FavoritesContext = createContext(null)

const STORAGE_KEY = 'fudly_favorites'
const STORAGE_PREFIX = 'fudly_favorites_user_'

const resolveOfferId = (offer) => {
  if (!offer) return null
  const raw = offer.id ?? offer.offer_id ?? offer.offerId ?? null
  if (raw == null) return null
  const numeric = Number(raw)
  return Number.isNaN(numeric) ? raw : numeric
}

const normalizeOfferPhoto = (offer) => {
  if (!offer) return null
  return (
    offer.photo ||
    offer.photo_url ||
    offer.image_url ||
    offer.photoUrl ||
    offer.imageUrl ||
    offer.photo_id ||
    offer.offer_photo ||
    offer.offer_photo_url ||
    offer.image ||
    null
  )
}

const getSessionStorage = () => {
  try {
    return window.sessionStorage
  } catch {
    return null
  }
}

const getStorageKey = () => {
  const tgUserId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id
  if (tgUserId) {
    return `${STORAGE_PREFIX}${tgUserId}`
  }
  const lastUserId = getSessionStorage()?.getItem('fudly_last_user_id')
  if (lastUserId) {
    return `${STORAGE_PREFIX}${lastUserId}`
  }
  return STORAGE_KEY
}

const normalizeFavoriteOffer = (offer) => {
  const offerId = resolveOfferId(offer)
  if (!offerId) return null
  return {
    ...(offer.id ? offer : { ...offer, id: offerId }),
    photo: normalizeOfferPhoto(offer) || offer.photo
  }
}

const loadStoredFavorites = () => {
  try {
    const storageKey = getStorageKey()
    let saved = localStorage.getItem(storageKey)
    if (!saved && storageKey !== STORAGE_KEY) {
      saved = localStorage.getItem(STORAGE_KEY)
      if (saved) {
        localStorage.setItem(storageKey, saved)
      }
    }
    if (!saved) return []
    const parsed = JSON.parse(saved)
    if (!Array.isArray(parsed)) return []
    return parsed.map(normalizeFavoriteOffer).filter(Boolean)
  } catch {
    return []
  }
}

const canSyncFavorites = () => Boolean(getTelegramInitData())

export function FavoritesProvider({ children }) {
  const [favorites, setFavorites] = useState(() => loadStoredFavorites())
  const favoritesRef = useRef(favorites)

  useEffect(() => {
    favoritesRef.current = favorites
  }, [favorites])

  // Save to localStorage whenever favorites change
  useEffect(() => {
    try {
      const storageKey = getStorageKey()
      localStorage.setItem(storageKey, JSON.stringify(favorites))
    } catch (error) {
      console.error('Failed to save favorites:', error)
    }
  }, [favorites])

  useEffect(() => {
    let isMounted = true

    const syncFavorites = async () => {
      if (!canSyncFavorites()) return

      try {
        const remoteFavorites = await api.getFavoriteOffers()
        if (!isMounted) return

        const remoteList = Array.isArray(remoteFavorites) ? remoteFavorites : []
        const remoteMap = new Map()
        for (const offer of remoteList) {
          const normalized = normalizeFavoriteOffer(offer)
          if (normalized) {
            remoteMap.set(normalized.id, normalized)
          }
        }

        const localSnapshot = favoritesRef.current || []
        const missingIds = []
        for (const offer of localSnapshot) {
          const normalized = normalizeFavoriteOffer(offer)
          if (!normalized) continue
          if (!remoteMap.has(normalized.id)) {
            remoteMap.set(normalized.id, normalized)
            missingIds.push(normalized.id)
          }
        }

        if (missingIds.length > 0) {
          await Promise.allSettled(missingIds.map((id) => api.addFavorite(id)))
        }

        const merged = Array.from(remoteMap.values())
        setFavorites(merged)
      } catch (error) {
        console.warn('Favorite sync failed:', error)
      }
    }

    syncFavorites()
    return () => {
      isMounted = false
    }
  }, [])

  const addToFavorites = useCallback((offer) => {
    const offerId = resolveOfferId(offer)
    if (!offerId) {
      console.warn('Favorite skipped: missing offer id', offer)
      return
    }
    if (favoritesRef.current.some(item => item.id === offerId)) {
      return
    }
    const normalized = normalizeFavoriteOffer(offer)
    if (!normalized) return
    setFavorites(prev => {
      // Check if already in favorites
      if (prev.some(item => item.id === offerId)) {
        return prev
      }
      return [...prev, normalized]
    })

    if (canSyncFavorites()) {
      api.addFavorite(offerId).catch(() => {})
    }

    // Haptic feedback
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light')
  }, [])

  const removeFromFavorites = useCallback((offerId) => {
    const resolvedId = typeof offerId === 'object' ? resolveOfferId(offerId) : offerId
    if (!resolvedId) return
    const normalizedId = Number(resolvedId)
    const compareId = Number.isNaN(normalizedId) ? resolvedId : normalizedId
    setFavorites(prev => prev.filter(item => item.id !== compareId))

    if (canSyncFavorites()) {
      api.removeFavorite(compareId).catch(() => {})
    }

    // Haptic feedback
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light')
  }, [])

  const toggleFavorite = useCallback((offer) => {
    const offerId = resolveOfferId(offer)
    if (!offerId) {
      console.warn('Favorite toggle skipped: missing offer id', offer)
      return
    }
    const normalized = normalizeFavoriteOffer(offer)
    if (!normalized) return
    const exists = favoritesRef.current.some(item => item.id === offerId)
    setFavorites(prev => {
      const exists = prev.some(item => item.id === offerId)
      if (exists) {
        return prev.filter(item => item.id !== offerId)
      }
      return [...prev, normalized]
    })

    if (canSyncFavorites()) {
      const syncAction = exists ? api.removeFavorite(offerId) : api.addFavorite(offerId)
      syncAction.catch(() => {})
    }

    // Haptic feedback
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light')
  }, [])

  const isFavorite = useCallback((offerId) => {
    const resolvedId = typeof offerId === 'object' ? resolveOfferId(offerId) : offerId
    if (!resolvedId) return false
    const normalizedId = Number(resolvedId)
    const compareId = Number.isNaN(normalizedId) ? resolvedId : normalizedId
    return favorites.some(item => item.id === compareId)
  }, [favorites])

  const clearFavorites = useCallback(() => {
    setFavorites([])
    if (canSyncFavorites()) {
      const ids = favoritesRef.current.map((item) => item.id).filter(Boolean)
      if (ids.length > 0) {
        Promise.allSettled(ids.map((id) => api.removeFavorite(id))).catch(() => {})
      }
    }
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

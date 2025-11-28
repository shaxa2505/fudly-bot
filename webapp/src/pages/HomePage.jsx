import { useState, useEffect, useRef, useCallback } from 'react'
import api from '../api/client'
import OfferCard from '../components/OfferCard'
import BottomNav from '../components/BottomNav'
import './HomePage.css'

const CATEGORIES = [
  { id: 'all', name: 'Barchasi' },
  { id: 'dairy', name: 'Sut' },
  { id: 'bakery', name: 'Non' },
  { id: 'meat', name: "Go'sht" },
  { id: 'sweets', name: 'Shirinliklar' },
  { id: 'drinks', name: 'Ichimliklar' },
  { id: 'frozen', name: 'Muzlatilgan' },
]

function HomePage({ onNavigate, tg }) {
  const [offers, setOffers] = useState([])
  const [loading, setLoading] = useState(false)
  const [selectedCategory, setSelectedCategory] = useState('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [favorites, setFavorites] = useState(new Set())
  const [cart, setCart] = useState(() => {
    const saved = localStorage.getItem('fudly_cart')
    return saved ? new Map(Object.entries(JSON.parse(saved))) : new Map()
  })
  const [hasMore, setHasMore] = useState(true)
  const [offset, setOffset] = useState(0)
  const observerTarget = useRef(null)

  // Load offers
  const loadOffers = useCallback(async (reset = false) => {
    if (loading) return

    setLoading(true)
    try {
      const currentOffset = reset ? 0 : offset
      const data = await api.getOffers({
        category: selectedCategory,
        search: searchQuery || undefined,
        limit: 20,
        offset: currentOffset,
      })

      if (reset) {
        setOffers(data)
        setOffset(20)
      } else {
        setOffers(prev => [...prev, ...data])
        setOffset(prev => prev + 20)
      }

      setHasMore(data.length === 20)
    } catch (error) {
      console.error('Error loading offers:', error)
      tg?.showAlert?.('Xatolik yuz berdi')
    } finally {
      setLoading(false)
    }
  }, [selectedCategory, searchQuery, offset, loading, tg])

  // Load favorites
  useEffect(() => {
    const loadFavorites = async () => {
      try {
        const data = await api.getFavorites()
        setFavorites(new Set(data.map(o => o.id)))
      } catch (error) {
        console.error('Error loading favorites:', error)
      }
    }
    loadFavorites()
  }, [])

  // Initial load
  useEffect(() => {
    loadOffers(true)
  }, [selectedCategory, searchQuery])

  // Infinite scroll
  useEffect(() => {
    const observer = new IntersectionObserver(
      entries => {
        if (entries[0].isIntersecting && hasMore && !loading) {
          loadOffers(false)
        }
      },
      { threshold: 0.1 }
    )

    if (observerTarget.current) {
      observer.observe(observerTarget.current)
    }

    return () => observer.disconnect()
  }, [hasMore, loading, loadOffers])

  // Save cart to localStorage
  useEffect(() => {
    localStorage.setItem('fudly_cart', JSON.stringify(Object.fromEntries(cart)))
  }, [cart])

  const toggleFavorite = async (offerId) => {
    try {
      if (favorites.has(offerId)) {
        await api.removeFavorite(offerId)
        setFavorites(prev => {
          const next = new Set(prev)
          next.delete(offerId)
          return next
        })
      } else {
        await api.addFavorite(offerId)
        setFavorites(prev => new Set(prev).add(offerId))
        tg?.HapticFeedback?.impactOccurred?.('light')
      }
    } catch (error) {
      console.error('Error toggling favorite:', error)
    }
  }

  const addToCart = (offer) => {
    setCart(prev => {
      const next = new Map(prev)
      const current = next.get(offer.id) || 0
      next.set(offer.id, current + 1)
      return next
    })
    tg?.HapticFeedback?.impactOccurred?.('medium')
  }

  const cartCount = Array.from(cart.values()).reduce((sum, qty) => sum + qty, 0)

  return (
    <div className="home-page">
      {/* Header */}
      <header className="header">
        <div className="header-content">
          <h1 className="logo">fudly.</h1>
          <div className="search-container">
            <input
              type="text"
              className="search-input"
              placeholder="Mahsulot qidirish..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            {searchQuery && (
              <button
                className="search-clear"
                onClick={() => setSearchQuery('')}
              >
                ✕
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Categories */}
      <div className="categories-wrapper">
        <div className="categories">
          {CATEGORIES.map(cat => (
            <button
              key={cat.id}
              className={`category-btn ${selectedCategory === cat.id ? 'active' : ''}`}
              onClick={() => setSelectedCategory(cat.id)}
            >
              <span className="category-name">{cat.name}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Location */}
      <div className="location-banner">
        <div className="location-content">
          <span className="location-icon">📍</span>
          <div className="location-text">
            <span className="location-label">Manzilni belgilang</span>
            <span className="location-value">Yarim soatda yetkazamiz</span>
          </div>
        </div>
      </div>

      {/* Section Title */}
      <div className="section-header">
        <h2 className="section-title">Barcha mahsulotlar</h2>
        <span className="section-count">{offers.length} ta</span>
      </div>

      {/* Offers Grid */}
      <div className="offers-grid">
        {loading && offers.length === 0 ? (
          Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="offer-card skeleton">
              <div className="skeleton-image" />
              <div className="skeleton-text" />
              <div className="skeleton-text short" />
            </div>
          ))
        ) : (
          offers.map(offer => (
            <OfferCard
              key={offer.id}
              offer={offer}
              isFavorite={favorites.has(offer.id)}
              onToggleFavorite={() => toggleFavorite(offer.id)}
              onAddToCart={() => addToCart(offer)}
            />
          ))
        )}
      </div>

      {/* Loading more */}
      {hasMore && (
        <div ref={observerTarget} className="loading-more">
          {loading && <div className="spinner" />}
        </div>
      )}

      {/* Bottom Navigation */}
      <BottomNav
        currentPage="home"
        onNavigate={onNavigate}
        cartCount={cartCount}
        favoritesCount={favorites.size}
      />
    </div>
  )
}

export default HomePage

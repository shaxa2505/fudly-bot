import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Flame, Milk, Cookie, Coffee as Beverage, Croissant, Beef, Apple, Salad, Package, Search } from 'lucide-react'
import api from '../api/client'
import { useCart } from '../context/CartContext'
import { transliterateCity, getSavedLocation, saveLocation, DEFAULT_LOCATION } from '../utils/cityUtils'
import OfferCard from '../components/OfferCard'
import OfferCardSkeleton from '../components/OfferCardSkeleton'
import HeroBanner from '../components/HeroBanner'
import FlashDeals from '../components/FlashDeals'
import BottomNav from '../components/BottomNav'
import PullToRefresh from '../components/PullToRefresh'
import RecentlyViewed from '../components/RecentlyViewed'
import { usePullToRefresh } from '../hooks/usePullToRefresh'
import './HomePage.css'

const CATEGORIES = [
  { id: 'all', name: 'Barchasi', icon: Flame, color: '#FF6B35' },
  { id: 'dairy', name: 'Sut', icon: Milk, color: '#2196F3' },
  { id: 'snacks', name: 'Sneklar', icon: Cookie, color: '#FF9800' },
  { id: 'drinks', name: 'Ichimlik', icon: Beverage, color: '#4CAF50' },
  { id: 'bakery', name: 'Non', icon: Croissant, color: '#8D6E63' },
  { id: 'meat', name: "Go'sht", icon: Beef, color: '#E53935' },
  { id: 'fruits', name: 'Meva', icon: Apple, color: '#F44336' },
  { id: 'vegetables', name: 'Sabzavot', icon: Salad, color: '#43A047' },
  { id: 'other', name: 'Boshqa', icon: Package, color: '#78909C' },
]

function HomePage() {
  const navigate = useNavigate()
  const [offers, setOffers] = useState([])
  const [loading, setLoading] = useState(false)
  const [selectedCategory, setSelectedCategory] = useState('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [location, setLocation] = useState(getSavedLocation)
  const [isLocating, setIsLocating] = useState(false)
  const [locationError, setLocationError] = useState('')
  const [showAddressModal, setShowAddressModal] = useState(false)
  const [manualCity, setManualCity] = useState(location.city)
  const [manualAddress, setManualAddress] = useState(location.address)

  // Quick filters state
  const [minDiscount, setMinDiscount] = useState(null) // null, 20, 30, 50
  const [sortBy, setSortBy] = useState('default') // default, discount, price_asc, price_desc

  // Search history state
  const [searchHistory, setSearchHistory] = useState([])
  const [showSearchHistory, setShowSearchHistory] = useState(false)
  const searchInputRef = useRef(null)

  // Use cart from context instead of local state
  const { addToCart, removeFromCart, getQuantity, cartCount } = useCart()

  const [hasMore, setHasMore] = useState(true)
  const [offset, setOffset] = useState(0)
  const formattedAddress = location.address
    ? location.address
        .split(',')
        .map(part => part.trim())
        .filter(Boolean)
        .slice(0, 3)
        .join(', ')
    : ''
  const hasPreciseLocation = Boolean(location.coordinates || location.address)
  const observerTarget = useRef(null)
  const autoLocationAttempted = useRef(null)

  // Извлекаем название города для API (без страны) и транслитерируем в кириллицу
  const cityRaw = location.city
    ? location.city.split(',')[0].trim()
    : 'Toshkent'
  const cityForApi = transliterateCity(cityRaw)

  useEffect(() => {
    saveLocation(location)
  }, [location])

  // Load search history on mount
  useEffect(() => {
    const loadSearchHistory = async () => {
      const userId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id
      if (userId) {
        try {
          const history = await api.getSearchHistory(userId, 5)
          setSearchHistory(history)
        } catch (error) {
          console.error('Error loading search history:', error)
        }
      }
    }
    loadSearchHistory()
  }, [])

  // Save search query to history when searching
  const handleSearchSubmit = useCallback(async () => {
    if (searchQuery.trim().length >= 2) {
      const userId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id
      if (userId) {
        try {
          await api.addSearchHistory(userId, searchQuery.trim())
          // Update local history
          setSearchHistory(prev => {
            const filtered = prev.filter(q => q.toLowerCase() !== searchQuery.trim().toLowerCase())
            return [searchQuery.trim(), ...filtered].slice(0, 5)
          })
        } catch (error) {
          console.error('Error saving search history:', error)
        }
      }
    }
    setShowSearchHistory(false)
  }, [searchQuery])

  // Handle search history item click
  const handleHistoryClick = (query) => {
    setSearchQuery(query)
    setShowSearchHistory(false)
  }

  // Clear search history
  const handleClearHistory = async () => {
    const userId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id
    if (userId) {
      try {
        await api.clearSearchHistory(userId)
        setSearchHistory([])
      } catch (error) {
        console.error('Error clearing search history:', error)
      }
    }
    setShowSearchHistory(false)
  }

  // Автоопределение локации при первом запуске
  useEffect(() => {
    if (autoLocationAttempted.current) return
    autoLocationAttempted.current = true

    // Если уже есть сохранённый адрес - не запрашиваем
    if (location.address || location.coordinates) return

    // Пытаемся определить автоматически
    if (navigator.geolocation) {
      setIsLocating(true)
      navigator.geolocation.getCurrentPosition(
        (position) => {
          const { latitude, longitude } = position.coords
          reverseGeocodeAuto(latitude, longitude)
        },
        (error) => {
          console.log('Auto-geolocation denied or failed:', error.message)
          setIsLocating(false)
          // Если отклонил - показываем модалку ручного ввода
          if (error.code === error.PERMISSION_DENIED) {
            setShowAddressModal(true)
          }
        },
        { enableHighAccuracy: true, timeout: 10000, maximumAge: 300000 }
      )
    }
  }, [])

  // Функция для автоматического геокодирования (при старте)
  const reverseGeocodeAuto = async (lat, lon) => {
    try {
      const response = await fetch(
        `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat}&lon=${lon}&accept-language=uz`,
        { headers: { 'User-Agent': 'FudlyApp/1.0' } }
      )
      if (!response.ok) throw new Error('Geo lookup failed')
      const data = await response.json()

      const city = data.address?.city || data.address?.town || data.address?.village || ''
      const state = data.address?.state || ''
      const primaryCity = city || state || 'Toshkent'
      const normalizedCity = primaryCity.includes("O'zbekiston") ? primaryCity : `${primaryCity}, O'zbekiston`

      setLocation({
        city: normalizedCity,
        address: data.display_name || '',
        coordinates: { lat, lon },
        region: state, // Сохраняем область
      })
      setLocationError('')
    } catch (error) {
      console.error('Reverse geocode error', error)
      setLocationError('Manzilni aniqlab bo\'lmadi')
    } finally {
      setIsLocating(false)
    }
  }

  const [showingAllCities, setShowingAllCities] = useState(false)

  // Load offers - сначала по городу, если пусто - из всех городов
  const loadOffers = useCallback(async (reset = false, forceAllCities = false) => {
    if (loading) return

    setLoading(true)
    try {
      const currentOffset = reset ? 0 : offset
      const params = {
        limit: 20,
        offset: currentOffset,
      }

      // Если не forceAllCities - фильтруем по городу
      if (!forceAllCities && !showingAllCities) {
        params.city = cityForApi
      }

      // Добавляем категорию только если выбрана конкретная (не "all")
      if (selectedCategory && selectedCategory !== 'all') {
        params.category = selectedCategory
      }

      // Добавляем поиск только если есть запрос
      if (searchQuery.trim()) {
        params.search = searchQuery.trim()
      }

      // Добавляем фильтр по скидке
      if (minDiscount) {
        params.min_discount = minDiscount
      }

      // Добавляем сортировку
      if (sortBy !== 'default') {
        params.sort_by = sortBy
      }

      const data = await api.getOffers(params)

      // Если город пустой и это первая загрузка - загружаем из всех городов
      if (reset && (!data || data.length === 0) && !forceAllCities && !showingAllCities) {
        setShowingAllCities(true)
        setLoading(false)
        return loadOffers(true, true)
      }

      if (reset) {
        setOffers(data || [])
        setOffset(20)
        if (forceAllCities) setShowingAllCities(true)
      } else {
        setOffers(prev => [...prev, ...(data || [])])
        setOffset(prev => prev + 20)
      }

      setHasMore((data?.length || 0) === 20)
    } catch (error) {
      console.error('Error loading offers:', error)
    } finally {
      setLoading(false)
    }
  }, [selectedCategory, searchQuery, offset, loading, cityForApi, showingAllCities, minDiscount, sortBy])

  // Pull-to-refresh handler
  const handleRefresh = useCallback(async () => {
    setShowingAllCities(false)
    await loadOffers(true)
  }, [loadOffers])

  // Pull-to-refresh hook
  const { isPulling, isRefreshing, pullDistance, progress } = usePullToRefresh(handleRefresh)

  // Initial load and search with debounce
  useEffect(() => {
    setShowingAllCities(false) // Сбрасываем при смене города/фильтров
    const timer = setTimeout(() => {
      loadOffers(true)
    }, searchQuery ? 500 : 0)

    return () => clearTimeout(timer)
  }, [selectedCategory, searchQuery, cityForApi, minDiscount, sortBy])

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

  // Cart is now saved automatically via CartContext

  const reverseGeocode = async (lat, lon) => {
    try {
      const response = await fetch(
        `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat}&lon=${lon}&accept-language=uz`,
        { headers: { 'User-Agent': 'FudlyApp/1.0' } }
      )
      if (!response.ok) throw new Error('Geo lookup failed')
      const data = await response.json()

      const city = data.address?.city || data.address?.town || data.address?.village || ''
      const state = data.address?.state || ''
      const primaryCity = city || state || 'Toshkent'
      const normalizedCity = primaryCity.includes("O'zbekiston") ? primaryCity : `${primaryCity}, O'zbekiston`

      setLocation({
        city: normalizedCity,
        address: data.display_name || '',
        coordinates: { lat, lon },
        region: state,
      })
      setLocationError('')
      setShowAddressModal(false) // Закрываем модалку после успешного определения
    } catch (error) {
      console.error('Reverse geocode error', error)
      setLocationError('Manzilni aniqlab bo\'lmadi')
    } finally {
      setIsLocating(false)
    }
  }

  const handleDetectLocation = () => {
    if (!navigator.geolocation) {
      setLocationError('Qurilmada geolokatsiya qo\'llab-quvvatlanmaydi')
      return
    }
    setIsLocating(true)
    setLocationError('')
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const { latitude, longitude } = position.coords
        reverseGeocode(latitude, longitude)
      },
      (error) => {
        console.error('Geolocation error', error)
        if (error.code === error.PERMISSION_DENIED) {
          setLocationError('Geolokatsiyaga ruxsat berilmadi. Brauzer sozlamalaridan ruxsat bering.')
        } else if (error.code === error.TIMEOUT) {
          setLocationError('Joylashuvni aniqlash vaqti tugadi. Qayta urinib ko\'ring.')
        } else {
          setLocationError('Geolokatsiyani olish imkonsiz')
        }
        setIsLocating(false)
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
    )
  }

  const openAddressModal = () => {
    setManualCity(location.city)
    setManualAddress(location.address)
    setShowAddressModal(true)
  }

  const handleSaveManualAddress = () => {
    const trimmedCity = manualCity.trim()
    const trimmedAddress = manualAddress.trim()
    setLocation(prev => ({
      city: trimmedCity || DEFAULT_LOCATION.city,
      address: trimmedAddress,
      coordinates: trimmedAddress ? prev.coordinates : null,
    }))
    setShowAddressModal(false)
    setLocationError('')
  }

  // Cart functions now come from useCart() hook

  return (
    <div className="home-page">
      {/* Pull-to-Refresh */}
      <PullToRefresh
        isRefreshing={isRefreshing}
        pullDistance={pullDistance}
        progress={progress}
      />

      {/* Header */}
      <header className="header">
        <div className="header-top">
          <button className="header-location" onClick={openAddressModal}>
            <div className="header-location-icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" stroke="var(--color-primary)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                <circle cx="12" cy="10" r="3" stroke="var(--color-primary)" strokeWidth="2"/>
              </svg>
            </div>
            <div className="header-location-text">
              <span className="header-location-label">Yetkazish</span>
              <span className="header-location-city">
                {cityRaw}
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none">
                  <path d="M6 9l6 6 6-6" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </span>
            </div>
          </button>
          <div className="header-actions">
            <button className="header-action-btn" onClick={() => navigate('/favorites')} aria-label="Sevimlilar">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
            <button className="header-action-btn" onClick={() => navigate('/profile')} aria-label="Profil">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="8" r="4" stroke="currentColor" strokeWidth="2"/>
                <path d="M6 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
              </svg>
            </button>
          </div>
        </div>
        <div className="header-search">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" className="search-icon">
            <circle cx="11" cy="11" r="8" stroke="currentColor" strokeWidth="2"/>
            <path d="M21 21l-4.35-4.35" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
          </svg>
          <input
            ref={searchInputRef}
            type="text"
            className="search-input"
            placeholder="Mahsulot qidirish..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onFocus={() => setShowSearchHistory(true)}
            onBlur={() => setTimeout(() => setShowSearchHistory(false), 200)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearchSubmit()}
          />
          {searchQuery && (
            <button className="search-clear" onClick={() => setSearchQuery('')}>
              ✕
            </button>
          )}

          {/* Search History Dropdown */}
          {showSearchHistory && searchHistory.length > 0 && !searchQuery && (
            <div className="search-history-dropdown">
              <div className="search-history-header">
                <span>So'nggi qidiruvlar</span>
                <button className="search-history-clear" onClick={handleClearHistory}>
                  Tozalash
                </button>
              </div>
              {searchHistory.map((query, index) => (
                <button
                  key={index}
                  className="search-history-item"
                  onMouseDown={() => handleHistoryClick(query)}
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                    <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2"/>
                    <path d="M12 6v6l4 2" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                  </svg>
                  <span>{query}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </header>

      {/* Quick Actions */}
      <div className="quick-actions">
        <button className="quick-action" onClick={() => navigate('/profile')}>
          <div className="quick-action-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
              <path d="M17 1l4 4-4 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M3 11V9a4 4 0 0 1 4-4h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M7 23l-4-4 4-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M21 13v2a4 4 0 0 1-4 4H3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </div>
          <span className="quick-action-text">Takrorlash</span>
        </button>
        <button className="quick-action" onClick={() => navigate('/favorites')}>
          <div className="quick-action-icon accent">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
              <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </div>
          <span className="quick-action-text">Sevimlilar</span>
        </button>
        <button className="quick-action" onClick={() => navigate('/profile')}>
          <div className="quick-action-icon purple">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
              <rect x="2" y="3" width="20" height="14" rx="2" stroke="currentColor" strokeWidth="2"/>
              <path d="M8 21h8M12 17v4" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            </svg>
          </div>
          <span className="quick-action-text">Buyurtmalar</span>
        </button>
        <button className="quick-action" onClick={() => navigate('/cart')}>
          <div className="quick-action-icon orange">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
              <path d="M9 22a1 1 0 1 0 0-2 1 1 0 0 0 0 2zM20 22a1 1 0 1 0 0-2 1 1 0 0 0 0 2z" stroke="currentColor" strokeWidth="2"/>
              <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </div>
          <span className="quick-action-text">Savat</span>
        </button>
      </div>

      {/* Hero Banner Carousel */}
      <HeroBanner onCategorySelect={(category) => {
        setSelectedCategory(category)
        setTimeout(() => {
          document.querySelector('.section-header')?.scrollIntoView({ behavior: 'smooth' })
        }, 100)
      }} />

      {/* Flash Deals - temporarily disabled until API deployed
      {selectedCategory === 'all' && !searchQuery && (
        <FlashDeals city={cityForApi} />
      )}
      */}

      {/* Unified Filter Bar */}
      <div className="filter-bar">
        {/* Categories Scroll */}
        <div className="filter-scroll">
          {CATEGORIES.map(cat => {
            const IconComponent = cat.icon
            return (
              <button
                key={cat.id}
                className={`filter-pill ${selectedCategory === cat.id ? 'active' : ''}`}
                onClick={() => {
                  window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light')
                  setSelectedCategory(cat.id)
                }}
                style={{ '--pill-color': cat.color }}
              >
                <IconComponent
                  size={18}
                  strokeWidth={2}
                  className="filter-pill-icon"
                  aria-hidden="true"
                />
                <span className="filter-pill-text">{cat.name}</span>
              </button>
            )
          })}

          {/* Divider */}
          <div className="filter-divider" />

          {/* Discount Filters */}
          <button
            className={`filter-pill discount ${minDiscount === 20 ? 'active' : ''}`}
            onClick={() => {
              window.Telegram?.WebApp?.HapticFeedback?.selectionChanged?.()
              setMinDiscount(minDiscount === 20 ? null : 20)
            }}
          >
            <span className="filter-pill-icon">🏷️</span>
            <span className="filter-pill-text">20%+</span>
          </button>
          <button
            className={`filter-pill discount ${minDiscount === 30 ? 'active' : ''}`}
            onClick={() => {
              window.Telegram?.WebApp?.HapticFeedback?.selectionChanged?.()
              setMinDiscount(minDiscount === 30 ? null : 30)
            }}
          >
            <span className="filter-pill-icon">🔥</span>
            <span className="filter-pill-text">30%+</span>
          </button>
          <button
            className={`filter-pill discount ${minDiscount === 50 ? 'active' : ''}`}
            onClick={() => {
              window.Telegram?.WebApp?.HapticFeedback?.selectionChanged?.()
              setMinDiscount(minDiscount === 50 ? null : 50)
            }}
          >
            <span className="filter-pill-icon">💥</span>
            <span className="filter-pill-text">50%+</span>
          </button>
        </div>

        {/* Sort Button */}
        <div className="filter-sort">
          <button
            className={`sort-btn ${sortBy !== 'default' ? 'active' : ''}`}
            onClick={() => {
              window.Telegram?.WebApp?.HapticFeedback?.selectionChanged?.()
              // Cycle through sort options
              const options = ['default', 'discount', 'price_asc', 'price_desc']
              const idx = options.indexOf(sortBy)
              setSortBy(options[(idx + 1) % options.length])
            }}
          >
            <span className="sort-btn-icon">
              {sortBy === 'discount' ? '🏷️' : sortBy === 'price_asc' ? '↑' : sortBy === 'price_desc' ? '↓' : '⇅'}
            </span>
            <span>
              {sortBy === 'discount' ? 'Chegirma' : sortBy === 'price_asc' ? 'Arzon' : sortBy === 'price_desc' ? 'Qimmat' : 'Tartiblash'}
            </span>
          </button>
        </div>
      </div>

      {/* Recently Viewed - Show only on home without search */}
      {selectedCategory === 'all' && !searchQuery && (
        <RecentlyViewed />
      )}

      {/* Section Title */}
      <div className="section-header">
        <h2 className="section-title">
          {selectedCategory === 'all' ? 'Barcha takliflar' : CATEGORIES.find(c => c.id === selectedCategory)?.name}
        </h2>
        <span className="offers-count">{offers.length} ta</span>
      </div>

      {/* Info banner if showing all cities */}
      {showingAllCities && offers.length > 0 && (
        <div className="all-cities-banner">
          <span className="all-cities-icon">🌍</span>
          <span className="all-cities-text">
            {cityRaw} da mahsulot yo'q. Barcha shaharlardan ko'rsatilmoqda
          </span>
        </div>
      )}

      {/* Offers Grid */}
      <div className="offers-grid">
        {loading && offers.length === 0 ? (
          Array.from({ length: 6 }).map((_, i) => (
            <OfferCardSkeleton key={i} />
          ))
        ) : offers.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">
              <Search size={80} strokeWidth={1.5} color="#7C7C7C" aria-hidden="true" />
            </div>
            <h3 className="empty-state-title">Hech narsa topilmadi</h3>
            <p className="empty-state-text">
              "{searchQuery}" so'zi bilan hech qanday mahsulot topilmadi.
              Boshqa so'z bilan qidirib ko'ring yoki filterni o'zgartiring.
            </p>
            <button
              className="btn-primary"
              onClick={() => {
                setSearchQuery('')
                setSelectedCategory('all')
              }}
            >
              Filterni tozalash
            </button>
          </div>
        ) : (
          offers.map((offer, index) => (
            <div
              key={offer.id}
              className="offer-card-wrapper animate-in"
              style={{ animationDelay: `${Math.min(index, 5) * 60}ms` }}
            >
              <OfferCard
                offer={offer}
                cartQuantity={getQuantity(offer.id)}
                onAddToCart={addToCart}
                onRemoveFromCart={removeFromCart}
              />
            </div>
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
        cartCount={cartCount}
      />

      {showAddressModal && (
        <div className="address-modal-overlay" onClick={() => setShowAddressModal(false)}>
          <div className="address-modal" onClick={(e) => e.stopPropagation()}>
            <div className="address-modal-header">
              <h3>Manzilni kiriting</h3>
              <button className="address-modal-close" onClick={() => setShowAddressModal(false)} aria-label="Yopish">
                ×
              </button>
            </div>

            {/* Кнопка автоопределения */}
            <button
              className="address-detect-btn"
              onClick={handleDetectLocation}
              disabled={isLocating}
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="2"/>
                <path d="M12 2v4M12 18v4M2 12h4M18 12h4" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
              </svg>
              {isLocating ? "Aniqlanmoqda..." : "Joylashuvni aniqlash"}
            </button>

            {locationError && (
              <div className="address-error">{locationError}</div>
            )}

            <div className="address-divider">
              <span>yoki</span>
            </div>

            <label className="address-label">
              Shahar yoki hudud
              <input
                type="text"
                value={manualCity}
                onChange={(e) => setManualCity(e.target.value)}
                className="address-input"
                placeholder="Masalan, Toshkent, O'zbekiston"
              />
            </label>
            <label className="address-label">
              Aniq manzil
              <textarea
                value={manualAddress}
                onChange={(e) => setManualAddress(e.target.value)}
                className="address-textarea"
                placeholder="Ko'cha, uy, blok, mo'ljal"
              />
            </label>
            <div className="address-modal-actions">
              <button className="address-btn secondary" onClick={() => setShowAddressModal(false)}>
                Bekor qilish
              </button>
              <button className="address-btn" onClick={handleSaveManualAddress}>
                Saqlash
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default HomePage

import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Flame, Milk, Cookie, Snowflake, Coffee as Beverage, Croissant, Beef, Apple, Salad, Package, Search, Info } from 'lucide-react'
import api from '../api/client'
import { useCart } from '../context/CartContext'
import { transliterateCity, getSavedLocation, saveLocation, DEFAULT_LOCATION } from '../utils/cityUtils'
import OfferCard from '../components/OfferCard'
import OfferCardSkeleton from '../components/OfferCardSkeleton'
import HeroBanner from '../components/HeroBanner'
import FlashDeals from '../components/FlashDeals'
import BottomNav from '../components/BottomNav'
import PullToRefresh from '../components/PullToRefresh'
import { usePullToRefresh } from '../hooks/usePullToRefresh'
import { blurOnEnter } from '../utils/helpers'
import './HomePage.css'

const CATEGORIES = [
  { id: 'all', name: 'Barchasi', icon: Flame, color: '#FF6B35' },
  { id: 'dairy', name: 'Sut', icon: Milk, color: '#2196F3' },
  { id: 'bakery', name: 'Non', icon: Croissant, color: '#8D6E63' },
  { id: 'meat', name: "Go'sht", icon: Beef, color: '#E53935' },
  { id: 'fruits', name: 'Meva', icon: Apple, color: '#F44336' },
  { id: 'vegetables', name: 'Sabzavot', icon: Salad, color: '#43A047' },
  { id: 'drinks', name: 'Ichimlik', icon: Beverage, color: '#4CAF50' },
  { id: 'sweets', name: 'Shirinlik', icon: Cookie, color: '#F59E0B' },
  { id: 'frozen', name: 'Muzlatilgan', icon: Snowflake, color: '#3B82F6' },
  { id: 'other', name: 'Boshqa', icon: Package, color: '#78909C' },
]

const CATEGORY_ALIASES = {
  sweets: ['sweets', 'snacks'],
}

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
  const [priceRange, setPriceRange] = useState('all') // all, up_20, 20_50, 50_100, 100_plus
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false)

  // Search history state
  const [searchHistory, setSearchHistory] = useState([])
  const [showSearchHistory, setShowSearchHistory] = useState(false)
  const searchInputRef = useRef(null)
  const manualSearchRef = useRef(0)

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
  const loadingRef = useRef(false)
  const offsetRef = useRef(0)
  const activeFiltersCount = [minDiscount, priceRange !== 'all', sortBy !== 'default']
    .filter(Boolean)
    .length

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

  const [showingAllCities, setShowingAllCities] = useState(false)

  // Load offers - сначала по городу, если пусто - из всех городов
  const loadOffers = useCallback(async (reset = false, forceAllCities = false) => {
    if (loadingRef.current) return

    loadingRef.current = true
    setLoading(true)
    try {
      const currentOffset = reset ? 0 : offsetRef.current
      const params = {
        limit: 20,
        offset: currentOffset,
      }

      // Если не forceAllCities - фильтруем по городу
      if (!forceAllCities && !showingAllCities) {
        params.city = cityForApi
      }

      const categoryAlias = CATEGORY_ALIASES[selectedCategory]
      if (selectedCategory && selectedCategory !== 'all' && !categoryAlias) {
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

      if (priceRange !== 'all') {
        if (priceRange === 'up_20') {
          params.max_price = 20000
        } else if (priceRange === '20_50') {
          params.min_price = 20000
          params.max_price = 50000
        } else if (priceRange === '50_100') {
          params.min_price = 50000
          params.max_price = 100000
        } else if (priceRange === '100_plus') {
          params.min_price = 100000
        }
      }

      // Добавляем сортировку
      if (sortBy !== 'default') {
        params.sort_by = sortBy
      }

      const data = await api.getOffers(params)
      const dataList = Array.isArray(data?.offers) ? data.offers : (Array.isArray(data) ? data : [])
      let nextOffers = dataList
      const normalizedQuery = searchQuery.trim().toLowerCase()

      if (normalizedQuery.length >= 2) {
        nextOffers = nextOffers.filter(offer => {
          const title = String(offer.title || '').toLowerCase()
          const store = String(offer.store_name || '').toLowerCase()
          return title.includes(normalizedQuery) || store.includes(normalizedQuery)
        })
      }

      if (categoryAlias) {
        nextOffers = nextOffers.filter(offer => categoryAlias.includes(String(offer.category || '').toLowerCase()))
      }

      if (minDiscount || priceRange !== 'all' || sortBy !== 'default') {
        nextOffers = nextOffers.filter(offer => {
          const discountPrice = Number(offer.discount_price || 0)
          const original = Number(offer.original_price || 0)
          const hasDiscount = original > discountPrice

          if (minDiscount) {
            if (!hasDiscount) return false
            const percent = Math.round((1 - discountPrice / original) * 100)
            if (percent < minDiscount) return false
          }

          if (priceRange !== 'all') {
            if (priceRange === 'up_20' && discountPrice > 20000) return false
            if (priceRange === '20_50' && (discountPrice < 20000 || discountPrice > 50000)) return false
            if (priceRange === '50_100' && (discountPrice < 50000 || discountPrice > 100000)) return false
            if (priceRange === '100_plus' && discountPrice < 100000) return false
          }

          return true
        })

        if (sortBy === 'discount') {
          nextOffers = [...nextOffers].sort((a, b) => {
            const aOriginal = Number(a.original_price || 0)
            const bOriginal = Number(b.original_price || 0)
            const aDiscount = Number(a.discount_price || 0)
            const bDiscount = Number(b.discount_price || 0)
            const aPercent = aOriginal > aDiscount ? Math.round((1 - aDiscount / aOriginal) * 100) : 0
            const bPercent = bOriginal > bDiscount ? Math.round((1 - bDiscount / bOriginal) * 100) : 0
            return bPercent - aPercent
          })
        } else if (sortBy === 'price_asc') {
          nextOffers = [...nextOffers].sort((a, b) => Number(a.discount_price || 0) - Number(b.discount_price || 0))
        } else if (sortBy === 'price_desc') {
          nextOffers = [...nextOffers].sort((a, b) => Number(b.discount_price || 0) - Number(a.discount_price || 0))
        }
      }

      // Если город пустой и это первая загрузка - загружаем из всех городов
      if (reset && dataList.length === 0 && !forceAllCities && !showingAllCities) {
        setShowingAllCities(true)
        loadingRef.current = false
        setLoading(false)
        return loadOffers(true, true)
      }

      if (reset) {
        setOffers(nextOffers || [])
        offsetRef.current = 20
        setOffset(20)
        if (forceAllCities) setShowingAllCities(true)
      } else {
        setOffers(prev => [...prev, ...(nextOffers || [])])
        offsetRef.current = offsetRef.current + 20
        setOffset(offsetRef.current)
      }

      setHasMore((dataList?.length || 0) === 20)
    } catch (error) {
      console.error('Error loading offers:', error)
    } finally {
      loadingRef.current = false
      setLoading(false)
    }
  }, [selectedCategory, searchQuery, cityForApi, showingAllCities, minDiscount, sortBy, priceRange])

  // Save search query to history when searching
  const handleSearchSubmit = useCallback(async () => {
    const trimmed = searchQuery.trim()
    searchInputRef.current?.blur()
    setShowSearchHistory(false)

    if (!trimmed) {
      manualSearchRef.current = Date.now()
      await loadOffers(true)
      return
    }

    if (trimmed.length >= 2) {
      const userId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id
      if (userId) {
        try {
          await api.addSearchHistory(userId, trimmed)
          // Update local history
          setSearchHistory(prev => {
            const filtered = prev.filter(q => q.toLowerCase() !== trimmed.toLowerCase())
            return [trimmed, ...filtered].slice(0, 5)
          })
        } catch (error) {
          console.error('Error saving search history:', error)
        }
      }
      manualSearchRef.current = Date.now()
      await loadOffers(true)
    }
  }, [searchQuery, loadOffers])

  // Handle search history item click
  const handleHistoryClick = (query) => {
    setSearchQuery(query)
    setShowSearchHistory(false)
    searchInputRef.current?.blur()
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


  // Pull-to-refresh handler
  const handleRefresh = useCallback(async () => {
    setShowingAllCities(false)
    await loadOffers(true)
  }, [loadOffers])

  // Pull-to-refresh hook
  const { isPulling, isRefreshing, pullDistance, progress } = usePullToRefresh(handleRefresh)

  // Initial load and search with debounce
  useEffect(() => {
    setShowingAllCities(false) // ?????????? ??? ????? ??????/????????
    const recentlyManual = Date.now() - manualSearchRef.current < 300
    if (recentlyManual) return

    const trimmed = searchQuery.trim()
    if (trimmed && trimmed.length < 2) {
      return
    }

    const timer = setTimeout(() => {
      loadOffers(true)
    }, trimmed ? 500 : 0)

    return () => clearTimeout(timer)
  }, [selectedCategory, searchQuery, cityForApi, minDiscount, sortBy, priceRange, loadOffers])

  // Infinite scroll
  useEffect(() => {
    const observer = new IntersectionObserver(
      entries => {
        if (entries[0].isIntersecting && hasMore) {
          loadOffers(false)
        }
      },
      { threshold: 0.1 }
    )

    if (observerTarget.current) {
      observer.observe(observerTarget.current)
    }

    return () => observer.disconnect()
  }, [hasMore, loadOffers])

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
      </header>

      {/* Subheader (Search) */}
      <div className="home-subheader">
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
            onKeyDown={(e) => blurOnEnter(e, handleSearchSubmit)}
          />
          {searchQuery && (
            <button
              className="search-clear"
              onClick={() => setSearchQuery('')}
              aria-label="Qidiruvni tozalash"
            >
              x
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
      <div className="filters-section">
        <div className="filters-primary">
          <div className="filters-scroll">
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
          </div>
          <button
            className={`filters-toggle ${showAdvancedFilters ? 'active' : ''}`}
            onClick={() => {
              window.Telegram?.WebApp?.HapticFeedback?.selectionChanged?.()
              setShowAdvancedFilters(prev => !prev)
            }}
            aria-expanded={showAdvancedFilters}
          >
            Filtrlar
            {activeFiltersCount > 0 && (
              <span className="filters-count">{activeFiltersCount}</span>
            )}
          </button>
        </div>

        {showAdvancedFilters && (
          <div className="filters-advanced">
            <div className="filter-group">
              <span className="filter-group-label">Chegirma</span>
              <div className="filter-group-row">
                <button
                  className={`filter-pill discount ${minDiscount === 20 ? 'active' : ''}`}
                  onClick={() => {
                    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged?.()
                    setMinDiscount(minDiscount === 20 ? null : 20)
                  }}
                >
                  <span className="filter-pill-icon">%</span>
                  <span className="filter-pill-text">20%+</span>
                </button>
                <button
                  className={`filter-pill discount ${minDiscount === 30 ? 'active' : ''}`}
                  onClick={() => {
                    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged?.()
                    setMinDiscount(minDiscount === 30 ? null : 30)
                  }}
                >
                  <span className="filter-pill-icon">%</span>
                  <span className="filter-pill-text">30%+</span>
                </button>
                <button
                  className={`filter-pill discount ${minDiscount === 50 ? 'active' : ''}`}
                  onClick={() => {
                    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged?.()
                    setMinDiscount(minDiscount === 50 ? null : 50)
                  }}
                >
                  <span className="filter-pill-icon">%</span>
                  <span className="filter-pill-text">50%+</span>
                </button>
              </div>
            </div>

            <div className="filter-group">
              <span className="filter-group-label">Narx</span>
              <div className="filter-group-row">
                <button
                  className={`filter-pill ${priceRange === 'up_20' ? 'active' : ''}`}
                  onClick={() => {
                    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged?.()
                    setPriceRange(priceRange === 'up_20' ? 'all' : 'up_20')
                  }}
                >
                  <span className="filter-pill-icon">sum</span>
                  <span className="filter-pill-text">0-20k</span>
                </button>
                <button
                  className={`filter-pill ${priceRange === '20_50' ? 'active' : ''}`}
                  onClick={() => {
                    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged?.()
                    setPriceRange(priceRange === '20_50' ? 'all' : '20_50')
                  }}
                >
                  <span className="filter-pill-icon">sum</span>
                  <span className="filter-pill-text">20-50k</span>
                </button>
                <button
                  className={`filter-pill ${priceRange === '50_100' ? 'active' : ''}`}
                  onClick={() => {
                    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged?.()
                    setPriceRange(priceRange === '50_100' ? 'all' : '50_100')
                  }}
                >
                  <span className="filter-pill-icon">sum</span>
                  <span className="filter-pill-text">50-100k</span>
                </button>
                <button
                  className={`filter-pill ${priceRange === '100_plus' ? 'active' : ''}`}
                  onClick={() => {
                    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged?.()
                    setPriceRange(priceRange === '100_plus' ? 'all' : '100_plus')
                  }}
                >
                  <span className="filter-pill-icon">sum</span>
                  <span className="filter-pill-text">100k+</span>
                </button>
              </div>
            </div>

            <div className="filter-group">
              <span className="filter-group-label">Tartib</span>
              <select
                className="sort-select"
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value)}
              >
                <option value="default">Standart</option>
                <option value="discount">Chegirma yuqori</option>
                <option value="price_asc">Arzonroq</option>
                <option value="price_desc">Qimmatroq</option>
              </select>
            </div>
          </div>
        )}
      </div>

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
          <span className="all-cities-icon" aria-hidden="true">
            <Info size={16} strokeWidth={2.2} />
          </span>
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
                setMinDiscount(null)
                setPriceRange('all')
                setSortBy('default')
              }}
            >
              Filterni tozalash
            </button>
          </div>
        ) : (
          offers.map((offer, index) => {
            const offerKey = offer.id || offer.offer_id || `${offer.store_id || 'store'}-${offer.title || 'offer'}-${index}`
            return (
              <div
                key={offerKey}
                className="offer-card-wrapper"
              >
                <OfferCard
                  offer={offer}
                  cartQuantity={getQuantity(offer.id || offer.offer_id)}
                  onAddToCart={addToCart}
                  onRemoveFromCart={removeFromCart}
                />
              </div>
            )
          })
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
                x
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
                onKeyDown={blurOnEnter}
                className="address-input"
                placeholder="Masalan, Toshkent, O'zbekiston"
              />
            </label>
            <label className="address-label">
              Aniq manzil
              <textarea
                value={manualAddress}
                onChange={(e) => setManualAddress(e.target.value)}
                onKeyDown={blurOnEnter}
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

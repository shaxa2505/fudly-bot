import { useState, useEffect, useRef, useCallback } from 'react'
import { Flame, Milk, Cookie, Snowflake, Coffee as Beverage, Croissant, Beef, Apple, Salad, Package, Search, SlidersHorizontal } from 'lucide-react'
import api from '../api/client'
import { useCart } from '../context/CartContext'
import { transliterateCity, getSavedLocation, saveLocation, DEFAULT_LOCATION, normalizeLocationName } from '../utils/cityUtils'
import OfferCard from '../components/OfferCard'
import OfferCardSkeleton from '../components/OfferCardSkeleton'
import HeroBanner from '../components/HeroBanner'
import RecentlyViewed from '../components/RecentlyViewed'
import BottomNav from '../components/BottomNav'
import PullToRefresh from '../components/PullToRefresh'
import { usePullToRefresh } from '../hooks/usePullToRefresh'
import { getScrollContainer } from '../utils/scrollContainer'
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

const CATEGORY_IDS = new Set(CATEGORIES.map(category => category.id))
const OFFERS_LIMIT = 20

const normalizeCategoryId = (value) => {
  const raw = String(value || '').toLowerCase().trim()
  if (!raw) return 'other'
  if (CATEGORY_IDS.has(raw)) return raw
  const aliasEntry = Object.entries(CATEGORY_ALIASES)
    .find(([, aliases]) => aliases.includes(raw))
  if (aliasEntry) return aliasEntry[0]
  return 'other'
}

function HomePage() {
  const [offers, setOffers] = useState([])
  const [offersTotal, setOffersTotal] = useState(null)
  const [loading, setLoading] = useState(false)
  const [selectedCategory, setSelectedCategory] = useState('all')
  const [activeCategory, setActiveCategory] = useState('all')
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
  const [categoryCounts, setCategoryCounts] = useState({})
  const [categoriesLoading, setCategoriesLoading] = useState(false)

  // Search history state
  const [searchHistory, setSearchHistory] = useState([])
  const [showSearchHistory, setShowSearchHistory] = useState(false)
  const [searchFocused, setSearchFocused] = useState(false)
  const [searchSuggestions, setSearchSuggestions] = useState([])
  const [suggestionsLoading, setSuggestionsLoading] = useState(false)
  const searchInputRef = useRef(null)
  const categoriesScrollRef = useRef(null)
  const categoryTabRefs = useRef(new Map())
  const categoryMarkersRef = useRef([])
  const activeCategoryRef = useRef(activeCategory)
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
  const offersCountValue = offersTotal ?? offers.length
  const offersCountLabel = hasMore && offersTotal == null
    ? `${offersCountValue}+ ta`
    : `${offersCountValue} ta`
  const trimmedSearch = searchQuery.trim()
  const showHistoryDropdown = showSearchHistory && !trimmedSearch && searchHistory.length > 0
  const showSuggestionsDropdown = showSearchHistory && trimmedSearch.length >= 2
  const showSearchDropdown = showHistoryDropdown || showSuggestionsDropdown

  const registerCategoryTab = useCallback((id, node) => {
    if (node) {
      categoryTabRefs.current.set(id, node)
    } else {
      categoryTabRefs.current.delete(id)
    }
  }, [])

  const handleCategorySelect = useCallback((categoryId, options = {}) => {
    const { withHaptic = true } = options
    if (withHaptic) {
      window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light')
    }
    setSelectedCategory(categoryId)
    setActiveCategory(categoryId)
  }, [])

  useEffect(() => {
    activeCategoryRef.current = activeCategory
  }, [activeCategory])

  useEffect(() => {
    setActiveCategory(selectedCategory)
  }, [selectedCategory])

  useEffect(() => {
    categoryMarkersRef.current = Array.from(
      document.querySelectorAll('.home-page [data-category-id]')
    )
  }, [offers, selectedCategory])

  // Sync active tab with scroll position when showing all categories.
  useEffect(() => {
    if (selectedCategory !== 'all' || searchQuery.trim()) return
    let rafId = 0

    const updateActiveFromScroll = () => {
      rafId = 0
      const markers = categoryMarkersRef.current
      if (!markers.length) return

      const subheader = document.querySelector('.home-subheader')
      const stickyOffset = subheader
        ? Math.max(subheader.getBoundingClientRect().bottom, 0) + 4
        : 0

      let candidate = null
      for (const marker of markers) {
        const rect = marker.getBoundingClientRect()
        if (rect.bottom <= stickyOffset) continue
        candidate = marker
        break
      }

      if (!candidate) return
      const nextCategory = normalizeCategoryId(candidate.dataset.categoryId || 'all')
      if (nextCategory !== activeCategoryRef.current) {
        setActiveCategory(nextCategory)
      }
    }

    const onScroll = () => {
      if (rafId) return
      rafId = window.requestAnimationFrame(updateActiveFromScroll)
    }

    const scrollContainer = getScrollContainer()
    if (!scrollContainer) {
      updateActiveFromScroll()
      return () => {
        if (rafId) window.cancelAnimationFrame(rafId)
      }
    }

    scrollContainer.addEventListener('scroll', onScroll, { passive: true })
    updateActiveFromScroll()

    return () => {
      scrollContainer.removeEventListener('scroll', onScroll)
      if (rafId) window.cancelAnimationFrame(rafId)
    }
  }, [selectedCategory, searchQuery, offers])

  useEffect(() => {
    const container = categoriesScrollRef.current
    const tab = categoryTabRefs.current.get(activeCategory)
    if (!container || !tab) return

    const containerRect = container.getBoundingClientRect()
    const tabRect = tab.getBoundingClientRect()
    const leftDelta = tabRect.left - containerRect.left
    const rightDelta = tabRect.right - containerRect.right

    if (leftDelta < 0) {
      container.scrollBy({ left: leftDelta - 12, behavior: 'smooth' })
    } else if (rightDelta > 0) {
      container.scrollBy({ left: rightDelta + 12, behavior: 'smooth' })
    }
  }, [activeCategory])


  // Извлекаем название города для API (без страны) и транслитерируем в кириллицу
  const cityRaw = location.city
    ? location.city.split(',')[0].trim()
    : ''
  const cityForApi = cityRaw ? transliterateCity(cityRaw) : ''
  const cityLabel = cityRaw || 'Shahar tanlang'
  const isLocationUnset = !cityRaw && !location.coordinates

  useEffect(() => {
    saveLocation(location)
  }, [location])

  // Load search history on mount
  useEffect(() => {
    const loadSearchHistory = async () => {
      const userId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id
      if (userId) {
        try {
          const history = await api.getSearchHistory(5)
          setSearchHistory(history)
        } catch (error) {
          console.error('Error loading search history:', error)
        }
      }
    }
    loadSearchHistory()
  }, [])

  useEffect(() => {
    let isActive = true

    const loadCategories = async () => {
      setCategoriesLoading(true)
      try {
        const params = {}
        if (cityForApi) {
          params.city = cityForApi
        }
        const data = await api.getCategories(params)
        if (!isActive) return
        const counts = {}
        if (Array.isArray(data)) {
          data.forEach((item) => {
            if (!item?.id) return
            counts[item.id] = Number(item.count) || 0
          })
        }
        setCategoryCounts(counts)
      } catch (error) {
        console.error('Error loading categories:', error)
        if (isActive) {
          setCategoryCounts({})
        }
      } finally {
        if (isActive) {
          setCategoriesLoading(false)
        }
      }
    }

    loadCategories()
    return () => {
      isActive = false
    }
  }, [cityForApi])
  // Load offers - сначала по городу, если пусто - из всех городов
  const loadOffers = useCallback(async (reset = false, options = {}) => {
    const { searchOverride, force = false } = options
    const searchValue = typeof searchOverride === 'string' ? searchOverride : searchQuery
    if (loadingRef.current) return

    loadingRef.current = true
    setLoading(true)
    try {
      const currentOffset = reset ? 0 : offsetRef.current
      const params = {
        limit: OFFERS_LIMIT,
        offset: currentOffset,
        include_meta: true,
      }
      if (cityForApi) {
        params.city = cityForApi
      }
      if (location.coordinates?.lat != null && location.coordinates?.lon != null) {
        params.lat = location.coordinates.lat
        params.lon = location.coordinates.lon
      }

      if (location.region) {
        params.region = location.region
      }
      if (location.district) {
        params.district = location.district
      }

      if (selectedCategory && selectedCategory !== 'all') {
        params.category = selectedCategory
      }

      // Добавляем поиск только если есть запрос
      if (searchValue.trim()) {
        params.search = searchValue.trim()
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
      } else {
        params.sort_by = 'urgent'
      }

      const data = await api.getOffers(params, { force })
      const items = Array.isArray(data?.items)
        ? data.items
        : (Array.isArray(data?.offers) ? data.offers : (Array.isArray(data) ? data : []))
      const total = Number.isFinite(data?.total) ? data.total : null
      const hasMoreResult = typeof data?.has_more === 'boolean'
        ? data.has_more
        : items.length === OFFERS_LIMIT
      const nextOffset = Number.isFinite(data?.next_offset) ? data.next_offset : null

      if (reset) {
        setOffers(items || [])
        offsetRef.current = nextOffset ?? items.length
        setOffset(offsetRef.current)
        setOffersTotal(total)
      } else {
        setOffers(prev => [...prev, ...(items || [])])
        offsetRef.current = nextOffset ?? offsetRef.current + items.length
        setOffset(offsetRef.current)
        if (total != null) {
          setOffersTotal(total)
        }
      }

      setHasMore(hasMoreResult)
    } catch (error) {
      console.error('Error loading offers:', error)
    } finally {
      loadingRef.current = false
      setLoading(false)
    }
  }, [
    selectedCategory,
    searchQuery,
    cityForApi,
    location.region,
    location.district,
    location.coordinates?.lat,
    location.coordinates?.lon,
    minDiscount,
    sortBy,
    priceRange,
  ])

  // Save search query to history when searching
  const handleSearchSubmit = useCallback(async (queryOverride) => {
    const nextQuery = typeof queryOverride === 'string' ? queryOverride : searchQuery
    const trimmed = nextQuery.trim()
    if (typeof queryOverride === 'string') {
      setSearchQuery(nextQuery)
    }
    searchInputRef.current?.blur()
    setShowSearchHistory(false)
    setSearchSuggestions([])

    if (!trimmed) {
      manualSearchRef.current = Date.now()
      await loadOffers(true, { searchOverride: '' })
      return
    }

    if (trimmed.length >= 2) {
      const userId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id
      if (userId) {
        try {
          await api.addSearchHistory(trimmed)
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
      await loadOffers(true, { searchOverride: trimmed })
    }
  }, [searchQuery, loadOffers])

  // Handle search history item click
  const handleHistoryClick = (query) => {
    handleSearchSubmit(query)
  }

  // Clear search history
  const handleClearHistory = async () => {
    const userId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id
    if (userId) {
      try {
        await api.clearSearchHistory()
        setSearchHistory([])
      } catch (error) {
        console.error('Error clearing search history:', error)
      }
    }
    setShowSearchHistory(false)
  }

  const handleSearchFocus = () => {
    setShowSearchHistory(true)
    setSearchFocused(true)
  }

  const handleSearchBlur = () => {
    setTimeout(() => {
      setShowSearchHistory(false)
      setSearchFocused(false)
    }, 200)
  }

  useEffect(() => {
    const trimmed = searchQuery.trim()
    if (!searchFocused || trimmed.length < 2) {
      setSearchSuggestions([])
      setSuggestionsLoading(false)
      return
    }

    let isActive = true
    const timer = setTimeout(async () => {
      setSuggestionsLoading(true)
      try {
        const suggestions = await api.getSearchSuggestions(trimmed, 5)
        if (isActive) {
          setSearchSuggestions((suggestions || []).filter(Boolean))
        }
      } catch (error) {
        if (isActive) {
          setSearchSuggestions([])
        }
      } finally {
        if (isActive) {
          setSuggestionsLoading(false)
        }
      }
    }, 250)

    return () => {
      isActive = false
      clearTimeout(timer)
    }
  }, [searchQuery, searchFocused])

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
      const data = await api.reverseGeocode(lat, lon, 'uz')
      if (!data) throw new Error('Geo lookup failed')

      const city = normalizeLocationName(
        data.address?.city || data.address?.town || data.address?.village || ''
      )
      const state = normalizeLocationName(data.address?.state || data.address?.region || '')
      const district = normalizeLocationName(
        data.address?.county || data.address?.city_district || data.address?.suburb || ''
      )
      const primaryCity = city || state || ''
      const normalizedCity = primaryCity
        ? (primaryCity.includes("O'zbekiston")
          ? primaryCity
          : `${primaryCity}, O'zbekiston`)
        : ''

      setLocation({
        city: normalizedCity,
        address: data.display_name || '',
        coordinates: { lat, lon },
        region: state,
        district, // Сохраняем область
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
    await loadOffers(true, { force: true })
  }, [loadOffers])

  // Pull-to-refresh hook
  const { containerRef, isPulling, isRefreshing, pullDistance, progress } = usePullToRefresh(handleRefresh)

  // Initial load and search with debounce
  useEffect(() => {
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
  }, [selectedCategory, searchQuery, cityForApi, location.region, location.district, minDiscount, sortBy, priceRange, loadOffers])

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
      const data = await api.reverseGeocode(lat, lon, 'uz')
      if (!data) throw new Error('Geo lookup failed')

      const city = normalizeLocationName(
        data.address?.city || data.address?.town || data.address?.village || ''
      )
      const state = normalizeLocationName(data.address?.state || data.address?.region || '')
      const district = normalizeLocationName(
        data.address?.county || data.address?.city_district || data.address?.suburb || ''
      )
      const primaryCity = city || state || ''
      const normalizedCity = primaryCity
        ? (primaryCity.includes("O'zbekiston")
          ? primaryCity
          : `${primaryCity}, O'zbekiston`)
        : ''

      setLocation({
        city: normalizedCity,
        address: data.display_name || '',
        coordinates: { lat, lon },
        region: state,
        district,
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
    const trimmedCity = normalizeLocationName(manualCity.trim())
    const trimmedAddress = manualAddress.trim()
    setLocation(prev => {
      const keepRegion = prev.city?.startsWith(trimmedCity)
      return {
        city: trimmedCity || DEFAULT_LOCATION.city,
        address: trimmedAddress,
        coordinates: trimmedAddress ? prev.coordinates : null,
        region: keepRegion ? prev.region : '',
        district: keepRegion ? prev.district : '',
      }
    })
    setShowAddressModal(false)
    setLocationError('')
  }

  // Cart functions now come from useCart() hook

  return (
    <div
      ref={containerRef}
      className="home-page"
    >
      {/* Pull-to-Refresh */}
      <PullToRefresh
        isRefreshing={isRefreshing}
        pullDistance={pullDistance}
        progress={progress}
      />

      {/* Header */}
      <header className="header">
        <div className="header-top">
          <div className="header-system-slot" aria-hidden="true" />
          <button className="header-location" onClick={openAddressModal}>
            <div className="header-location-text">
              <span className="header-location-city">
                <span className="header-location-city-name">{cityLabel}</span>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none">
                  <path d="M6 9l6 6 6-6" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </span>
            </div>
          </button>
          <div className="header-system-slot" aria-hidden="true" />
        </div>
      </header>

      {/* Subheader (Search) */}
      <div className={`home-subheader ${searchFocused ? 'search-active' : ''}`}>
        <div className="header-search">
          <div className="search-field">
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
              onFocus={handleSearchFocus}
              onBlur={handleSearchBlur}
              onKeyDown={(e) => blurOnEnter(e, handleSearchSubmit)}
            />
            {searchQuery && (
              <button
                className="search-clear"
                onClick={() => {
                  setSearchQuery('')
                  setSearchSuggestions([])
                }}
                aria-label="Qidiruvni tozalash"
              >
                x
              </button>
            )}

            {/* Search History Dropdown */}
            {showSearchDropdown && (
              <div className="search-history-dropdown">
                {showHistoryDropdown && (
                  <>
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
                  </>
                )}
                {showSuggestionsDropdown && (
                  <>
                    <div className="search-history-header">
                      <span>Tavsiyalar</span>
                      {suggestionsLoading && (
                        <span className="search-suggestions-loading">Yuklanmoqda...</span>
                      )}
                    </div>
                    {searchSuggestions.length === 0 && !suggestionsLoading ? (
                      <div className="search-suggestions-empty">Topilmadi</div>
                    ) : (
                      searchSuggestions.map((query, index) => (
                        <button
                          key={`${query}-${index}`}
                          className="search-history-item"
                          onMouseDown={() => handleSearchSubmit(query)}
                        >
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                            <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2"/>
                            <path d="M12 6v6l4 2" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                          </svg>
                          <span>{query}</span>
                        </button>
                      ))
                    )}
                  </>
                )}
              </div>
            )}
          </div>
          <button
            type="button"
            className={`search-filter-toggle ${showAdvancedFilters ? 'active' : ''}`}
            onClick={() => {
              window.Telegram?.WebApp?.HapticFeedback?.selectionChanged?.()
              setShowAdvancedFilters(prev => !prev)
            }}
            aria-label="Filtrlar"
            aria-expanded={showAdvancedFilters}
          >
            <span className="filter-icon" aria-hidden="true">
              <SlidersHorizontal size={16} strokeWidth={2} />
            </span>
            {activeFiltersCount > 0 && (
              <span className="search-filter-count">{activeFiltersCount}</span>
            )}
          </button>
        </div>
      </div>

      {showAdvancedFilters && (
        <div className="filters-section">
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
        </div>
      )}

      {/* Hero Banner Carousel */}
      <HeroBanner onCategorySelect={(category) => {
        handleCategorySelect(category, { withHaptic: false })
        setTimeout(() => {
          document.querySelector('.section-header')?.scrollIntoView({ behavior: 'smooth' })
        }, 100)
      }} />

      <div className="categories-nav-section">
        <div
          className="category-tabs"
          ref={categoriesScrollRef}
          role="tablist"
          aria-label="Kategoriyalar"
        >
          {CATEGORIES.map(cat => {
            const Icon = cat.icon
            const count = categoryCounts[cat.id]
            const showCount = Number.isFinite(count)
            return (
              <button
                key={cat.id}
                type="button"
                ref={(node) => registerCategoryTab(cat.id, node)}
                className={`category-tab ${activeCategory === cat.id ? 'is-active' : ''}`}
                role="tab"
                aria-selected={activeCategory === cat.id}
                tabIndex={activeCategory === cat.id ? 0 : -1}
                onClick={() => handleCategorySelect(cat.id)}
              >
                <span className="category-tab-label">
                  <Icon size={14} strokeWidth={2} className="category-tab-icon" aria-hidden="true" />
                  <span>{cat.name}</span>
                </span>
                {showCount && (
                  <span className="category-tab-count">
                    {categoriesLoading ? '...' : count}
                  </span>
                )}
              </button>
            )
          })}
        </div>
      </div>

      {isLocationUnset && (
        <div className="location-warning">
          Manzil aniqlanmagan. Siz hozir barcha shaharlar bo‘yicha mahsulotlarni ko‘ryapsiz.
          Manzilni kiriting yoki geolokatsiyani yoqing, shunda yaqin atrofdagi takliflar ko‘rsatiladi.
        </div>
      )}

      {selectedCategory === 'all' && !trimmedSearch && (
        <RecentlyViewed />
      )}

      {/* Section Title */}
      <div
        className="section-header"
        data-category-id={selectedCategory === 'all' ? 'all' : selectedCategory}
      >
        <h2 className="section-title">
          {selectedCategory === 'all' ? 'Barcha takliflar' : CATEGORIES.find(c => c.id === selectedCategory)?.name}
        </h2>
        <span className="offers-count">{offersCountLabel}</span>
      </div>

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
                data-category-id={normalizeCategoryId(offer.category)}
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





import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { Flame, Milk, Cookie, Snowflake, Coffee as Beverage, Croissant, Beef, Apple, Salad, Package, Search, SlidersHorizontal } from 'lucide-react'
import api from '../api/client'
import { useCart } from '../context/CartContext'
import { transliterateCity, getSavedLocation, saveLocation, DEFAULT_LOCATION, normalizeLocationName, buildLocationFromReverseGeocode } from '../utils/cityUtils'
import { getPreferredLocation } from '../utils/geolocation'
import OfferCard from '../components/OfferCard'
import OfferCardSkeleton from '../components/OfferCardSkeleton'
import HeroBanner from '../components/HeroBanner'
import BottomNav from '../components/BottomNav'
import PullToRefresh from '../components/PullToRefresh'
import { usePullToRefresh } from '../hooks/usePullToRefresh'
import { getScrollContainer, getScrollTop } from '../utils/scrollContainer'
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
const GEO_ATTEMPT_KEY = 'fudly_geo_attempt_ts'
const GEO_STATUS_KEY = 'fudly_geo_status'
const GEO_COOLDOWN_MS = 24 * 60 * 60 * 1000 // 24h to avoid repeated prompts
const GEO_ACCURACY_METERS = 200
let homePageCache = null

const normalizeCategoryId = (value) => {
  const raw = String(value || '').toLowerCase().trim()
  if (!raw) return 'other'
  if (CATEGORY_IDS.has(raw)) return raw
  const aliasEntry = Object.entries(CATEGORY_ALIASES)
    .find(([, aliases]) => aliases.includes(raw))
  if (aliasEntry) return aliasEntry[0]
  return 'other'
}

const buildLocationCacheKey = (locationValue) => {
  if (!locationValue) return ''
  const coords = locationValue.coordinates || {}
  const parts = [
    locationValue.city || '',
    locationValue.region || '',
    locationValue.district || '',
    locationValue.address || '',
    coords.lat ?? '',
    coords.lon ?? '',
  ]
  return parts.map(part => String(part).trim().toLowerCase()).join('|')
}

const applyScrollTop = (target, value) => {
  const container = target || getScrollContainer()
  if (!container) return
  const nextValue = Math.max(0, Number(value) || 0)
  if (
    container === document.body ||
    container === document.documentElement ||
    container === document.scrollingElement
  ) {
    window.scrollTo(0, nextValue)
  } else {
    container.scrollTop = nextValue
  }
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
  const [manualError, setManualError] = useState('')
  const [geoStatusLabel, setGeoStatusLabel] = useState(() => localStorage.getItem(GEO_STATUS_KEY) || '')

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
  const latestRequestRef = useRef(0)
  const queuedResetRef = useRef(null)
  const loadOffersRef = useRef(null)
  const restoringRef = useRef(false)
  const pendingScrollRef = useRef(null)
  const cacheSnapshotRef = useRef(null)
  const restoreHandledRef = useRef(false)

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
  const resolvedOffersTotal = offersTotal && offersTotal > 0 ? offersTotal : null
  const offersCountValue = resolvedOffersTotal ?? offers.length
  const offersCountLabel = hasMore && resolvedOffersTotal == null && offers.length > 0
    ? `${offersCountValue}+ ta`
    : `${offersCountValue} ta`
  const offersCountBadge = offersCountLabel.replace(/\s*ta$/, '').trim()
  const [hasNearbyFallback, setHasNearbyFallback] = useState(false)
  const derivedCategoryCounts = useMemo(() => {
    if (!offers.length) return {}
    const counts = {}
    CATEGORIES.forEach((category) => {
      counts[category.id] = 0
    })
    const totalCount = offersTotal && offersTotal > 0 ? offersTotal : offers.length
    counts.all = totalCount
    offers.forEach((offer) => {
      const categoryId = normalizeCategoryId(offer?.category)
      counts[categoryId] = (counts[categoryId] || 0) + 1
    })
    return counts
  }, [offers, offersTotal])
  const effectiveCategoryCounts = useMemo(() => {
    if (categoriesLoading || offers.length === 0) return categoryCounts
    const hasRelevantCounts = CATEGORIES.some(
      (category) => Number(categoryCounts?.[category.id]) > 0
    )
    const hasAllCount = Number(categoryCounts?.all) > 0
    if (hasRelevantCounts || hasAllCount) return categoryCounts
    return derivedCategoryCounts
  }, [categoriesLoading, categoryCounts, derivedCategoryCounts, offers.length])
  const getGeoAttemptTs = () => {
    const stored = localStorage.getItem(GEO_ATTEMPT_KEY)
    const ts = stored ? Number(stored) : 0
    return Number.isFinite(ts) ? ts : 0
  }
  const setGeoAttempt = (status = '') => {
    localStorage.setItem(GEO_ATTEMPT_KEY, String(Date.now()))
    if (status) {
      localStorage.setItem(GEO_STATUS_KEY, status)
      setGeoStatusLabel(status)
    }
  }
  const shouldSkipGeo = () => {
    const ts = getGeoAttemptTs()
    if (!ts) return false
    return Date.now() - ts < GEO_COOLDOWN_MS
  }
  const trimmedSearch = searchQuery.trim()
  const showHistoryDropdown = showSearchHistory && !trimmedSearch && searchHistory.length > 0
  const showSuggestionsDropdown = showSearchHistory && trimmedSearch.length >= 2
  const showSearchDropdown = showHistoryDropdown || showSuggestionsDropdown
  const locationCacheKey = buildLocationCacheKey(location)

  useEffect(() => {
    if (restoreHandledRef.current) return
    if (!homePageCache || homePageCache.key !== locationCacheKey) return
    const cached = homePageCache.data || {}
    const cachedOffers = Array.isArray(cached.offers) ? cached.offers : []
    if (cached.isLoading && cachedOffers.length === 0) return
    restoreHandledRef.current = true
    restoringRef.current = true
    setOffers(cachedOffers)
    setOffersTotal(cached.offersTotal ?? null)
    setHasMore(typeof cached.hasMore === 'boolean' ? cached.hasMore : true)
    const nextOffset = Number.isFinite(cached.offset) ? cached.offset : 0
    setOffset(nextOffset)
    offsetRef.current = nextOffset
    setSelectedCategory(cached.selectedCategory || 'all')
    setActiveCategory(cached.activeCategory || cached.selectedCategory || 'all')
    setSearchQuery(cached.searchQuery || '')
    setMinDiscount(cached.minDiscount ?? null)
    setPriceRange(cached.priceRange || 'all')
    setSortBy(cached.sortBy || 'default')
    setHasNearbyFallback(Boolean(cached.hasNearbyFallback))
    setCategoryCounts(cached.categoryCounts || {})
    setLoading(false)
    loadingRef.current = false
    pendingScrollRef.current = Number.isFinite(cached.scrollTop) ? cached.scrollTop : 0
  }, [locationCacheKey])

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

  useEffect(() => {
    if (pendingScrollRef.current == null) return
    const targetScroll = pendingScrollRef.current
    pendingScrollRef.current = null
    const container = getScrollContainer()
    if (!container) {
      restoringRef.current = false
      return
    }
    requestAnimationFrame(() => {
      applyScrollTop(container, targetScroll)
      requestAnimationFrame(() => {
        container.dispatchEvent(new Event('scroll'))
        restoringRef.current = false
      })
    })
  }, [offers.length])

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

  useEffect(() => {
    const handleLocationUpdate = (event) => {
      const next = event?.detail
      if (!next) return
      setLocation(prev => {
        const prevCoords = prev.coordinates || {}
        const nextCoords = next.coordinates || {}
        const same =
          (prev.city || '') === (next.city || '') &&
          (prev.address || '') === (next.address || '') &&
          (prev.region || '') === (next.region || '') &&
          (prev.district || '') === (next.district || '') &&
          prevCoords.lat === nextCoords.lat &&
          prevCoords.lon === nextCoords.lon
        if (same) return prev
        return { ...prev, ...next }
      })
    }

    window.addEventListener('fudly:location', handleLocationUpdate)
    return () => window.removeEventListener('fudly:location', handleLocationUpdate)
  }, [])

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
        if (location.region) {
          params.region = location.region
        }
        if (location.district) {
          params.district = location.district
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
  }, [cityForApi, location.region, location.district])
  // Load offers - сначала по городу, если пусто - из всех городов
  const loadOffers = useCallback(async (reset = false, options = {}) => {
    const { searchOverride, force = false } = options
    const searchValue = typeof searchOverride === 'string' ? searchOverride : searchQuery
    const trimmedSearchValue = searchValue.trim()
    if (loadingRef.current) {
      if (reset) {
        queuedResetRef.current = { searchOverride, force }
        latestRequestRef.current += 1
      }
      return
    }

    const requestId = ++latestRequestRef.current
    loadingRef.current = true
    setLoading(true)
    try {
      const currentOffset = reset ? 0 : offsetRef.current
      const params = {
        limit: OFFERS_LIMIT,
        offset: currentOffset,
      }
      if (reset) {
        params.include_meta = true
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

      if (!trimmedSearchValue && selectedCategory && selectedCategory !== 'all') {
        params.category = selectedCategory
      }

      // Добавляем поиск только если есть запрос
      if (trimmedSearchValue) {
        params.search = trimmedSearchValue
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

      let data = await api.getOffers(params, { force })
      let items = Array.isArray(data?.items)
        ? data.items
        : (Array.isArray(data?.offers) ? data.offers : (Array.isArray(data) ? data : []))
      let total = Number.isFinite(data?.total) ? data.total : null
      if (total === 0 && items.length > 0) {
        total = null
      }
      let hasMoreResult = typeof data?.has_more === 'boolean'
        ? data.has_more
        : items.length === OFFERS_LIMIT
      let nextOffset = Number.isFinite(data?.next_offset) ? data.next_offset : null

      if (
        trimmedSearchValue &&
        items.length === 0 &&
        (params.city || params.region || params.district || params.lat || params.lon)
      ) {
        const fallbackParams = { ...params }
        delete fallbackParams.city
        delete fallbackParams.region
        delete fallbackParams.district
        delete fallbackParams.lat
        delete fallbackParams.lon
        data = await api.getOffers(fallbackParams, { force: true })
        items = Array.isArray(data?.items)
          ? data.items
          : (Array.isArray(data?.offers) ? data.offers : (Array.isArray(data) ? data : []))
        total = Number.isFinite(data?.total) ? data.total : null
        if (total === 0 && items.length > 0) {
          total = null
        }
        hasMoreResult = typeof data?.has_more === 'boolean'
          ? data.has_more
          : items.length === OFFERS_LIMIT
        nextOffset = Number.isFinite(data?.next_offset) ? data.next_offset : null
      }

      if (requestId !== latestRequestRef.current) {
        return
      }

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
      if (reset) {
        // If we had coordinates but got empty list, assume we fell back to broader scope
        if (
          (location.coordinates?.lat != null && location.coordinates?.lon != null) &&
          items.length === 0
        ) {
          setHasNearbyFallback(true)
        } else {
          setHasNearbyFallback(false)
        }
      }
    } catch (error) {
      console.error('Error loading offers:', error)
    } finally {
      loadingRef.current = false
      setLoading(false)
      if (queuedResetRef.current) {
        const nextReset = queuedResetRef.current
        queuedResetRef.current = null
        loadOffersRef.current?.(true, nextReset)
      }
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

  useEffect(() => {
    loadOffersRef.current = loadOffers
  }, [loadOffers])

  useEffect(() => {
    cacheSnapshotRef.current = {
      offers,
      offersTotal,
      hasMore,
      offset: Number.isFinite(offset) ? offset : offsetRef.current,
      selectedCategory,
      activeCategory,
      searchQuery,
      minDiscount,
      priceRange,
      sortBy,
      hasNearbyFallback,
      categoryCounts,
      isLoading: loading,
    }
  }, [
    offers,
    offersTotal,
    hasMore,
    loading,
    offset,
    selectedCategory,
    activeCategory,
    searchQuery,
    minDiscount,
    priceRange,
    sortBy,
    hasNearbyFallback,
    categoryCounts,
  ])

  useEffect(() => {
    return () => {
      const snapshot = cacheSnapshotRef.current
      if (!snapshot) return
      const scrollContainer = getScrollContainer()
      const scrollTop = getScrollTop(scrollContainer)
      homePageCache = {
        key: locationCacheKey,
        data: {
          ...snapshot,
          scrollTop,
        },
      }
    }
  }, [locationCacheKey])

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
        const suggestions = await api.getSearchSuggestions(trimmed, 5, {
          city: cityForApi || undefined,
          region: location.region || undefined,
          district: location.district || undefined,
        })
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
  }, [searchQuery, searchFocused, cityForApi, location.region, location.district])

  // Автоопределение локации при первом запуске
  useEffect(() => {
    if (autoLocationAttempted.current) return
    autoLocationAttempted.current = true

    if (shouldSkipGeo()) return
    if (location.address || location.coordinates) return
    if (location.source === 'manual') return

    if (!navigator.geolocation && !window.Telegram?.WebApp?.requestLocation) return

    let isActive = true
    const resolveAutoLocation = async () => {
      setIsLocating(true)
      setGeoAttempt('start')
      try {
        const coords = await getPreferredLocation({
          preferTelegram: true,
          enableHighAccuracy: true,
          timeout: 10000,
          maximumAge: 300000,
          minAccuracy: GEO_ACCURACY_METERS,
          retryOnLowAccuracy: true,
          highAccuracyTimeout: 15000,
          highAccuracyMaximumAge: 0,
        })
        if (!isActive) return
        const ok = await reverseGeocodeAuto(coords.latitude, coords.longitude)
        setGeoAttempt(ok ? 'ok' : 'fail')
      } catch (error) {
        if (!isActive) return
        console.log('Auto-geolocation denied or failed:', error?.message || error)
        if (error?.code === error.PERMISSION_DENIED) {
          setGeoAttempt('denied')
          setShowAddressModal(true)
        } else {
          setGeoAttempt('fail')
        }
        setIsLocating(false)
      }
    }

    resolveAutoLocation()
    return () => {
      isActive = false
    }
  }, [])

  // Функция для автоматического геокодирования (при старте)
  const reverseGeocodeAuto = async (lat, lon) => {
    try {
      const data = await api.reverseGeocode(lat, lon, 'uz')
      if (!data) throw new Error('Geo lookup failed')
      setLocation(buildLocationFromReverseGeocode(data, lat, lon))
      setLocationError('')
      return true
    } catch (error) {
      console.error('Reverse geocode error', error)
      setLocationError('Manzilni aniqlab bo\'lmadi')
      return false
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
    if (restoringRef.current) return
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
      setLocation(buildLocationFromReverseGeocode(data, lat, lon))
      setLocationError('')
      setShowAddressModal(false)
      return true // Закрываем модалку после успешного определения
    } catch (error) {
      console.error('Reverse geocode error', error)
      setLocationError('Manzilni aniqlab bo\'lmadi')
      return false
    } finally {
      setIsLocating(false)
    }
  }

  const handleDetectLocation = () => {
    if (!navigator.geolocation && !window.Telegram?.WebApp?.requestLocation) {
      setLocationError('Qurilmada geolokatsiya qo\'llab-quvvatlanmaydi')
      return
    }
    setIsLocating(true)
    setGeoAttempt('start')
    setLocationError('')
    getPreferredLocation({
      preferTelegram: true,
      enableHighAccuracy: true,
      timeout: 15000,
      maximumAge: 0,
      minAccuracy: GEO_ACCURACY_METERS,
      retryOnLowAccuracy: true,
      highAccuracyTimeout: 20000,
      highAccuracyMaximumAge: 0,
    })
      .then(async ({ latitude, longitude }) => {
        const ok = await reverseGeocode(latitude, longitude)
        setGeoAttempt(ok ? 'ok' : 'fail')
      })
      .catch((error) => {
        console.error('Geolocation error', error)
        if (error?.code === error.PERMISSION_DENIED) {
          setLocationError('Geolokatsiyaga ruxsat berilmadi. Brauzer sozlamalaridan ruxsat bering.')
        } else if (error?.code === error.TIMEOUT) {
          setLocationError('Joylashuvni aniqlash vaqti tugadi. Qayta urinib ko\'ring.')
        } else {
          setLocationError('Geolokatsiyani olish imkonsiz')
        }
        setGeoAttempt(error?.code === error.PERMISSION_DENIED ? 'denied' : 'fail')
        setIsLocating(false)
      })
  }

  const openAddressModal = () => {
    setManualCity(location.city)
    setManualAddress(location.address)
    setManualError('')
    setShowAddressModal(true)
  }

  const handleSaveManualAddress = () => {
    const trimmedCity = normalizeLocationName(manualCity.trim())
    const trimmedAddress = manualAddress.trim()
    if (!trimmedCity) {
      setManualError('Shahar yoki hududni kiriting')
      return
    }
    setManualError('')
    setLocation(prev => {
      const keepRegion = prev.city?.startsWith(trimmedCity)
      return {
        city: trimmedCity || DEFAULT_LOCATION.city,
        address: trimmedAddress,
        coordinates: trimmedAddress ? prev.coordinates : null,
        region: keepRegion ? prev.region : '',
        district: keepRegion ? prev.district : '',
        source: 'manual',
      }
    })
    setShowAddressModal(false)
    setLocationError('')
  }

  const handleResetLocation = () => {
    setLocation(DEFAULT_LOCATION)
    setManualCity('')
    setManualAddress('')
    setManualError('')
    setLocationError('')
    localStorage.removeItem(GEO_ATTEMPT_KEY)
    localStorage.removeItem(GEO_STATUS_KEY)
    autoLocationAttempted.current = false
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
          <div className="header-title">
            <span className="header-location-label">Manzil</span>
            <button className="header-location" onClick={openAddressModal}>
              <span className="header-location-city-name">{cityLabel}</span>
              <svg className="header-location-caret" width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M6 9l6 6 6-6" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </div>
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
              placeholder="Restoran yoki mahsulot qidirish..."
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
        <div className="categories-header">
          <h3>Kategoriyalar</h3>
        </div>
        <div
          className="category-tabs"
          ref={categoriesScrollRef}
          role="tablist"
          aria-label="Kategoriyalar"
        >
          {CATEGORIES.map(cat => {
            const Icon = cat.icon
            const count = effectiveCategoryCounts?.[cat.id]
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
                <span className="category-tab-icon-wrap" aria-hidden="true">
                  <Icon size={20} strokeWidth={2} className="category-tab-icon" />
                </span>
                <span className="category-tab-text">{cat.name}</span>
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

      {hasNearbyFallback && (
        <div className="location-warning">
          Yaqin atrofda takliflar topilmadi. Siz kengaytirilgan hududdagi mahsulotlarni ko'ryapsiz.
          <button
            className="location-warning-btn"
            onClick={() => setShowAddressModal(true)}
          >
            Manzilni o‘zgartirish
          </button>
        </div>
      )}

      {/* Section Title */}
      <div
        className="section-header"
        data-category-id={selectedCategory === 'all' ? 'all' : selectedCategory}
      >
        <div className="section-header-left">
          <h2 className="section-title">
            {selectedCategory === 'all' ? 'Siz uchun takliflar' : CATEGORIES.find(c => c.id === selectedCategory)?.name}
          </h2>
          <span className="offers-count">{offersCountBadge}</span>
        </div>
        <button
          type="button"
          className="section-link"
          onClick={() => {
            window.Telegram?.WebApp?.HapticFeedback?.selectionChanged?.()
            handleCategorySelect('all', { withHaptic: false })
            setSearchQuery('')
            setMinDiscount(null)
            setPriceRange('all')
            setSortBy('default')
          }}
        >
          Hammasi
        </button>
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
                  imagePriority={index < 4}
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
            {geoStatusLabel && (
              <div className="address-helper">
                Oxirgi avto-aniqlash: {geoStatusLabel}
              </div>
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
              <span className="address-helper">Shahar yoki tuman nomi kerak</span>
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
              <span className="address-helper">Ixtiyoriy, agar yetkazib berish kerak bo‘lsa</span>
            </label>
            {manualError && <div className="address-error">{manualError}</div>}
            <div className="address-modal-actions">
              <button className="address-btn secondary" onClick={() => setShowAddressModal(false)}>
                Bekor qilish
              </button>
              <button className="address-btn" onClick={handleSaveManualAddress}>
                Saqlash
              </button>
              <button className="address-btn ghost" onClick={handleResetLocation}>
                Joylashuvni tozalash
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default HomePage





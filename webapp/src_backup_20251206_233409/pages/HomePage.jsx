import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/client'
import { useCart } from '../context/CartContext'
import { transliterateCity, getSavedLocation, saveLocation, DEFAULT_LOCATION } from '../utils/cityUtils'
import BottomNav from '../components/BottomNav'
import PullToRefresh from '../components/PullToRefresh'
import RecentlyViewed from '../components/RecentlyViewed'
import { usePullToRefresh } from '../hooks/usePullToRefresh'
import HomeHeader from './home/HomeHeader'
import FlashDealsSection from '../components/FlashDealsSection'
import CategoriesSection from './home/CategoriesSection'
import FiltersPanel from './home/FiltersPanel'
import PopularSection from './home/PopularSection'
import OffersSection from './home/OffersSection'
import AddressModal from './home/AddressModal'
import './HomePage.css'

const CATEGORIES = [
  { id: 'all', name: 'Hammasi', icon: '🔥', color: '#FF6B35' },
  { id: 'dairy', name: 'Sut', icon: '🥛', color: '#2196F3' },
  { id: 'snacks', name: 'Yengil taom', icon: '🍪', color: '#FF9800' },
  { id: 'drinks', name: 'Ichimlik', icon: '🧃', color: '#4CAF50' },
  { id: 'bakery', name: 'Non', icon: '🍞', color: '#8D6E63' },
  { id: 'meat', name: "Go'sht", icon: '🥩', color: '#E53935' },
  { id: 'fruits', name: 'Mevalar', icon: '🍎', color: '#F44336' },
  { id: 'vegetables', name: 'Sabzavot', icon: '🥬', color: '#43A047' },
  { id: 'other', name: 'Boshqa', icon: '📦', color: '#78909C' },
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

  // Header scroll state
  const [isScrolled, setIsScrolled] = useState(false)

  // Search history state
  const [searchHistory, setSearchHistory] = useState([])
  const [showSearchHistory, setShowSearchHistory] = useState(false)
  const searchInputRef = useRef(null)
  const lastScrollTrigger = useRef('')
  const pendingResetRef = useRef(false)
  const [loadError, setLoadError] = useState('')

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

  // Header scroll effect
  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 50)
    }
    window.addEventListener('scroll', handleScroll, { passive: true })
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

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
      if (!userId) return

      try {
        const history = await api.getSearchHistory(userId, 5)
        const normalizedHistory = (history || [])
          .map(item => (typeof item === 'string' ? item : item?.query))
          .filter(Boolean)
        setSearchHistory(normalizedHistory)
      } catch (error) {
        console.error('Error loading search history:', error)
      }
    }

    loadSearchHistory()
  }, [])

  // Save search query to history when searching
  const handleSearchSubmit = useCallback(async () => {
    const trimmedQuery = searchQuery.trim()
    if (trimmedQuery.length < 2) {
      setShowSearchHistory(false)
      return
    }

    const userId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id
    if (!userId) {
      setShowSearchHistory(false)
      return
    }

    try {
      await api.addSearchHistory(userId, trimmedQuery)
      setSearchHistory(prev => {
        const updated = [trimmedQuery, ...prev.filter(item => item !== trimmedQuery)]
        return updated.slice(0, 5)
      })
    } catch (error) {
      console.error('Error saving search history:', error)
    } finally {
      setShowSearchHistory(false)
    }
  }, [searchQuery])

  // Handle search history item click
  const handleHistoryClick = useCallback((query) => {
    setSearchQuery(query)
    setShowSearchHistory(false)
  }, [])

  // Clear search history
  const handleClearHistory = useCallback(async () => {
    const userId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id
    try {
      if (userId) {
        await api.clearSearchHistory(userId)
      }
      setSearchHistory([])
    } catch (error) {
      console.error('Error clearing search history:', error)
    } finally {
      setShowSearchHistory(false)
    }
  }, [])

  // Функция для автоматического геокодирования (при старте)
  const reverseGeocodeAuto = useCallback(async (lat, lon) => {
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
  }, [])

  // Автоопределение локации при первом запуске
  useEffect(() => {
    if (autoLocationAttempted.current) return
    autoLocationAttempted.current = true

    if (location.address || location.coordinates) return
    if (!navigator.geolocation) {
      setLocationError('Qurilmada geolokatsiya qo\'llab-quvvatlanmaydi')
      return
    }

    setIsLocating(true)
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        reverseGeocodeAuto(coords.latitude, coords.longitude)
      },
      (error) => {
        console.error('Auto geolocation error', error)
        setIsLocating(false)
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
    )
  }, [location.address, location.coordinates, reverseGeocodeAuto])

  const [showingAllCities, setShowingAllCities] = useState(false)

  // Load offers - сначала по городу, если пусто - из всех городов
  const loadOffers = useCallback(async (reset = false, forceAllCities = false) => {
    if (loading) {
      if (reset) {
        pendingResetRef.current = true
      }
      return
    }

    setLoading(true)
    setLoadError('')
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
      setLoadError('Takliflarni yuklashda xatolik. Qayta urinib ko\'ring.')
    } finally {
      setLoading(false)
      if (pendingResetRef.current) {
        pendingResetRef.current = false
        loadOffers(true, forceAllCities)
      }
    }
  }, [selectedCategory, searchQuery, offset, loading, cityForApi, showingAllCities, minDiscount, sortBy])

  // Pull-to-refresh handler
  const handleRefresh = useCallback(async () => {
    setShowingAllCities(false)
    await loadOffers(true)
  }, [loadOffers])

  const handleResetFilters = useCallback(() => {
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged?.()
    setSearchQuery('')
    setSelectedCategory('all')
    setMinDiscount(null)
    setSortBy('default')
  }, [])

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

  const isFiltered = Boolean(
    searchQuery ||
    selectedCategory !== 'all' ||
    minDiscount !== null ||
    sortBy !== 'default'
  )
  const filterSummary = [
    selectedCategory !== 'all' ? CATEGORIES.find(c => c.id === selectedCategory)?.name : null,
    searchQuery ? `"${searchQuery}"` : null,
    minDiscount ? `${minDiscount}%+` : null,
    sortBy === 'discount' ? 'Chegirma ↓' : null,
    sortBy === 'price_asc' ? 'Narx ↑' : null,
    sortBy === 'price_desc' ? 'Narx ↓' : null,
  ].filter(Boolean)
  const showEmptyHighlight = isFiltered && !loading && offers.length === 0
  const heroLocationLine = formattedAddress || 'Manzilni belgilang'
  const heroOfferSummary = loading ? 'Takliflar yuklanmoqda...' : `${offers.length} ta taklif`
  const heroDiscountSummary = minDiscount ? `${minDiscount}%+ chegirma faolda` : 'Chegirmalar ochiq'

  // Scroll to results when filters/search change and data is ready
  useEffect(() => {
    if (loading || offers.length === 0) return
    const trigger = `${selectedCategory}|${minDiscount}|${sortBy}|${searchQuery}`
    if (trigger === lastScrollTrigger.current) return
    lastScrollTrigger.current = trigger
    const sectionHeader = document.querySelector('.section-header')
    if (sectionHeader) {
      sectionHeader.scrollIntoView({ behavior: 'smooth' })
    }
  }, [selectedCategory, minDiscount, sortBy, searchQuery, loading, offers.length])

  // Autofocus search when no results to encourage refinement
  useEffect(() => {
    if (!loading && offers.length === 0 && !showAddressModal) {
      window.scrollTo({ top: 0, behavior: 'smooth' })
      if (searchInputRef.current) {
        searchInputRef.current.focus()
      }
    }
  }, [loading, offers.length, showAddressModal])

  return (
    <div className="home-page">
      {/* Pull-to-Refresh */}
      <PullToRefresh
        isRefreshing={isRefreshing}
        pullDistance={pullDistance}
        progress={progress}
      />

      <HomeHeader
        city={cityRaw}
        isScrolled={isScrolled}
        onSelectAddress={openAddressModal}
        onNavigateFavorites={() => navigate('/favorites')}
        onNavigateProfile={() => navigate('/profile')}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        onSubmitSearch={handleSearchSubmit}
        searchInputRef={searchInputRef}
        showSearchHistory={showSearchHistory}
        searchHistory={searchHistory}
        onHistoryClick={handleHistoryClick}
        onClearHistory={handleClearHistory}
        setShowSearchHistory={setShowSearchHistory}
        loading={loading}
        loadError={loadError}
        onRetryLoad={() => loadOffers(true, showingAllCities)}
      />

      {/* Flash Deals Section */}
      {selectedCategory === 'all' && !searchQuery && (
        <FlashDealsSection />
      )}

      <CategoriesSection
        categories={CATEGORIES}
        selectedCategory={selectedCategory}
        onSelectCategory={setSelectedCategory}
      />

      <FiltersPanel
        isFiltered={isFiltered}
        onResetFilters={handleResetFilters}
        minDiscount={minDiscount}
        onMinDiscountChange={setMinDiscount}
        sortBy={sortBy}
        onSortChange={setSortBy}
        filterSummary={filterSummary}
        showEmptyHighlight={showEmptyHighlight}
      />

      {selectedCategory === 'all' && !searchQuery && (
        <RecentlyViewed />
      )}

      <PopularSection
        isVisible={selectedCategory === 'all' && !searchQuery}
        offers={offers}
        loading={loading}
        onOfferClick={(offer) => navigate(`/product/${offer.id}`, { state: { offer } })}
        onScrollToList={() => {
          document.querySelector('.section-header')?.scrollIntoView({ behavior: 'smooth' })
        }}
      />

      <OffersSection
        selectedCategory={selectedCategory}
        categories={CATEGORIES}
        offers={offers}
        loading={loading}
        isFiltered={isFiltered}
        onResetFilters={handleResetFilters}
        showingAllCities={showingAllCities}
        city={cityRaw}
        getQuantity={getQuantity}
        onAddToCart={addToCart}
        onRemoveFromCart={removeFromCart}
        hasMore={hasMore}
        observerRef={observerTarget}
      />

      <BottomNav currentPage="home" cartCount={cartCount} />

      <AddressModal
        isOpen={showAddressModal}
        onClose={() => setShowAddressModal(false)}
        manualCity={manualCity}
        onCityChange={setManualCity}
        manualAddress={manualAddress}
        onAddressChange={setManualAddress}
        onSave={handleSaveManualAddress}
        onDetectLocation={handleDetectLocation}
        isLocating={isLocating}
        locationError={locationError}
      />
    </div>
  )
}

export default HomePage

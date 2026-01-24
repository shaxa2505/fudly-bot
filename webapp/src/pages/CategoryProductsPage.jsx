import { useState, useEffect, useRef } from 'react'
import { useParams, useLocation } from 'react-router-dom'
import api from '../api/client'
import { useCart } from '../context/CartContext'
import OfferCard from '../components/OfferCard'
import OfferCardSkeleton from '../components/OfferCardSkeleton'
import { blurOnEnter } from '../utils/helpers'
import { getSavedLocation, transliterateCity } from '../utils/cityUtils'
import { getScrollContainer, getScrollTop } from '../utils/scrollContainer'
import './CategoryProductsPage.css'

const PRICE_RANGE_LABELS = {
  up_20: '0-20k',
  '20_50': '20-50k',
  '50_100': '50-100k',
  '100_plus': '100k+',
}

const SORT_LABELS = {
  discount: 'Chegirma yuqori',
  price_asc: 'Arzonroq',
  price_desc: 'Qimmatroq',
}

const categoryPageCache = new Map()

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

function CategoryProductsPage() {
  const params = useParams()
  const location = useLocation()
  const { addToCart, removeFromCart, getQuantity } = useCart()

  // Get categoryId and categoryName from params or state
  const categoryId = params.categoryId || location.state?.categoryId
  const categoryName = location.state?.categoryName || categoryId

  const [offers, setOffers] = useState([])
  const [loading, setLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false)
  const [minDiscount, setMinDiscount] = useState(null)
  const [priceRange, setPriceRange] = useState('all')
  const [sortBy, setSortBy] = useState('default')
  const hasActiveFilters = Boolean(minDiscount || priceRange !== 'all' || sortBy !== 'default')
  const restoringRef = useRef(false)
  const pendingScrollRef = useRef(null)
  const cacheSnapshotRef = useRef(null)
  const restoredKeyRef = useRef(null)
  const savedLocation = getSavedLocation()
  const locationCacheKey = buildLocationCacheKey(savedLocation)
  const cacheKey = `${categoryId || 'all'}|${locationCacheKey}`

  useEffect(() => {
    if (restoredKeyRef.current === cacheKey) return
    restoredKeyRef.current = cacheKey
    const cached = categoryPageCache.get(cacheKey)
    if (!cached) return
    const cachedOffers = Array.isArray(cached.offers) ? cached.offers : []
    if (cached.isLoading && cachedOffers.length === 0) return
    restoringRef.current = true
    setOffers(cachedOffers)
    setSearchQuery(cached.searchQuery || '')
    setDebouncedSearch(cached.debouncedSearch || cached.searchQuery || '')
    setMinDiscount(cached.minDiscount ?? null)
    setPriceRange(cached.priceRange || 'all')
    setSortBy(cached.sortBy || 'default')
    setLoading(false)
    pendingScrollRef.current = Number.isFinite(cached.scrollTop) ? cached.scrollTop : 0
  }, [cacheKey])

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
        restoringRef.current = false
      })
    })
  }, [offers.length])

  const loadOffers = async (options = {}) => {
    const { searchOverride } = options
    const searchValue = typeof searchOverride === 'string' ? searchOverride : debouncedSearch
    const trimmedSearch = searchValue?.trim() || ''

    setLoading(true)
    try {
      const cityRaw = savedLocation?.city ? savedLocation.city.split(',')[0].trim() : ''
      const cityForApi = transliterateCity(cityRaw)
      const params = { limit: 50 }
      if (categoryId) {
        params.category = categoryId
      }
      if (trimmedSearch) {
        params.search = trimmedSearch
      }
      if (cityForApi) {
        params.city = cityForApi
      }
      if (savedLocation?.region) {
        params.region = savedLocation.region
      }
      if (savedLocation?.district) {
        params.district = savedLocation.district
      }
      if (savedLocation?.coordinates?.lat != null && savedLocation?.coordinates?.lon != null) {
        params.lat = savedLocation.coordinates.lat
        params.lon = savedLocation.coordinates.lon
      }
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
      if (sortBy !== 'default') {
        params.sort_by = sortBy
      }

      const data = await api.getOffers(params)
      const items = Array.isArray(data?.items)
        ? data.items
        : (Array.isArray(data?.offers) ? data.offers : (Array.isArray(data) ? data : []))
      setOffers(items)
    } catch (error) {
      console.error('Error loading offers:', error)
      alert('Xatolik yuz berdi')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    cacheSnapshotRef.current = {
      offers,
      searchQuery,
      debouncedSearch,
      minDiscount,
      priceRange,
      sortBy,
      isLoading: loading,
    }
  }, [offers, searchQuery, debouncedSearch, minDiscount, priceRange, sortBy, loading])

  useEffect(() => {
    return () => {
      const snapshot = cacheSnapshotRef.current
      if (!snapshot) return
      const scrollContainer = getScrollContainer()
      const scrollTop = getScrollTop(scrollContainer)
      categoryPageCache.set(cacheKey, {
        ...snapshot,
        scrollTop,
      })
    }
  }, [cacheKey])

  useEffect(() => {
    const trimmed = searchQuery.trim()
    const timer = setTimeout(() => {
      setDebouncedSearch(trimmed)
    }, trimmed ? 400 : 0)

    return () => clearTimeout(timer)
  }, [searchQuery])

  useEffect(() => {
    if (restoringRef.current) return
    loadOffers()
  }, [categoryId, debouncedSearch, minDiscount, priceRange, sortBy])

  const handleSearch = () => {
    setDebouncedSearch(searchQuery.trim())
  }

  const handleClearSearch = () => {
    setSearchQuery('')
    setDebouncedSearch('')
  }

  const handleSearchKeyDown = (event) => blurOnEnter(event, handleSearch)

  const clearAllFilters = () => {
    setMinDiscount(null)
    setPriceRange('all')
    setSortBy('default')
  }

  const renderFilterChips = () => {
    if (!hasActiveFilters) return null

    return (
      <div className="category-active-filters-bar">
        {minDiscount && (
          <button className="category-filter-chip" onClick={() => setMinDiscount(null)}>
            <span>{minDiscount}%+</span>
            <span aria-hidden className="category-chip-close">x</span>
          </button>
        )}
        {priceRange !== 'all' && (
          <button className="category-filter-chip" onClick={() => setPriceRange('all')}>
            <span>{PRICE_RANGE_LABELS[priceRange] || priceRange}</span>
            <span aria-hidden className="category-chip-close">x</span>
          </button>
        )}
        {sortBy !== 'default' && (
          <button className="category-filter-chip" onClick={() => setSortBy('default')}>
            <span>{SORT_LABELS[sortBy] || sortBy}</span>
            <span aria-hidden className="category-chip-close">x</span>
          </button>
        )}
        <button className="category-clear-filters-btn" onClick={clearAllFilters}>
          Tozalash
        </button>
      </div>
    )
  }

  return (
    <div className="category-products-page">
      {/* Header */}
      <header className="category-header">
        <div className="topbar-card category-header-inner">
          <h1 className="category-title">{categoryName || 'Mahsulotlar'}</h1>
          <button
            className="category-header-filter-btn"
            onClick={() => setShowAdvancedFilters(prev => !prev)}
          >
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <line x1="4" y1="6" x2="20" y2="6" stroke="#181725" strokeWidth="2" strokeLinecap="round"/>
              <line x1="4" y1="12" x2="20" y2="12" stroke="#181725" strokeWidth="2" strokeLinecap="round"/>
              <line x1="4" y1="18" x2="20" y2="18" stroke="#181725" strokeWidth="2" strokeLinecap="round"/>
              <circle cx="8" cy="6" r="2" fill="#181725"/>
              <circle cx="16" cy="12" r="2" fill="#181725"/>
              <circle cx="12" cy="18" r="2" fill="#181725"/>
            </svg>
            {hasActiveFilters && <span className="category-filter-indicator" aria-hidden />}
          </button>
        </div>
      </header>

      {/* Search */}
      <div className="category-search-section">
        <div className="category-search-box">
          <div className="category-search-field">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" className="category-search-icon">
              <circle cx="11" cy="11" r="8" stroke="#181725" strokeWidth="2"/>
              <path d="M21 21l-4.35-4.35" stroke="#181725" strokeWidth="2" strokeLinecap="round"/>
            </svg>
            <input
              type="text"
              className="category-search-input"
              placeholder="Qidirish"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={handleSearchKeyDown}
            />
            {searchQuery && (
              <button className="category-clear-search-btn" onClick={handleClearSearch}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="10" fill="#B3B3B3"/>
                  <path d="M8 8l8 8M16 8l-8 8" stroke="white" strokeWidth="2" strokeLinecap="round"/>
                </svg>
              </button>
            )}
          </div>
          <button className="category-filter-toggle" onClick={() => setShowAdvancedFilters(prev => !prev)}>
            <span className="category-filter-toggle-icon" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                <line x1="4" y1="6" x2="20" y2="6" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                <line x1="4" y1="12" x2="20" y2="12" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                <line x1="4" y1="18" x2="20" y2="18" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                <circle cx="8" cy="6" r="2" fill="currentColor"/>
                <circle cx="16" cy="12" r="2" fill="currentColor"/>
                <circle cx="12" cy="18" r="2" fill="currentColor"/>
              </svg>
            </span>
            <span className="category-filter-label">Filtr</span>
            {hasActiveFilters && <span className="category-filter-indicator" aria-hidden />}
          </button>
        </div>
      </div>

      {showAdvancedFilters && (
        <div className="category-filters-section">
          <div className="category-filters-advanced">
            <div className="category-filter-group">
              <span className="category-filter-group-label">Chegirma</span>
              <div className="category-filter-group-row">
                <button
                  className={`category-filter-pill discount ${minDiscount === 20 ? 'active' : ''}`}
                  onClick={() => setMinDiscount(minDiscount === 20 ? null : 20)}
                >
                  <span className="category-filter-pill-icon">%</span>
                  <span className="category-filter-pill-text">20%+</span>
                </button>
                <button
                  className={`category-filter-pill discount ${minDiscount === 30 ? 'active' : ''}`}
                  onClick={() => setMinDiscount(minDiscount === 30 ? null : 30)}
                >
                  <span className="category-filter-pill-icon">%</span>
                  <span className="category-filter-pill-text">30%+</span>
                </button>
                <button
                  className={`category-filter-pill discount ${minDiscount === 50 ? 'active' : ''}`}
                  onClick={() => setMinDiscount(minDiscount === 50 ? null : 50)}
                >
                  <span className="category-filter-pill-icon">%</span>
                  <span className="category-filter-pill-text">50%+</span>
                </button>
              </div>
            </div>

            <div className="category-filter-group">
              <span className="category-filter-group-label">Narx</span>
              <div className="category-filter-group-row">
                <button
                  className={`category-filter-pill ${priceRange === 'up_20' ? 'active' : ''}`}
                  onClick={() => setPriceRange(priceRange === 'up_20' ? 'all' : 'up_20')}
                >
                  <span className="category-filter-pill-icon">sum</span>
                  <span className="category-filter-pill-text">0-20k</span>
                </button>
                <button
                  className={`category-filter-pill ${priceRange === '20_50' ? 'active' : ''}`}
                  onClick={() => setPriceRange(priceRange === '20_50' ? 'all' : '20_50')}
                >
                  <span className="category-filter-pill-icon">sum</span>
                  <span className="category-filter-pill-text">20-50k</span>
                </button>
                <button
                  className={`category-filter-pill ${priceRange === '50_100' ? 'active' : ''}`}
                  onClick={() => setPriceRange(priceRange === '50_100' ? 'all' : '50_100')}
                >
                  <span className="category-filter-pill-icon">sum</span>
                  <span className="category-filter-pill-text">50-100k</span>
                </button>
                <button
                  className={`category-filter-pill ${priceRange === '100_plus' ? 'active' : ''}`}
                  onClick={() => setPriceRange(priceRange === '100_plus' ? 'all' : '100_plus')}
                >
                  <span className="category-filter-pill-icon">sum</span>
                  <span className="category-filter-pill-text">100k+</span>
                </button>
              </div>
            </div>

            <div className="category-filter-group">
              <span className="category-filter-group-label">Tartib</span>
              <select
                className="category-sort-select"
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value)}
              >
                <option value="default">Standart</option>
                <option value="discount">Chegirma yuqori</option>
                <option value="price_asc">Arzonroq</option>
                <option value="price_desc">Qimmatroq</option>
              </select>
            </div>

            {hasActiveFilters && (
              <div className="category-filters-reset">
                <button className="category-clear-filters-btn" onClick={clearAllFilters}>
                  Filtrlarni tozalash
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {renderFilterChips()}

      {/* Products Grid */}
      <div className="products-grid">
        {loading ? (
          Array.from({ length: 6 }).map((_, i) => (
            <OfferCardSkeleton key={i} />
          ))
        ) : offers.length === 0 ? (
          <div className="category-empty">
            <div className="empty-state">
              <div className="empty-state-icon" aria-hidden="true">
                <svg width="64" height="64" viewBox="0 0 24 24" fill="none">
                  <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="1.8" />
                  <path d="M21 21l-4.2-4.2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                </svg>
              </div>
              <h3 className="empty-state-title">Mahsulotlar yo'q</h3>
              <p className="empty-state-description">
                {hasActiveFilters
                  ? "Tanlangan filtrlar bo'yicha natija topilmadi"
                  : "Bu kategoriyada hozircha mahsulot yo'q"}
              </p>
              {hasActiveFilters && (
                <button className="btn-secondary" onClick={clearAllFilters}>
                  Filtrlarni tozalash
                </button>
              )}
            </div>
          </div>
        ) : (
          offers.map((offer, index) => (
            <OfferCard
              key={offer.id}
              offer={offer}
              cartQuantity={getQuantity(offer.id)}
              onAddToCart={addToCart}
              onRemoveFromCart={removeFromCart}
              imagePriority={index < 4}
            />
          ))
        )}
      </div>
    </div>
  )
}

export default CategoryProductsPage

import { useState, useEffect, useMemo, useCallback } from 'react'
import api from '../api/client'
import OfferCard from '../components/OfferCard'
import FilterPanel, { FILTER_CATEGORY_OPTIONS, FILTER_BRAND_OPTIONS } from '../components/FilterPanel'
import './CategoryProductsPage.css'

function CategoryProductsPage({ categoryId, categoryName, onNavigate, onBack }) {
  const [offers, setOffers] = useState([])
  const [loading, setLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [showFilters, setShowFilters] = useState(false)
  const [selectedFilters, setSelectedFilters] = useState({
    categories: [],
    brands: []
  })
  const [cart, setCart] = useState(() => {
    const saved = localStorage.getItem('fudly_cart')
    return saved ? new Map(Object.entries(JSON.parse(saved))) : new Map()
  })

  const categoryDictionary = useMemo(
    () => Object.fromEntries(FILTER_CATEGORY_OPTIONS.map(option => [option.id, option])),
    []
  )

  const brandDictionary = useMemo(
    () => Object.fromEntries(FILTER_BRAND_OPTIONS.map(option => [option.id, option])),
    []
  )

  useEffect(() => {
    loadOffers()
  }, [categoryId])

  const loadOffers = async () => {
    setLoading(true)
    try {
      const data = await api.getOffers({
        category: categoryId,
        search: searchQuery || undefined,
        limit: 50
      })
      setOffers(data)
    } catch (error) {
      console.error('Error loading offers:', error)
      alert('Xatolik yuz berdi')
    } finally {
      setLoading(false)
    }
  }

  const handleSearch = () => {
    loadOffers()
  }

  const handleClearSearch = () => {
    setSearchQuery('')
    setTimeout(() => loadOffers(), 0)
  }

  const handleSearchKeyPress = (e) => {
    if (e.key === 'Enter') {
      handleSearch()
    }
  }

  const addToCart = (offer) => {
    setCart(prev => {
      const next = new Map(prev)
      const current = next.get(offer.id) || 0
      next.set(offer.id, current + 1)
      localStorage.setItem('fudly_cart', JSON.stringify(Object.fromEntries(next)))
      return next
    })
  }

  const handleApplyFilters = (filters) => {
    setSelectedFilters(filters)
    setShowFilters(false)
  }

  const removeFilterValue = (type, value) => {
    setSelectedFilters(prev => ({
      ...prev,
      [type]: prev[type].filter(item => item !== value)
    }))
  }

  const clearAllFilters = () => {
    setSelectedFilters({ categories: [], brands: [] })
  }

  const filterOffers = useCallback(
    (items) => {
      const { categories, brands } = selectedFilters
      if (categories.length === 0 && brands.length === 0) {
        return items
      }

      const categoryKeywords = categories.flatMap(id => categoryDictionary[id]?.keywords || [])
      const brandKeywords = brands.flatMap(id => brandDictionary[id]?.keywords || [])

      if (categoryKeywords.length === 0 && brandKeywords.length === 0) {
        return items
      }

      return items.filter(offer => {
        const haystack = `${offer.title || ''} ${offer.description || ''} ${offer.store_name || ''}`.toLowerCase()
        const matchesCategories =
          categoryKeywords.length === 0 || categoryKeywords.some(keyword => haystack.includes(keyword))
        const matchesBrands =
          brandKeywords.length === 0 || brandKeywords.some(keyword => haystack.includes(keyword))
        return matchesCategories && matchesBrands
      })
    },
    [selectedFilters, categoryDictionary, brandDictionary]
  )

  const filteredOffers = useMemo(() => filterOffers(offers), [offers, filterOffers])

  const hasActiveFilters = selectedFilters.categories.length > 0 || selectedFilters.brands.length > 0

  const renderFilterChips = () => (
    <div className="active-filters-bar">
      {selectedFilters.categories.map(id => (
        <button
          key={`cat-${id}`}
          className="filter-chip"
          onClick={() => removeFilterValue('categories', id)}
        >
          <span>{categoryDictionary[id]?.name || id}</span>
          <span aria-hidden className="chip-close">×</span>
        </button>
      ))}
      {selectedFilters.brands.map(id => (
        <button
          key={`brand-${id}`}
          className="filter-chip"
          onClick={() => removeFilterValue('brands', id)}
        >
          <span>{brandDictionary[id]?.name || id}</span>
          <span aria-hidden className="chip-close">×</span>
        </button>
      ))}
      <button className="clear-filters-btn" onClick={clearAllFilters}>
        Tozalash
      </button>
    </div>
  )

  return (
    <div className="category-products-page">
      {/* Header */}
      <header className="category-header">
        <button className="back-btn" onClick={onBack}>
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <path d="M15 18l-6-6 6-6" stroke="#181725" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>
        <h1 className="category-title">{categoryName || 'Mahsulotlar'}</h1>
        <button className="filter-btn" onClick={() => setShowFilters(true)}>
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <line x1="4" y1="6" x2="20" y2="6" stroke="#181725" strokeWidth="2" strokeLinecap="round"/>
            <line x1="4" y1="12" x2="20" y2="12" stroke="#181725" strokeWidth="2" strokeLinecap="round"/>
            <line x1="4" y1="18" x2="20" y2="18" stroke="#181725" strokeWidth="2" strokeLinecap="round"/>
            <circle cx="8" cy="6" r="2" fill="#181725"/>
            <circle cx="16" cy="12" r="2" fill="#181725"/>
            <circle cx="12" cy="18" r="2" fill="#181725"/>
          </svg>
          {hasActiveFilters && <span className="filter-indicator" aria-hidden />}
        </button>
      </header>

      {/* Search */}
      <div className="search-section">
        <div className="search-box">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" className="search-icon-left">
            <circle cx="11" cy="11" r="8" stroke="#181725" strokeWidth="2"/>
            <path d="M21 21l-4.35-4.35" stroke="#181725" strokeWidth="2" strokeLinecap="round"/>
          </svg>
          <input
            type="text"
            className="search-input-active"
            placeholder="Qidirish"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyPress={handleSearchKeyPress}
          />
          {searchQuery && (
            <button className="clear-search-btn" onClick={handleClearSearch}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="10" fill="#B3B3B3"/>
                <path d="M8 8l8 8M16 8l-8 8" stroke="white" strokeWidth="2" strokeLinecap="round"/>
              </svg>
            </button>
          )}
          <button className="filter-icon-btn" onClick={() => setShowFilters(true)}>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <line x1="4" y1="6" x2="20" y2="6" stroke="#181725" strokeWidth="2" strokeLinecap="round"/>
              <line x1="4" y1="12" x2="20" y2="12" stroke="#181725" strokeWidth="2" strokeLinecap="round"/>
              <line x1="4" y1="18" x2="20" y2="18" stroke="#181725" strokeWidth="2" strokeLinecap="round"/>
              <circle cx="8" cy="6" r="2" fill="#181725"/>
              <circle cx="16" cy="12" r="2" fill="#181725"/>
              <circle cx="12" cy="18" r="2" fill="#181725"/>
            </svg>
            {hasActiveFilters && <span className="filter-indicator" aria-hidden />}
          </button>
        </div>
      </div>

      {hasActiveFilters && renderFilterChips()}

      {/* Products Grid */}
      <div className="products-grid">
        {loading ? (
          Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="offer-card skeleton">
              <div className="skeleton-image" />
              <div className="skeleton-text" />
              <div className="skeleton-text short" />
            </div>
          ))
        ) : filteredOffers.length === 0 ? (
          <div style={{ gridColumn: '1 / -1', textAlign: 'center', padding: '60px 20px' }}>
            <div style={{ fontSize: '64px', marginBottom: '16px' }}>📦</div>
            <h3 style={{ fontSize: '20px', color: '#181725', marginBottom: '8px' }}>Mahsulotlar yo'q</h3>
            <p style={{ color: '#7C7C7C' }}>
              {hasActiveFilters
                ? "Tanlangan filtrlar bo'yicha natija topilmadi"
                : "Bu kategoriyada hozircha mahsulot yo'q"}
            </p>
          </div>
        ) : (
          filteredOffers.map(offer => (
            <OfferCard
              key={offer.id}
              offer={offer}
              onAddToCart={() => addToCart(offer)}
              onNavigate={onNavigate}
            />
          ))
        )}
      </div>

      {/* Filter Panel */}
      {showFilters && (
        <FilterPanel
          onClose={() => setShowFilters(false)}
          onApply={handleApplyFilters}
          selectedFilters={selectedFilters}
        />
      )}
    </div>
  )
}

export default CategoryProductsPage

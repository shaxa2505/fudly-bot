import { useState, useEffect, useMemo, useCallback } from 'react'
import { ArrowLeft } from 'lucide-react'
import { useNavigate, useParams, useLocation } from 'react-router-dom'
import api from '../api/client'
import { useCart } from '../context/CartContext'
import OfferCard from '../components/OfferCard'
import FilterPanel, { FILTER_CATEGORY_OPTIONS, FILTER_BRAND_OPTIONS } from '../components/FilterPanel'
import { blurOnEnter } from '../utils/helpers'
import './CategoryProductsPage.css'

function CategoryProductsPage() {
  const navigate = useNavigate()
  const params = useParams()
  const location = useLocation()
  const { addToCart, removeFromCart, getQuantity } = useCart()

  // Get categoryId and categoryName from params or state
  const categoryId = params.categoryId || location.state?.categoryId
  const categoryName = location.state?.categoryName || categoryId

  const [offers, setOffers] = useState([])
  const [loading, setLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [showFilters, setShowFilters] = useState(false)
  const [selectedFilters, setSelectedFilters] = useState({
    categories: [],
    brands: []
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

  const handleSearchKeyDown = (event) => blurOnEnter(event, handleSearch)

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
          <span aria-hidden className="chip-close">x</span>
        </button>
      ))}
      {selectedFilters.brands.map(id => (
        <button
          key={`brand-${id}`}
          className="filter-chip"
          onClick={() => removeFilterValue('brands', id)}
        >
          <span>{brandDictionary[id]?.name || id}</span>
          <span aria-hidden className="chip-close">x</span>
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
        <button className="app-back-btn" onClick={() => navigate(-1)} aria-label="Orqaga">
          <ArrowLeft size={20} strokeWidth={2} />
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
            onKeyDown={handleSearchKeyDown}
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
          filteredOffers.map(offer => (
            <OfferCard
              key={offer.id}
              offer={offer}
              cartQuantity={getQuantity(offer.id)}
              onAddToCart={addToCart}
              onRemoveFromCart={removeFromCart}
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


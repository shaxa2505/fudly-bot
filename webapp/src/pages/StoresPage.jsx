import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/client'
import { useCart } from '../context/CartContext'
import { getSavedLocation, getLatinCity, getCyrillicCity } from '../utils/cityUtils'
import BottomNav from '../components/BottomNav'
import './StoresPage.css'

function StoresPage() {
  const navigate = useNavigate()
  const { cartCount } = useCart()

  const [stores, setStores] = useState([])
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedType, setSelectedType] = useState('all')
  const [selectedStore, setSelectedStore] = useState(null)
  const [storeOffers, setStoreOffers] = useState([])
  const [loadingOffers, setLoadingOffers] = useState(false)

  // Get current city using shared utils
  const location = getSavedLocation()
  const cityLatin = getLatinCity(location)
  const cityRaw = getCyrillicCity(location.city)

  const BUSINESS_TYPES = [
    { id: 'all', label: 'Barchasi', icon: '🏪' },
    { id: 'supermarket', label: 'Supermarket', icon: '🛒' },
    { id: 'cafe', label: 'Kafe', icon: '☕' },
    { id: 'restaurant', label: 'Restoran', icon: '🍽️' },
    { id: 'bakery', label: 'Novvoyxona', icon: '🥖' },
    { id: 'grocery', label: 'Oziq-ovqat', icon: '🥬' },
  ]

  useEffect(() => {
    loadStores()
  }, [selectedType, cityRaw])

  const loadStores = async () => {
    setLoading(true)
    try {
      let params = { city: cityRaw }
      if (selectedType !== 'all') {
        params.business_type = selectedType
      }
      let data = await api.getStores(params)

      // If no stores found with city filter, try without city
      if ((!data || data.length === 0) && cityRaw) {
        const paramsNoCity = selectedType !== 'all' ? { business_type: selectedType } : {}
        data = await api.getStores(paramsNoCity)
      }

      setStores(data || [])
    } catch (error) {
      console.error('Error loading stores:', error)
      setStores([])
    } finally {
      setLoading(false)
    }
  }

  const loadStoreOffers = async (store) => {
    setSelectedStore(store)
    setLoadingOffers(true)
    try {
      const offers = await api.getStoreOffers(store.id)
      setStoreOffers(offers)
    } catch (error) {
      console.error('Error loading store offers:', error)
      setStoreOffers([])
    } finally {
      setLoadingOffers(false)
    }
  }

  const closeStoreModal = () => {
    setSelectedStore(null)
    setStoreOffers([])
  }

  const filteredStores = stores.filter(store =>
    store.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    store.address?.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const getTypeIcon = (type) => {
    const found = BUSINESS_TYPES.find(t => t.id === type)
    return found?.icon || '🏪'
  }

  const renderStars = (rating) => {
    const stars = []
    const fullStars = Math.floor(rating)
    const hasHalf = rating % 1 >= 0.5

    for (let i = 0; i < 5; i++) {
      if (i < fullStars) {
        stars.push(<span key={i} className="star filled">★</span>)
      } else if (i === fullStars && hasHalf) {
        stars.push(<span key={i} className="star half">★</span>)
      } else {
        stars.push(<span key={i} className="star empty">★</span>)
      }
    }
    return stars
  }

  return (
    <div className="stores-page">
      {/* Header */}
      <header className="stores-header">
        <div className="header-top">
          <h1 className="page-title">Do'konlar</h1>
          <span className="city-badge">📍 {cityLatin}</span>
        </div>

        {/* Search */}
        <div className="search-box">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" className="search-icon">
            <circle cx="11" cy="11" r="8" stroke="#7C7C7C" strokeWidth="2"/>
            <path d="M21 21l-4.35-4.35" stroke="#7C7C7C" strokeWidth="2" strokeLinecap="round"/>
          </svg>
          <input
            type="text"
            className="search-input"
            placeholder="Do'kon qidirish..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          {searchQuery && (
            <button className="clear-search" onClick={() => setSearchQuery('')}>
              ✕
            </button>
          )}
        </div>
      </header>

      {/* Type Filters */}
      <div className="type-filters">
        {BUSINESS_TYPES.map(type => (
          <button
            key={type.id}
            className={`type-chip ${selectedType === type.id ? 'active' : ''}`}
            onClick={() => setSelectedType(type.id)}
          >
            <span className="type-icon">{type.icon}</span>
            <span className="type-label">{type.label}</span>
          </button>
        ))}
      </div>

      {/* Stores List */}
      <div className="stores-content">
        {loading ? (
          <div className="loading-grid">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="store-skeleton">
                <div className="skeleton-header"></div>
                <div className="skeleton-line"></div>
                <div className="skeleton-line short"></div>
              </div>
            ))}
          </div>
        ) : filteredStores.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">🏪</div>
            <h3>Do'konlar topilmadi</h3>
            <p>Bu shaharda hali do'konlar yo'q yoki qidiruv bo'yicha hech narsa topilmadi</p>
          </div>
        ) : (
          <div className="stores-grid">
            {filteredStores.map((store, idx) => (
              <div
                key={store.id}
                className="store-card"
                onClick={() => loadStoreOffers(store)}
                style={{ animationDelay: `${idx * 0.05}s` }}
              >
                <div className="store-header">
                  <span className="store-type-icon">{getTypeIcon(store.business_type)}</span>
                  {store.offers_count > 0 && (
                    <span className="offers-badge">{store.offers_count} ta taklif</span>
                  )}
                </div>

                <h3 className="store-name">{store.name}</h3>

                {store.address && (
                  <p className="store-address">📍 {store.address}</p>
                )}

                <div className="store-footer">
                  <div className="store-rating">
                    {renderStars(store.rating || 0)}
                    <span className="rating-value">{(store.rating || 0).toFixed(1)}</span>
                  </div>
                  {store.delivery_enabled && (
                    <span className="delivery-badge">🚚 Yetkazib berish</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Store Modal */}
      {selectedStore && (
        <div className="modal-overlay" onClick={closeStoreModal}>
          <div className="store-modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-store-info">
                <span className="modal-type-icon">{getTypeIcon(selectedStore.business_type)}</span>
                <div>
                  <h2 className="modal-store-name">{selectedStore.name}</h2>
                  {selectedStore.address && (
                    <p className="modal-store-address">📍 {selectedStore.address}</p>
                  )}
                </div>
              </div>
              <button className="modal-close" onClick={closeStoreModal}>✕</button>
            </div>

            <div className="modal-body">
              {loadingOffers ? (
                <div className="loading-offers">
                  <div className="spinner"></div>
                  <p>Takliflar yuklanmoqda...</p>
                </div>
              ) : storeOffers.length === 0 ? (
                <div className="no-offers">
                  <span className="no-offers-icon">📦</span>
                  <p>Hozirda takliflar yo'q</p>
                </div>
              ) : (
                <div className="modal-offers">
                  <h3 className="offers-title">Mavjud takliflar</h3>
                  <div className="offers-list">
                    {storeOffers.map(offer => (
                      <div
                        key={offer.id}
                        className="offer-item"
                        onClick={() => {
                          closeStoreModal()
                          navigate('/product', { state: { offerId: offer.id } })
                        }}
                      >
                        <img
                          src={offer.photo || 'https://via.placeholder.com/60?text=📷'}
                          alt={offer.title}
                          className="offer-image"
                        />
                        <div className="offer-info">
                          <h4 className="offer-title">{offer.title}</h4>
                          <div className="offer-prices">
                            <span className="offer-discount">{Math.round(offer.discount_price).toLocaleString()} so'm</span>
                            <span className="offer-original">{Math.round(offer.original_price).toLocaleString()}</span>
                            <span className="offer-percent">-{Math.round(offer.discount_percent)}%</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="modal-footer">
              <button
                className="view-all-btn"
                onClick={() => {
                  closeStoreModal()
                  navigate('/', { state: { storeId: selectedStore.id } })
                }}
              >
                Barcha mahsulotlarni ko'rish →
              </button>
            </div>
          </div>
        </div>
      )}

      <BottomNav currentPage="stores" cartCount={cartCount} />
    </div>
  )
}

export default StoresPage

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/client'
import { useCart } from '../context/CartContext'
import { getSavedLocation, getLatinCity, getCyrillicCity } from '../utils/cityUtils'
import BottomNav from '../components/BottomNav'
import './StoresPage.css'

const BUSINESS_TYPES = [
  { id: 'all', label: 'Barchasi', icon: '🏪' },
  { id: 'supermarket', label: 'Supermarket', icon: '🛒' },
  { id: 'cafe', label: 'Kafe', icon: '☕' },
  { id: 'restaurant', label: 'Restoran', icon: '🍽️' },
  { id: 'bakery', label: 'Novvoyxona', icon: '🥖' },
  { id: 'grocery', label: 'Oziq-ovqat', icon: '🥬' },
]

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

  const location = getSavedLocation()
  const cityLatin = getLatinCity(location)
  const cityRaw = getCyrillicCity(location.city)

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
      setStoreOffers(offers || [])
    } catch (error) {
      console.error('Error loading store offers:', error)
      setStoreOffers([])
    } finally {
      setLoadingOffers(false)
    }
  }

  const closeModal = () => {
    setSelectedStore(null)
    setStoreOffers([])
  }

  const filteredStores = stores.filter(store =>
    store.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    store.address?.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const getTypeIcon = (type) => {
    return BUSINESS_TYPES.find(t => t.id === type)?.icon || '🏪'
  }

  const handleOfferClick = (offer) => {
    closeModal()
    navigate('/product', { state: { offer } })
  }

  return (
    <div className="sp">
      {/* Header */}
      <header className="sp-header">
        <div className="sp-header-top">
          <h1 className="sp-title">Do'konlar</h1>
          <span className="sp-city">📍 {cityLatin}</span>
        </div>

        <div className="sp-search">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
            <circle cx="11" cy="11" r="8" stroke="currentColor" strokeWidth="2"/>
            <path d="M21 21l-4.35-4.35" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
          </svg>
          <input
            type="text"
            placeholder="Do'kon qidirish..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          {searchQuery && (
            <button onClick={() => setSearchQuery('')}>✕</button>
          )}
        </div>
      </header>

      {/* Type Filters */}
      <div className="sp-filters">
        {BUSINESS_TYPES.map(type => (
          <button
            key={type.id}
            className={`sp-filter ${selectedType === type.id ? 'active' : ''}`}
            onClick={() => setSelectedType(type.id)}
          >
            <span>{type.icon}</span>
            <span>{type.label}</span>
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="sp-content">
        {loading ? (
          <div className="sp-grid">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="sp-card sp-skeleton">
                <div className="sp-skel-icon"></div>
                <div className="sp-skel-line"></div>
                <div className="sp-skel-line short"></div>
              </div>
            ))}
          </div>
        ) : filteredStores.length === 0 ? (
          <div className="sp-empty">
            <span>🏪</span>
            <h3>Do'konlar topilmadi</h3>
            <p>Bu shaharda hali do'konlar yo'q</p>
          </div>
        ) : (
          <div className="sp-grid">
            {filteredStores.map((store, idx) => (
              <div
                key={store.id}
                className="sp-card"
                onClick={() => loadStoreOffers(store)}
                style={{ animationDelay: `${idx * 0.05}s` }}
              >
                {/* Store Image */}
                <div className="sp-card-image">
                  {store.photo_url ? (
                    <img
                      src={store.photo_url}
                      alt={store.name}
                      onError={(e) => {
                        e.target.style.display = 'none'
                        e.target.nextSibling.style.display = 'flex'
                      }}
                    />
                  ) : null}
                  <div className="sp-card-placeholder" style={{ display: store.photo_url ? 'none' : 'flex' }}>
                    <span>{getTypeIcon(store.business_type)}</span>
                  </div>
                  {store.offers_count > 0 && (
                    <span className="sp-card-badge">{store.offers_count} ta</span>
                  )}
                </div>

                <div className="sp-card-body">
                  <h3 className="sp-card-name">{store.name}</h3>

                  {store.address && (
                    <p className="sp-card-addr">📍 {store.address}</p>
                  )}

                  <div className="sp-card-footer">
                    {store.rating > 0 && (
                      <span className="sp-card-rating">
                        ⭐ {store.rating.toFixed(1)}
                      </span>
                    )}
                    {store.delivery_enabled && (
                      <span className="sp-card-delivery">🚚</span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Bottom Sheet Modal */}
      {selectedStore && (
        <div className="sp-overlay" onClick={closeModal}>
          <div className="sp-sheet" onClick={e => e.stopPropagation()}>
            {/* Drag Handle */}
            <div className="sp-sheet-handle"></div>

            {/* Header */}
            <div className="sp-sheet-header">
              <div className="sp-sheet-info">
                <span className="sp-sheet-icon">{getTypeIcon(selectedStore.business_type)}</span>
                <div>
                  <h2>{selectedStore.name}</h2>
                  {selectedStore.address && <p>📍 {selectedStore.address}</p>}
                  {selectedStore.rating > 0 && (
                    <span className="sp-sheet-rating">⭐ {selectedStore.rating.toFixed(1)}</span>
                  )}
                </div>
              </div>
              <button className="sp-sheet-close" onClick={closeModal}>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                  <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                </svg>
              </button>
            </div>

            {/* Body */}
            <div className="sp-sheet-body">
              {loadingOffers ? (
                <div className="sp-sheet-loading">
                  <div className="sp-spinner"></div>
                  <p>Yuklanmoqda...</p>
                </div>
              ) : storeOffers.length === 0 ? (
                <div className="sp-sheet-empty">
                  <span>📦</span>
                  <p>Hozirda takliflar yo'q</p>
                </div>
              ) : (
                <>
                  <h3 className="sp-sheet-title">
                    Mavjud takliflar
                    <span>({storeOffers.length})</span>
                  </h3>
                  <div className="sp-offers">
                    {storeOffers.map(offer => {
                      const imgUrl = offer.image_url || offer.photo || ''
                      // Calculate discount percent if not provided
                      let discountPercent = 0
                      if (offer.discount_percent) {
                        discountPercent = Math.round(offer.discount_percent)
                      } else if (offer.original_price && offer.discount_price && offer.original_price > offer.discount_price) {
                        discountPercent = Math.round((1 - offer.discount_price / offer.original_price) * 100)
                      }

                      return (
                        <div
                          key={offer.id}
                          className="sp-offer"
                          onClick={() => handleOfferClick(offer)}
                        >
                          <div className="sp-offer-img">
                            {imgUrl ? (
                              <img
                                src={imgUrl}
                                alt=""
                                onError={(e) => {
                                  e.target.style.display = 'none'
                                  e.target.nextSibling.style.display = 'flex'
                                }}
                              />
                            ) : null}
                            <div className="sp-offer-placeholder" style={{ display: imgUrl ? 'none' : 'flex' }}>
                              <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                                <rect x="3" y="3" width="18" height="18" rx="2" stroke="#ccc" strokeWidth="1.5"/>
                                <circle cx="8.5" cy="8.5" r="1.5" fill="#ccc"/>
                                <path d="M21 15l-5-5L5 21" stroke="#ccc" strokeWidth="1.5"/>
                              </svg>
                            </div>
                          </div>
                          <div className="sp-offer-info">
                            <h4>{offer.title}</h4>
                            <div className="sp-offer-price">
                              <span className="sp-offer-current">
                                {Math.round(offer.discount_price).toLocaleString()} so'm
                              </span>
                              {offer.original_price > offer.discount_price && (
                                <span className="sp-offer-old">
                                  {Math.round(offer.original_price).toLocaleString()}
                                </span>
                              )}
                              {discountPercent > 0 && (
                                <span className="sp-offer-badge">-{discountPercent}%</span>
                              )}
                            </div>
                          </div>
                          <svg className="sp-offer-arrow" width="20" height="20" viewBox="0 0 24 24" fill="none">
                            <path d="M9 18l6-6-6-6" stroke="#999" strokeWidth="2" strokeLinecap="round"/>
                          </svg>
                        </div>
                      )
                    })}
                  </div>
                </>
              )}
            </div>

            {/* Footer */}
            {storeOffers.length > 0 && (
              <div className="sp-sheet-footer">
                <button
                  className="sp-sheet-btn"
                  onClick={() => {
                    closeModal()
                    navigate('/', { state: { storeId: selectedStore.id } })
                  }}
                >
                  Barcha mahsulotlarni ko'rish
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                    <path d="M5 12h14M12 5l7 7-7 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      <BottomNav currentPage="stores" cartCount={cartCount} />
    </div>
  )
}

export default StoresPage

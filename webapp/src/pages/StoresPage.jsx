import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Store, ShoppingCart, Coffee as CafeIcon, Utensils, Croissant, Salad, Star } from 'lucide-react'
import api from '../api/client'
import { useCart } from '../context/CartContext'
import { getSavedLocation, getLatinCity, getCyrillicCity } from '../utils/cityUtils'
import { getCurrentLocation, addDistanceToStores, saveLocation, getSavedLocation as getGeoLocation } from '../utils/geolocation'
import BottomNav from '../components/BottomNav'
import StoreMap from '../components/StoreMap'
import './StoresPage.css'

const BUSINESS_TYPES = [
  { id: 'all', label: 'Barchasi', icon: Store },
  { id: 'supermarket', label: 'Supermarket', icon: ShoppingCart },
  { id: 'cafe', label: 'Kafe', icon: CafeIcon },
  { id: 'restaurant', label: 'Restoran', icon: Utensils },
  { id: 'bakery', label: 'Novvoyxona', icon: Croissant },
  { id: 'grocery', label: 'Oziq-ovqat', icon: Salad },
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
  const [storeReviews, setStoreReviews] = useState({ reviews: [], average_rating: 0, total_reviews: 0 })
  const [loadingOffers, setLoadingOffers] = useState(false)
  const [activeTab, setActiveTab] = useState('offers') // 'offers' or 'reviews'
  const [viewMode, setViewMode] = useState('list') // 'list' or 'map'
  const [userLocation, setUserLocation] = useState(null)
  const [locationLoading, setLocationLoading] = useState(false)

  const location = getSavedLocation()
  const cityLatin = getLatinCity(location)
  const cityRaw = getCyrillicCity(location.city)

  useEffect(() => {
    loadStores()
    // Try to get saved location
    const savedGeo = getGeoLocation()
    if (savedGeo) {
      setUserLocation(savedGeo)
    }
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

      setStores(Array.isArray(data) ? data : [])
    } catch (error) {
      console.error('Error loading stores:', error)
      // Show user-friendly error
      if (window.Telegram?.WebApp) {
        window.Telegram.WebApp.showAlert('Do\'konlarni yuklashda xatolik. Iltimos, qaytadan urinib ko\'ring.')
      }
      setStores([])
    } finally {
      setLoading(false)
    }
  }

  const loadStoreOffers = async (store) => {
    if (!store || !store.id) {
      console.error('Invalid store data:', store)
      return
    }
    
    setSelectedStore(store)
    setLoadingOffers(true)
    setActiveTab('offers')
    try {
      const [offers, reviews] = await Promise.all([
        api.getStoreOffers(store.id),
        api.getStoreReviews(store.id)
      ])
      setStoreOffers(Array.isArray(offers) ? offers : [])
      setStoreReviews(reviews || { reviews: [], average_rating: 0, total_reviews: 0 })
    } catch (error) {
      console.error('Error loading store data:', error)
      if (window.Telegram?.WebApp) {
        window.Telegram.WebApp.showAlert('Ma\'lumotlarni yuklashda xatolik')
      }
      setStoreOffers([])
      setStoreReviews({ reviews: [], average_rating: 0, total_reviews: 0 })
    } finally {
      setLoadingOffers(false)
    }
  }

  const closeModal = () => {
    setSelectedStore(null)
    setStoreOffers([])
    setStoreReviews({ reviews: [], average_rating: 0, total_reviews: 0 })
    setActiveTab('offers')
  }

  const requestLocation = async () => {
    setLocationLoading(true)
    try {
      const location = await getCurrentLocation()
      setUserLocation(location)
      saveLocation(location)
    } catch (error) {
      console.error('Location error:', error)
      if (window.Telegram?.WebApp) {
        window.Telegram.WebApp.showAlert('Joylashuvni aniqlab bo\'lmadi')
      }
    } finally {
      setLocationLoading(false)
    }
  }

  // Add distance to stores if user location available
  const storesWithDistance = userLocation
    ? addDistanceToStores(stores, userLocation)
    : stores

  const filteredStores = storesWithDistance.filter(store =>
    store.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    store.address?.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const getTypeIcon = (type) => {
    return BUSINESS_TYPES.find(t => t.id === type)?.icon || Store
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
            {(() => {
              const IconComponent = type.icon
              return (
                <span aria-hidden="true">
                  <IconComponent size={18} strokeWidth={2} />
                </span>
              )
            })()}
            <span>{type.label}</span>
          </button>
        ))}
      </div>

      {/* View Toggle & Location */}
      <div className="sp-view-controls">
        <div className="sp-view-toggle">
          <button
            className={`sp-view-btn ${viewMode === 'list' ? 'active' : ''}`}
            onClick={() => setViewMode('list')}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
              <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            </svg>
            Ro'yxat
          </button>
          <button
            className={`sp-view-btn ${viewMode === 'map' ? 'active' : ''}`}
            onClick={() => setViewMode('map')}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
              <path d="M1 6l8-4 6 3 8-4v16l-8 4-6-3-8 4V6z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round"/>
              <path d="M9 2v18M15 5v18" stroke="currentColor" strokeWidth="2"/>
            </svg>
            Xarita
          </button>
        </div>
        <button
          className={`sp-location-btn ${userLocation ? 'active' : ''}`}
          onClick={requestLocation}
          disabled={locationLoading}
        >
          {locationLoading ? (
            <div className="sp-location-spinner"></div>
          ) : (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="2"/>
              <path d="M12 2v4M12 18v4M2 12h4M18 12h4" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            </svg>
          )}
          {userLocation ? 'Joylashuv ✓' : 'Joylashuv'}
        </button>
      </div>

      {/* Content */}
      <div className="sp-content">
        {viewMode === 'map' ? (
          <StoreMap
            stores={filteredStores}
            userLocation={userLocation}
            onStoreSelect={loadStoreOffers}
            lang="uz"
          />
        ) : loading ? (
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
                  {api.getPhotoUrl(store.photo_url) && (
                    <img
                      src={api.getPhotoUrl(store.photo_url)}
                      alt={store.name}
                      className="sp-card-img"
                      onError={(e) => {
                        e.target.style.display = 'none'
                        e.target.parentNode.querySelector('.sp-card-placeholder').style.display = 'flex'
                      }}
                    />
                  )}
                  <div className="sp-card-placeholder" style={{ display: api.getPhotoUrl(store.photo_url) ? 'none' : 'flex' }}>
                    <svg width="40" height="40" viewBox="0 0 24 24" fill="none">
                      <path d="M3 21h18M3 7v14M21 7v14M6 7V4a1 1 0 011-1h10a1 1 0 011 1v3M12 11v6M9 14h6" stroke="#bbb" strokeWidth="1.5" strokeLinecap="round"/>
                    </svg>
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
                    {store.distance != null && (
                      <span className="sp-card-distance">
                        📏 {store.distance.toFixed(1)} km
                      </span>
                    )}
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
                {(() => {
                  const IconComponent = getTypeIcon(selectedStore.business_type)
                  return <IconComponent size={24} strokeWidth={2} className="sp-sheet-icon" aria-hidden="true" />
                })()}
                <div>
                  <h2>{selectedStore.name}</h2>
                  {selectedStore.address && (
                    <p>
                      <span>📍</span> {selectedStore.address}
                    </p>
                  )}
                  {(storeReviews.average_rating > 0 || selectedStore.rating > 0) && (
                    <span className="sp-sheet-rating">
                      <Star size={16} fill="#FFB800" color="#FFB800" strokeWidth={0} aria-hidden="true" />
                      <span>{(storeReviews.average_rating || selectedStore.rating).toFixed(1)}</span>
                      {storeReviews.total_reviews > 0 && (
                        <span className="sp-sheet-reviews-count"> ({storeReviews.total_reviews})</span>
                      )}
                    </span>
                  )}
                </div>
              </div>
              <button className="sp-sheet-close" onClick={closeModal}>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                  <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                </svg>
              </button>
            </div>

            {/* Tabs */}
            <div className="sp-sheet-tabs">
              <button
                className={`sp-sheet-tab ${activeTab === 'offers' ? 'active' : ''}`}
                onClick={() => setActiveTab('offers')}
              >
                📦 Takliflar ({storeOffers.length})
              </button>
              <button
                className={`sp-sheet-tab ${activeTab === 'reviews' ? 'active' : ''}`}
                onClick={() => setActiveTab('reviews')}
              >
                ⭐ Sharhlar ({storeReviews.total_reviews})
              </button>
            </div>

            {/* Body */}
            <div className="sp-sheet-body">
              {loadingOffers ? (
                <div className="sp-sheet-loading">
                  <div className="sp-spinner"></div>
                  <p>Yuklanmoqda...</p>
                </div>
              ) : activeTab === 'offers' ? (
                storeOffers.length === 0 ? (
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
                )
              ) : (
                // Reviews tab
                storeReviews.reviews.length === 0 ? (
                  <div className="sp-sheet-empty">
                    <Star size={48} color="#FFB800" strokeWidth={2} aria-hidden="true" />
                    <p>Hali sharhlar yo'q</p>
                  </div>
                ) : (
                  <div className="sp-reviews">
                    {storeReviews.reviews.map((review, idx) => (
                      <div key={idx} className="sp-review">
                        <div className="sp-review-header">
                          <span className="sp-review-name">{review.user_name || 'Foydalanuvchi'}</span>
                          <span className="sp-review-stars">
                            {Array.from({ length: review.rating }).map((_, i) => (
                              <Star key={i} size={14} fill="#FFB800" color="#FFB800" strokeWidth={0} aria-hidden="true" />
                            ))}
                          </span>
                        </div>
                        {review.comment && (
                          <p className="sp-review-text">{review.comment}</p>
                        )}
                        {review.created_at && (
                          <span className="sp-review-date">
                            {new Date(review.created_at).toLocaleDateString('uz-UZ')}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                )
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

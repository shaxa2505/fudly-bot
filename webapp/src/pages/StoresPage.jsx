import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Store,
  ShoppingCart,
  Coffee as CafeIcon,
  Utensils,
  Croissant,
  Salad,
  Star,
  Heart,
  ShoppingBag,
  Bell,
  Search,
} from 'lucide-react'
import api from '../api/client'
import { useCart } from '../context/CartContext'
import {
  getSavedLocation,
  getLatinCity,
  getCyrillicCity,
  saveLocation,
  buildLocationFromReverseGeocode,
} from '../utils/cityUtils'
import { getCurrentLocation, addDistanceToStores } from '../utils/geolocation'
import { blurOnEnter } from '../utils/helpers'
import { resolveOfferImageUrl, resolveStoreImageUrl } from '../utils/imageUtils'
import BottomNav from '../components/BottomNav'
import StoreMap from '../components/StoreMap'
import './StoresPage.css'

const FILTER_CHIPS = [
  { id: 'all', label: 'Hammasi' },
  { id: 'favorites', label: 'Sevimlilar' },
  { id: 'nearby', label: 'Yaqin-atrofda' },
  { id: 'supermarket', label: 'Supermarket', businessType: 'supermarket' },
  { id: 'bakery', label: 'Pishiriqlar', businessType: 'bakery' },
]

const BUSINESS_META = {
  supermarket: { label: 'Supermarket', icon: ShoppingCart },
  cafe: { label: 'Kafe', icon: CafeIcon },
  restaurant: { label: 'Restoran', icon: Utensils },
  bakery: { label: 'Nonvoyxona', icon: Croissant },
  grocery: { label: 'Oziq-ovqat', icon: Salad },
}


const getStoreStatus = (store) => {
  const offers = Number(store?.offers_count || 0)
  if (!offers) return null
  if (offers <= 2) {
    return { label: 'Tez tugayapti', tone: 'low' }
  }
  return { label: 'Ochiq', tone: 'open', showIcon: true }
}

const toPriceNumber = (value) => {
  const numeric = Number(value)
  if (!Number.isFinite(numeric) || numeric <= 0) return null
  return numeric
}

const pickStorePrice = (store, keys) => {
  for (const key of keys) {
    const value = toPriceNumber(store?.[key])
    if (value != null) return value
  }
  return null
}

const getStorePrices = (store) => {
  const current = pickStorePrice(store, [
    'min_discount_price',
    'discount_price',
    'min_price',
    'offer_price',
    'price_from',
    'price',
    'lowest_price',
    'min_offer_price',
  ])
  const original = pickStorePrice(store, [
    'min_original_price',
    'original_price',
    'price_old',
    'old_price',
    'max_price',
    'price_before_discount',
  ])
  const normalizedOriginal = original && current && original <= current ? null : original
  return { current, original: normalizedOriginal }
}

const getNextOpenLabel = (store, hoursLabel) => {
  const rawStart =
    store?.open_time ||
    store?.opening_time ||
    store?.opens_at ||
    store?.open_at ||
    ''
  let start = rawStart
  if (!start && hoursLabel) {
    const [firstPart] = String(hoursLabel).split('-')
    start = (firstPart || '').trim()
  }
  if (!start) return 'Ertaga'
  return `Ertaga ${start}`
}

function StoresPage() {
  const navigate = useNavigate()
  const { cartCount } = useCart()

  const [stores, setStores] = useState([])
  const [favoriteStores, setFavoriteStores] = useState([])
  const [favoriteIds, setFavoriteIds] = useState(() => new Set())
  const [loading, setLoading] = useState(true)
  const [favoritesLoading, setFavoritesLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)
  const [activeFilter, setActiveFilter] = useState('all')
  const [selectedStore, setSelectedStore] = useState(null)
  const [storeOffers, setStoreOffers] = useState([])
  const [storeReviews, setStoreReviews] = useState({ reviews: [], average_rating: 0, total_reviews: 0 })
  const [loadingOffers, setLoadingOffers] = useState(false)
  const [activeTab, setActiveTab] = useState('offers')
  const [viewMode, setViewMode] = useState('list')
  const [location, setLocation] = useState(getSavedLocation)
  const [userLocation, setUserLocation] = useState(() => {
    const saved = getSavedLocation()
    const coords = saved?.coordinates
    if (coords?.lat == null || coords?.lon == null) return null
    return { latitude: coords.lat, longitude: coords.lon }
  })
  const [locationLoading, setLocationLoading] = useState(false)
  const searchInputRef = useRef(null)

  const cityLatin = getLatinCity(location)
  const cityRaw = getCyrillicCity(location.city)
  const regionRaw = location.region || ''
  const districtRaw = location.district || ''
  const activeChip = FILTER_CHIPS.find((chip) => chip.id === activeFilter)
  const activeBusinessType = activeChip?.businessType || 'all'

  useEffect(() => {
    loadStores()
  }, [activeFilter, cityRaw, regionRaw, districtRaw, userLocation, viewMode])

  useEffect(() => {
    loadFavorites()
  }, [])

  useEffect(() => {
    if (userLocation) return
    if (location.coordinates?.lat == null || location.coordinates?.lon == null) return
    setUserLocation({ latitude: location.coordinates.lat, longitude: location.coordinates.lon })
  }, [location.coordinates?.lat, location.coordinates?.lon, userLocation])

  useEffect(() => {
    if (searchOpen) {
      searchInputRef.current?.focus()
    }
  }, [searchOpen])

  useEffect(() => {
    const handleLocationUpdate = (event) => {
      const next = event?.detail
      if (!next) return
      setLocation((prev) => {
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

      if (next.coordinates?.lat != null && next.coordinates?.lon != null) {
        setUserLocation({ latitude: next.coordinates.lat, longitude: next.coordinates.lon })
      }
    }

    window.addEventListener('fudly:location', handleLocationUpdate)
    return () => window.removeEventListener('fudly:location', handleLocationUpdate)
  }, [])

  const loadFavorites = async () => {
    setFavoritesLoading(true)
    try {
      const data = await api.getFavorites()
      const list = Array.isArray(data) ? data : []
      setFavoriteStores(list)
      setFavoriteIds(new Set(list.map((store) => store.id)))
    } catch (error) {
      console.error('Error loading favorites:', error)
    } finally {
      setFavoritesLoading(false)
    }
  }

  const loadStores = async () => {
    if (activeFilter === 'favorites') {
      setLoading(false)
      return
    }

    if (activeFilter === 'nearby' && !userLocation) {
      setLoading(false)
      return
    }

    setLoading(true)
    try {
      const params = {}
      if (cityRaw) params.city = cityRaw
      if (regionRaw) params.region = regionRaw
      if (districtRaw) params.district = districtRaw
      if (activeBusinessType !== 'all') {
        params.business_type = activeBusinessType
      }
      if (userLocation?.latitude != null && userLocation?.longitude != null) {
        params.lat = userLocation.latitude
        params.lon = userLocation.longitude
      }
      if (viewMode === 'map') {
        params.resolve_coords = true
      }

      const data = await api.getStores(params)
      setStores(Array.isArray(data) ? data : [])
    } catch (error) {
      console.error('Error loading stores:', error)
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
        api.getStoreReviews(store.id),
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
      const coords = await getCurrentLocation()
      setUserLocation(coords)

      let nextLocation = {
        ...location,
        coordinates: { lat: coords.latitude, lon: coords.longitude },
      }

      try {
        const data = await api.reverseGeocode(coords.latitude, coords.longitude, 'uz')
        if (data) {
          const resolved = buildLocationFromReverseGeocode(data, coords.latitude, coords.longitude)
          nextLocation = {
            ...nextLocation,
            ...resolved,
            city: resolved.city || nextLocation.city,
            region: resolved.region || nextLocation.region,
            district: resolved.district || nextLocation.district,
            address: resolved.address || nextLocation.address,
            coordinates: resolved.coordinates || nextLocation.coordinates,
          }
        }
      } catch (err) {
        console.error('Reverse geocode error:', err)
      }

      setLocation(nextLocation)
      saveLocation(nextLocation)
    } catch (error) {
      console.error('Location error:', error)
      if (window.Telegram?.WebApp) {
        window.Telegram.WebApp.showAlert('Joylashuvni aniqlab bo\'lmadi')
      }
    } finally {
      setLocationLoading(false)
    }
  }

  const handleFilterSelect = (id) => {
    setActiveFilter(id)
    if (id === 'nearby' && !userLocation) {
      requestLocation()
    }
    if (id === 'favorites' && favoriteStores.length === 0) {
      loadFavorites()
    }
  }

  const handleOfferClick = (offer) => {
    closeModal()
    navigate('/product', { state: { offer } })
  }

  const toggleFavorite = async (storeId) => {
    if (!storeId) return
    const isFavorite = favoriteIds.has(storeId)
    try {
      if (isFavorite) {
        await api.removeFavoriteStore(storeId)
      } else {
        await api.addFavoriteStore(storeId)
      }
      setFavoriteIds((prev) => {
        const next = new Set(prev)
        if (isFavorite) {
          next.delete(storeId)
        } else {
          next.add(storeId)
        }
        return next
      })
      setFavoriteStores((prev) => {
        if (isFavorite) {
          return prev.filter((store) => store.id !== storeId)
        }
        if (prev.some((store) => store.id === storeId)) {
          return prev
        }
        const addedStore = stores.find((store) => store.id === storeId)
        return addedStore ? [addedStore, ...prev] : prev
      })
    } catch (error) {
      console.error('Favorite toggle error:', error)
      if (window.Telegram?.WebApp) {
        window.Telegram.WebApp.showAlert('Sevimlilarni yangilab bo\'lmadi')
      }
    }
  }

  const baseStores = activeFilter === 'favorites' ? favoriteStores : stores
  const filteredStores = baseStores.filter((store) => {
    const query = searchQuery.toLowerCase()
    return (
      store.name?.toLowerCase().includes(query) ||
      store.address?.toLowerCase().includes(query)
    )
  })

  const visibleStores = userLocation
    ? addDistanceToStores(filteredStores, userLocation)
    : filteredStores

  const isLoading = activeFilter === 'favorites' ? favoritesLoading : loading

  return (
    <div className="sp">
      <header className="sp-header">
        <div className="sp-header-inner">
          <div className="sp-header-top">
            <div className="sp-location">
              <span className="sp-location-label">Yetkazish manzili</span>
              <button className="sp-location-btn" type="button" onClick={requestLocation}>
                <span>{cityLatin || 'Tanlanmagan'}</span>
                <svg className="sp-location-caret" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <path d="M6 9l6 6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
            </div>
            <button
              className="sp-search-btn"
              type="button"
              aria-label="Qidiruv"
              onClick={() => setSearchOpen((prev) => !prev)}
            >
              <Search size={18} strokeWidth={2} />
            </button>
          </div>
          <div className="sp-view-toggle" role="tablist" aria-label="Ko'rinish">
            <button
              className={`sp-view-pill ${viewMode === 'list' ? 'active' : ''}`}
              type="button"
              role="tab"
              aria-selected={viewMode === 'list'}
              onClick={() => setViewMode('list')}
            >
              Ro'yxat
            </button>
            <button
              className={`sp-view-pill ${viewMode === 'map' ? 'active' : ''}`}
              type="button"
              role="tab"
              aria-selected={viewMode === 'map'}
              onClick={() => setViewMode('map')}
            >
              Xarita
            </button>
          </div>
        </div>

        {searchOpen && (
          <div className="sp-searchbar">
            <div className="sp-search-input">
              <Search size={16} strokeWidth={2} />
              <input
                ref={searchInputRef}
                type="text"
                placeholder="Do'kon qidirish..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={blurOnEnter}
              />
              {searchQuery && (
                <button type="button" onClick={() => setSearchQuery('')} aria-label="Qidiruvni tozalash">
                  ?
                </button>
              )}
            </div>
          </div>
        )}

        <div className="sp-chip-row" role="tablist" aria-label="Filtrlar">
          {FILTER_CHIPS.map((chip) => (
            <button
              key={chip.id}
              type="button"
              className={`sp-chip ${activeFilter === chip.id ? 'active' : ''}`}
              onClick={() => handleFilterSelect(chip.id)}
              disabled={chip.id === 'nearby' && locationLoading}
            >
              {chip.label}
            </button>
          ))}
        </div>
        <div className="sp-divider" />
      </header>

      <main className="sp-main">
        {viewMode === 'map' ? (
          <div className="sp-map">
            <StoreMap
              stores={visibleStores}
              userLocation={userLocation}
              onStoreSelect={loadStoreOffers}
              lang="uz"
            />
          </div>
        ) : isLoading ? (
          <div className="sp-store-list">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="sp-store-card sp-skeleton">
                <div className="sp-skel-media"></div>
                <div className="sp-skel-body">
                  <div className="sp-skel-line wide"></div>
                  <div className="sp-skel-line"></div>
                  <div className="sp-skel-line short"></div>
                </div>
              </div>
            ))}
          </div>
        ) : visibleStores.length === 0 ? (
          <div className="sp-empty">
            <span>INFO</span>
            <h3>Do'konlar topilmadi</h3>
            <p>Bu hududda do'konlar mavjud emas</p>
          </div>
        ) : (
          <div className="sp-store-list">
            {visibleStores.map((store) => {
              const storePhotoUrl = resolveStoreImageUrl(store)
              const meta = BUSINESS_META[store.business_type] || {}
              const Icon = meta.icon || Store
              const status = getStoreStatus(store)
              const distanceLabel =
                store.distance != null ? `${store.distance.toFixed(1)} km` : ''
              const isFavorite = favoriteIds.has(store.id)
              const offersCount = Number(store.offers_count || 0)
              const hasOffers = offersCount > 0
              const hoursLabel =
                store.working_hours ||
                store.work_time ||
                (store.open_time && store.close_time
                  ? `${store.open_time} - ${store.close_time}`
                  : '')
              const pickupLabel = store.delivery_enabled ? 'Yetkazib berish' : 'Olib ketish'
              const showSchedule = store.delivery_enabled === false && hoursLabel
              const { current: currentPrice, original: originalPrice } = getStorePrices(store)
              const priceTone = showSchedule ? 'is-dark' : ''
              const priceLabel = currentPrice != null
                ? `${Math.round(currentPrice).toLocaleString()} so'm`
                : ''
              const originalLabel = originalPrice != null
                ? `${Math.round(originalPrice).toLocaleString()} so'm`
                : ''
              const nextOpenLabel = getNextOpenLabel(store, hoursLabel)

              return (
                <article
                  key={store.id}
                  className={`sp-store-card ${!hasOffers ? 'is-muted' : ''}`}
                  onClick={() => loadStoreOffers(store)}
                >
                  <div className="sp-store-media">
                    {storePhotoUrl ? (
                      <img
                        src={storePhotoUrl}
                        alt={store.name}
                        className="sp-store-image"
                        loading="lazy"
                        decoding="async"
                        onError={(e) => {
                          e.target.style.display = 'none'
                        }}
                      />
                    ) : (
                      <div className="sp-store-placeholder">
                        <Icon size={32} strokeWidth={1.5} />
                      </div>
                    )}

                    {status && (
                      <span className={`sp-store-status ${status.tone}`}>
                        {status.showIcon && (
                          <Store size={10} strokeWidth={2} className="sp-store-status-icon" />
                        )}
                        {status.label}
                      </span>
                    )}
                  </div>

                  <div className="sp-store-body">
                    <div className="sp-store-top">
                      <div>
                        <h3 className="sp-store-title">{store.name}</h3>
                        <div className="sp-store-meta">
                          {store.rating > 0 && (
                            <span className="sp-meta-item sp-store-rating">
                              <Star size={12} fill="#F59E0B" color="#F59E0B" strokeWidth={0} />
                              {store.rating.toFixed(1)}
                            </span>
                          )}
                          {distanceLabel && <span className="sp-meta-item">{distanceLabel}</span>}
                          {meta.label && <span className="sp-meta-item">{meta.label}</span>}
                        </div>
                      </div>

                      <button
                        type="button"
                        className={`sp-store-favorite ${isFavorite ? 'active' : ''}`}
                        onClick={(e) => {
                          e.stopPropagation()
                          toggleFavorite(store.id)
                        }}
                        aria-label="Sevimlilar"
                      >
                        <Heart size={20} strokeWidth={2} fill={isFavorite ? 'currentColor' : 'none'} />
                      </button>
                    </div>

                    <div className="sp-store-bottom">
                      <div className="sp-store-price">
                        {originalPrice != null && currentPrice != null && (
                          <span className="sp-store-price-old">{originalLabel}</span>
                        )}
                        {currentPrice != null ? (
                          <span className={`sp-store-price-current ${priceTone}`}>{priceLabel}</span>
                        ) : (
                          <span className="sp-store-price-placeholder">-- ---</span>
                        )}
                      </div>

                      {hasOffers ? (
                        showSchedule ? (
                          <div className="sp-store-schedule">
                            <span className="sp-store-schedule-label">{pickupLabel}</span>
                            <span className="sp-store-schedule-time">{hoursLabel}</span>
                          </div>
                        ) : (
                          <div className="sp-store-badge">
                            <ShoppingBag size={12} strokeWidth={2} />
                            {offersCount} ta qoldi
                          </div>
                        )
                      ) : (
                        <div className="sp-store-notify">
                          <Bell size={12} strokeWidth={2} />
                          {nextOpenLabel}
                        </div>
                      )}
                    </div>
                  </div>
                </article>
              )
            })}
          </div>
        )}
      </main>

      {selectedStore && (
        <div className="sp-overlay" onClick={closeModal}>
          <div className="sp-sheet" onClick={(e) => e.stopPropagation()}>
            <div className="sp-sheet-handle"></div>

            <div className="sp-sheet-header">
              <div className="sp-sheet-info">
                {(() => {
                  const meta = BUSINESS_META[selectedStore.business_type] || {}
                  const IconComponent = meta.icon || Store
                  return <IconComponent size={24} strokeWidth={2} className="sp-sheet-icon" aria-hidden="true" />
                })()}
                <div>
                  <h2>{selectedStore.name}</h2>
                  {selectedStore.address && (
                    <p>Manzil: {selectedStore.address}</p>
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
                  <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                </svg>
              </button>
            </div>

            <div className="sp-sheet-tabs">
              <button
                className={`sp-sheet-tab ${activeTab === 'offers' ? 'active' : ''}`}
                onClick={() => setActiveTab('offers')}
              >
                Takliflar ({storeOffers.length})
              </button>
              <button
                className={`sp-sheet-tab ${activeTab === 'reviews' ? 'active' : ''}`}
                onClick={() => setActiveTab('reviews')}
              >
                Sharhlar ({storeReviews.total_reviews})
              </button>
            </div>

            <div className="sp-sheet-body">
              {loadingOffers ? (
                <div className="sp-sheet-loading">
                  <div className="sp-spinner"></div>
                  <p>Yuklanmoqda...</p>
                </div>
              ) : activeTab === 'offers' ? (
                storeOffers.length === 0 ? (
                  <div className="sp-sheet-empty">
                    <span>INFO</span>
                    <p>Hozirda takliflar yo'q</p>
                  </div>
                ) : (
                  <>
                    <h3 className="sp-sheet-title">
                      Mavjud takliflar
                      <span>({storeOffers.length})</span>
                    </h3>
                    <div className="sp-offers">
                      {storeOffers.map((offer) => {
                        const imgUrl = resolveOfferImageUrl(offer)
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
                                  loading="lazy"
                                  decoding="async"
                                  onError={(e) => {
                                    e.target.style.display = 'none'
                                    e.target.nextSibling.style.display = 'flex'
                                  }}
                                />
                              ) : null}
                              <div className="sp-offer-placeholder" style={{ display: imgUrl ? 'none' : 'flex' }}>
                                <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                                  <rect x="3" y="3" width="18" height="18" rx="2" stroke="#ccc" strokeWidth="1.5" />
                                  <circle cx="8.5" cy="8.5" r="1.5" fill="#ccc" />
                                  <path d="M21 15l-5-5L5 21" stroke="#ccc" strokeWidth="1.5" />
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
                              <path d="M9 18l6-6-6-6" stroke="#999" strokeWidth="2" strokeLinecap="round" />
                            </svg>
                          </div>
                        )
                      })}
                    </div>
                  </>
                )
              ) : (
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
                    <path d="M5 12h14M12 5l7 7-7 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
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

import { useState, useEffect, useRef, useMemo, useDeferredValue, useCallback } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import {
  Store,
  ShoppingCart,
  Coffee as CafeIcon,
  Utensils,
  Croissant,
  Salad,
  Star,
  MapPin,
  List,
  Navigation,
  ArrowRight,
} from 'lucide-react'
import api from '../api/client'
import { useCart } from '../context/CartContext'
import {
  getSavedLocation,
  getLatinCity,
  getCyrillicCity,
  normalizeLocationName,
  saveLocation,
  buildLocationFromReverseGeocode,
} from '../utils/cityUtils'
import { getCurrentLocation, addDistanceToStores } from '../utils/geolocation'
import { getStoreAvailability, getTashkentNowMinutes } from '../utils/availability'
import { blurOnEnter } from '../utils/helpers'
import { resolveOfferImageUrl, resolveStoreImageUrl } from '../utils/imageUtils'
import { resolveUiLanguage, tByLang } from '../utils/uiLanguage'
import BottomNav from '../components/BottomNav'
import StoreMap from '../components/StoreMap'
import ScrollTopButton from '../components/ScrollTopButton'
import './StoresPage.css'

const FILTER_CHIP_DEFS = [
  { id: 'all' },
  { id: 'favorites' },
  { id: 'nearby' },
  { id: 'supermarket', businessType: 'supermarket' },
  { id: 'bakery', businessType: 'bakery' },
]

const BUSINESS_META = {
  supermarket: { labelRu: 'Супермаркет', labelUz: 'Supermarket', icon: ShoppingCart },
  cafe: { labelRu: 'Кафе', labelUz: 'Kafe', icon: CafeIcon },
  restaurant: { labelRu: 'Ресторан', labelUz: 'Restoran', icon: Utensils },
  bakery: { labelRu: 'Пекарня', labelUz: 'Nonvoyxona', icon: Croissant },
  grocery: { labelRu: 'Продукты', labelUz: 'Oziq-ovqat', icon: Salad },
}

const STORE_CATEGORY_LABELS = {
  bakery: 'BAKERY',
  supermarket: 'SUPERMARKET',
  cafe: 'CAFE',
  restaurant: 'RESTAURANT',
  grocery: 'GROCERY',
  pizzeria: 'PIZZERIA',
}

const CITY_CENTERS = {
  toshkent: { lat: 41.3111, lon: 69.2797 },
  tashkent: { lat: 41.3111, lon: 69.2797 },
  samarqand: { lat: 39.6542, lon: 66.9597 },
  samarkand: { lat: 39.6542, lon: 66.9597 },
  buxoro: { lat: 39.7670, lon: 64.4230 },
  bukhara: { lat: 39.7670, lon: 64.4230 },
  "farg'ona": { lat: 40.3894, lon: 71.7843 },
  fargona: { lat: 40.3894, lon: 71.7843 },
  fergana: { lat: 40.3894, lon: 71.7843 },
  andijon: { lat: 40.7821, lon: 72.3442 },
  andijan: { lat: 40.7821, lon: 72.3442 },
  namangan: { lat: 40.9983, lon: 71.6726 },
  navoiy: { lat: 40.1039, lon: 65.3688 },
  navoi: { lat: 40.1039, lon: 65.3688 },
  qarshi: { lat: 38.8606, lon: 65.7891 },
  karshi: { lat: 38.8606, lon: 65.7891 },
  nukus: { lat: 42.4531, lon: 59.6103 },
  urganch: { lat: 41.5506, lon: 60.6319 },
  urgench: { lat: 41.5506, lon: 60.6319 },
  jizzax: { lat: 40.1269, lon: 67.8283 },
  jizzakh: { lat: 40.1269, lon: 67.8283 },
  termiz: { lat: 37.2242, lon: 67.2783 },
  termez: { lat: 37.2242, lon: 67.2783 },
  guliston: { lat: 40.4897, lon: 68.7840 },
  gulistan: { lat: 40.4897, lon: 68.7840 },
  chirchiq: { lat: 41.4689, lon: 69.5822 },
  chirchik: { lat: 41.4689, lon: 69.5822 },
  "kattaqo'rg'on": { lat: 39.8983, lon: 66.2565 },
  kattakurgan: { lat: 39.8983, lon: 66.2565 },
  kattaqurgan: { lat: 39.8983, lon: 66.2565 },
  olmaliq: { lat: 40.8460, lon: 69.5995 },
  angren: { lat: 41.0169, lon: 70.1436 },
  bekobod: { lat: 40.2204, lon: 69.2701 },
  bekabad: { lat: 40.2204, lon: 69.2701 },
  shahrisabz: { lat: 39.0578, lon: 66.8345 },
  "marg'ilon": { lat: 40.4724, lon: 71.7246 },
  margilan: { lat: 40.4724, lon: 71.7246 },
  "qo'qon": { lat: 40.5286, lon: 70.9421 },
  qoqon: { lat: 40.5286, lon: 70.9421 },
  kokand: { lat: 40.5286, lon: 70.9421 },
  xiva: { lat: 41.3783, lon: 60.3639 },
  khiva: { lat: 41.3783, lon: 60.3639 },
}


const parseClockLabelToMinutes = (label) => {
  if (!label || typeof label !== 'string') return null
  const [hoursRaw, minutesRaw] = label.split(':')
  const hours = Number(hoursRaw)
  const minutes = Number(minutesRaw)
  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) return null
  if (hours < 0 || hours > 23 || minutes < 0 || minutes > 59) return null
  return hours * 60 + minutes
}

const formatDurationLabel = (minutes) => {
  if (!Number.isFinite(minutes) || minutes <= 0) return ''
  if (minutes < 60) return `${minutes}m`
  const hours = Math.floor(minutes / 60)
  return `${hours}h`
}

const getMinutesUntilClosing = (availability) => {
  if (!availability?.isOpen) return null
  const closeAtMinutes = parseClockLabelToMinutes(availability.endLabel)
  if (closeAtMinutes == null) return null
  const nowMinutes = getTashkentNowMinutes()
  const delta = closeAtMinutes - nowMinutes
  if (delta >= 0) return delta
  return 24 * 60 + delta
}

const getStoreCategoryLabel = (store) => {
  const explicit =
    store?.category_label ||
    store?.business_type_label ||
    store?.store_type_label ||
    store?.category
  if (explicit) return String(explicit).replace(/[_-]+/g, ' ').trim().toUpperCase()

  const businessType = String(store?.business_type || '').trim().toLowerCase()
  if (STORE_CATEGORY_LABELS[businessType]) return STORE_CATEGORY_LABELS[businessType]
  if ((store?.name || '').toLowerCase().includes('pizza')) return STORE_CATEGORY_LABELS.pizzeria
  if (businessType) return businessType.replace(/[_-]+/g, ' ').toUpperCase()
  return 'STORE'
}

const getStoreStatusLine = (store, availability, lang) => {
  const t = (ru, uz) => tByLang(lang, ru, uz)
  const offers = Number(store?.offers_count || 0)

  if (offers <= 0) {
    return { tone: 'muted', text: t('Нет доступных товаров', 'Mahsulotlar mavjud emas') }
  }

  if (!availability.isOpen) {
    return { tone: 'warning', text: t('Сейчас закрыто', 'Hozir yopiq') }
  }

  const minutesUntilClose = getMinutesUntilClosing(availability)
  if (minutesUntilClose != null && minutesUntilClose <= 60) {
    const closesInLabel = formatDurationLabel(minutesUntilClose)
    return {
      tone: 'warning',
      text: closesInLabel
        ? t(`Последний шанс: закрывается через ${closesInLabel}`, `${closesInLabel} dan keyin yopiladi`)
        : t('Последний шанс: скоро закрывается', 'Tez orada yopiladi'),
    }
  }

  return { tone: 'success', text: `${offers} ta mahsulot qoldi` }
}

const formatDistanceLabel = (distance) => {
  const value = Number(distance)
  if (!Number.isFinite(value) || value < 0) return ''
  const formatted = value >= 10 ? Math.round(value) : Number(value.toFixed(1))
  return `${formatted} km`
}

const formatRatingLabel = (rating) => {
  const value = Number(rating)
  if (!Number.isFinite(value) || value <= 0) return ''
  return value.toFixed(1)
}

function StoresPage({ user }) {
  const navigate = useNavigate()
  const routeLocation = useLocation()
  const { cartCount } = useCart()
  const lang = resolveUiLanguage(user)
  const t = (ru, uz) => tByLang(lang, ru, uz)
  const sumLabel = t('сум', "so'm")
  const locale = lang === 'ru' ? 'ru-RU' : 'uz-UZ'

  const [stores, setStores] = useState([])
  const [favoriteStores, setFavoriteStores] = useState([])
  const [favoriteIds, setFavoriteIds] = useState(() => new Set())
  const [loading, setLoading] = useState(true)
  const [favoritesLoading, setFavoritesLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchFocused, setSearchFocused] = useState(false)
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
  const openStoreRef = useRef(null)
  const filterChips = useMemo(
    () => FILTER_CHIP_DEFS.map((chip) => ({
      ...chip,
      label:
        chip.id === 'all'
          ? t('Все', 'Hammasi')
          : chip.id === 'favorites'
            ? t('Избранные', 'Sevimlilar')
            : chip.id === 'nearby'
              ? t('Рядом', 'Yaqin-atrofda')
              : chip.id === 'supermarket'
                ? t('Супермаркет', 'Supermarket')
                : t('Выпечка', 'Pishiriqlar'),
    })),
    [lang]
  )

  const deferredQuery = useDeferredValue(searchQuery)
  const normalizedQuery = deferredQuery.trim().toLowerCase()

  const cityLatin = getLatinCity(location)
  const cityRaw = getCyrillicCity(location.city)
  const regionRaw = location.region || ''
  const districtRaw = location.district || ''
  const activeChip = filterChips.find((chip) => chip.id === activeFilter)
  const activeBusinessType = activeChip?.businessType || 'all'
  const normalizedCityKey = normalizeLocationName(cityLatin).toLowerCase()
  const fallbackCenter = location?.coordinates?.lat != null && location?.coordinates?.lon != null
    ? { lat: location.coordinates.lat, lon: location.coordinates.lon }
    : CITY_CENTERS[normalizedCityKey] || null

  useEffect(() => {
    loadStores()
  }, [activeFilter, cityRaw, regionRaw, districtRaw, userLocation, viewMode, lang])

  useEffect(() => {
    loadFavorites()
  }, [])

  useEffect(() => {
    if (userLocation) return
    if (location.coordinates?.lat == null || location.coordinates?.lon == null) return
    setUserLocation({ latitude: location.coordinates.lat, longitude: location.coordinates.lon })
  }, [location.coordinates?.lat, location.coordinates?.lon, userLocation])

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
      window.Telegram?.WebApp?.showAlert?.(
        t(
          'Ошибка загрузки магазинов. Попробуйте еще раз.',
          "Do'konlarni yuklashda xatolik. Iltimos, qaytadan urinib ko'ring."
        )
      )
      setStores([])
    } finally {
      setLoading(false)
    }
  }

  const loadStoreOffers = useCallback(async (store) => {
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
      window.Telegram?.WebApp?.showAlert?.(t('Ошибка загрузки данных', "Ma'lumotlarni yuklashda xatolik"))
      setStoreOffers([])
      setStoreReviews({ reviews: [], average_rating: 0, total_reviews: 0 })
    } finally {
      setLoadingOffers(false)
    }
  }, [lang])

  useEffect(() => {
    const openStore = routeLocation.state?.openStore
    const storeId = openStore?.id || openStore?.store_id
    if (!storeId) return
    const openStoreKey = `${routeLocation.key || 'state'}:${storeId}`
    if (openStoreRef.current === openStoreKey) return
    openStoreRef.current = openStoreKey
    const matchedStore = stores.find((store) => store.id === storeId)
    loadStoreOffers(matchedStore || { ...openStore, id: storeId })
    navigate(routeLocation.pathname, { replace: true, state: {} })
  }, [routeLocation.state, routeLocation.pathname, routeLocation.key, stores, loadStoreOffers, navigate])

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
        const data = await api.reverseGeocode(coords.latitude, coords.longitude, lang)
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
      window.Telegram?.WebApp?.showAlert?.(t('Не удалось определить локацию', "Joylashuvni aniqlab bo'lmadi"))
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

  const toggleFavorite = useCallback(async (storeId) => {
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
      window.Telegram?.WebApp?.showAlert?.(t('Не удалось обновить избранное', "Sevimlilarni yangilab bo'lmadi"))
    }
  }, [favoriteIds, stores, lang])

  const baseStores = useMemo(
    () => (activeFilter === 'favorites' ? favoriteStores : stores),
    [activeFilter, favoriteStores, stores]
  )

  const filteredStores = useMemo(() => {
    if (!normalizedQuery) return baseStores
    return baseStores.filter((store) => {
      const name = (store.name || '').toLowerCase()
      const address = (store.address || '').toLowerCase()
      return name.includes(normalizedQuery) || address.includes(normalizedQuery)
    })
  }, [baseStores, normalizedQuery])

  const visibleStores = useMemo(() => {
    if (!userLocation) return filteredStores
    return addDistanceToStores(filteredStores, userLocation)
  }, [filteredStores, userLocation])

  const isLoading = activeFilter === 'favorites' ? favoritesLoading : loading

  return (
    <div className="sp">
      <header className="sp-header">
        <div className="sp-header-top">
          <div className="sp-header-title">
            <span className="sp-location-city-name">{t('Магазины', "Do'konlar")}</span>
          </div>
        </div>
      </header>

      <div className={`sp-subheader ${searchFocused ? 'search-active' : ''}`}>
        <div className="sp-header-search">
          <div className="sp-search-field">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" className="sp-search-icon">
              <circle cx="11" cy="11" r="8" stroke="currentColor" strokeWidth="2"/>
              <path d="M21 21l-4.35-4.35" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            </svg>
            <input
              ref={searchInputRef}
              type="text"
              className="sp-search-input"
              placeholder={t('Поиск магазинов...', "Do'kon qidirish...")}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onFocus={() => setSearchFocused(true)}
              onBlur={() => setSearchFocused(false)}
              onKeyDown={blurOnEnter}
            />
            {searchQuery && (
              <button
                type="button"
                className="sp-search-clear"
                onClick={() => setSearchQuery('')}
                aria-label={t('Очистить поиск', 'Qidiruvni tozalash')}
              >
                x
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="sp-chip-row" role="tablist" aria-label={t('Фильтры', 'Filtrlar')}>
        {filterChips.map((chip) => (
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

      <div className="sp-section-header">
        <h3 className="sp-section-title">{t('Магазины', "Do'konlar")}</h3>
        <button
          type="button"
          className="sp-section-action"
          onClick={() => setViewMode(viewMode === 'list' ? 'map' : 'list')}
          aria-label={viewMode === 'list' ? t('Показать карту', "Xaritani ko'rish") : t('Показать список', "Ro'yxatni ko'rish")}
        >
          <span>{viewMode === 'list' ? t('Карта', 'Xarita') : t('Список', "Ro'yxat")}</span>
          {viewMode === 'list' ? (
            <MapPin size={16} strokeWidth={2} />
          ) : (
            <List size={16} strokeWidth={2} />
          )}
        </button>
      </div>
      <div className="sp-divider" />

      <main className="sp-main">
        {viewMode === 'map' ? (
          <div className="sp-map">
            <StoreMap
              stores={visibleStores}
              userLocation={userLocation}
              fallbackCenter={fallbackCenter}
              cityLabel={cityLatin}
              onRequestLocation={requestLocation}
              locationLoading={locationLoading}
              onStoreSelect={loadStoreOffers}
              lang={lang}
            />
          </div>
        ) : isLoading ? (
          <div className="sp-store-list">
            {[...Array(4)].map((_, i) => (
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
            <h3>{t('Магазины не найдены', "Do'konlar topilmadi")}</h3>
            <p>{t('В этом районе пока нет магазинов', "Bu hududda do'konlar mavjud emas")}</p>
          </div>
        ) : (
          <div className="sp-store-list">
            {visibleStores.map((store) => {
              const storePhotoUrl = resolveStoreImageUrl(store)
              const Icon = (BUSINESS_META[store.business_type] || {}).icon || Store
              const storeAvailability = getStoreAvailability(store)
              const distanceLabel = formatDistanceLabel(store.distance)
              const ratingLabel = formatRatingLabel(store.rating)
              const categoryLabel = getStoreCategoryLabel(store)
              const statusLine = getStoreStatusLine(store, storeAvailability, lang)

              return (
                <article
                  key={store.id}
                  className={`sp-store-card ${statusLine.tone === 'muted' ? 'is-muted' : ''}`}
                  onClick={() => loadStoreOffers(store)}
                >
                  <div className="sp-store-media">
                    <div className="sp-store-placeholder" aria-hidden="true">
                      <Icon size={32} strokeWidth={1.5} />
                    </div>
                    {storePhotoUrl && (
                      <>
                        <img
                          src={storePhotoUrl}
                          alt={store.name}
                          className="sp-store-image"
                          loading="lazy"
                          decoding="async"
                          onLoad={(event) => {
                            event.currentTarget.parentElement?.classList.add('is-loaded')
                          }}
                          onError={(event) => {
                            const parent = event.currentTarget.parentElement
                            event.currentTarget.classList.add('is-error')
                            parent?.classList.add('is-error')
                            parent?.classList.remove('is-loaded')
                          }}
                        />
                        <div className="sp-store-image-skeleton" aria-hidden="true" />
                      </>
                    )}
                    <div className="sp-store-badges">
                      {distanceLabel && (
                        <span className="sp-store-pill">
                          <Navigation size={12} strokeWidth={2.2} />
                          {distanceLabel}
                        </span>
                      )}
                      {ratingLabel && (
                        <span className="sp-store-pill">
                          <Star size={11} fill="#F6B212" color="#F6B212" strokeWidth={0} />
                          {ratingLabel}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="sp-store-body">
                    <div className="sp-store-top">
                      <div className="sp-store-main">
                        <h3 className="sp-store-title">{store.name}</h3>
                        <p className="sp-store-category">{categoryLabel}</p>
                      </div>

                      <button
                        type="button"
                        className="sp-store-open"
                        onClick={(e) => {
                          e.stopPropagation()
                          loadStoreOffers(store)
                        }}
                        aria-label={t('Открыть магазин', "Do'konni ochish")}
                      >
                        <ArrowRight size={18} strokeWidth={2.1} />
                      </button>
                    </div>

                    <p className={`sp-store-status-line is-${statusLine.tone}`}>
                      <span className="sp-store-status-dot" aria-hidden="true" />
                      {statusLine.text}
                    </p>
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
                    <p>{t('Адрес', 'Manzil')}: {selectedStore.address}</p>
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
                {t('Предложения', 'Takliflar')} ({storeOffers.length})
              </button>
              <button
                className={`sp-sheet-tab ${activeTab === 'reviews' ? 'active' : ''}`}
                onClick={() => setActiveTab('reviews')}
              >
                {t('Отзывы', 'Sharhlar')} ({storeReviews.total_reviews})
              </button>
            </div>

            <div className="sp-sheet-body">
              {loadingOffers ? (
                <div className="sp-sheet-loading">
                  <div className="sp-spinner"></div>
                  <p>{t('Загрузка...', 'Yuklanmoqda...')}</p>
                </div>
              ) : activeTab === 'offers' ? (
                storeOffers.length === 0 ? (
                  <div className="sp-sheet-empty">
                    <span>INFO</span>
                    <p>{t('Сейчас предложений нет', "Hozirda takliflar yo'q")}</p>
                  </div>
                ) : (
                  <>
                    <h3 className="sp-sheet-title">
                      {t('Доступные предложения', 'Mavjud takliflar')}
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
                                  {Math.round(offer.discount_price).toLocaleString(locale)} {sumLabel}
                                </span>
                                {offer.original_price > offer.discount_price && (
                                  <span className="sp-offer-old">
                                    {Math.round(offer.original_price).toLocaleString(locale)}
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
                    <p>{t('Пока нет отзывов', "Hali sharhlar yo'q")}</p>
                  </div>
                ) : (
                  <div className="sp-reviews">
                    {storeReviews.reviews.map((review, idx) => (
                      <div key={idx} className="sp-review">
                        <div className="sp-review-header">
                          <span className="sp-review-name">{review.user_name || t('Пользователь', 'Foydalanuvchi')}</span>
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
                            {new Date(review.created_at).toLocaleDateString(locale)}
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
                  {t('Посмотреть все товары', "Barcha mahsulotlarni ko'rish")}
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                    <path d="M5 12h14M12 5l7 7-7 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      <ScrollTopButton />
      <BottomNav currentPage="stores" cartCount={cartCount} lang={lang} />
    </div>
  )
}

export default StoresPage

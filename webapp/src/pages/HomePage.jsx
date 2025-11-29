import { useState, useEffect, useRef, useCallback } from 'react'
import api from '../api/client'
import OfferCard from '../components/OfferCard'
import BottomNav from '../components/BottomNav'
import fudlyLogo from '../assets/fudly-logo.svg'
import './HomePage.css'

const CATEGORIES = [
  { id: 'all', name: 'Hammasi', icon: '🔥' },
  { id: 'dairy', name: 'Sut', icon: '🥛' },
  { id: 'snacks', name: 'Gazaklar', icon: '🍪' },
  { id: 'drinks', name: 'Ichimlik', icon: '🧃' },
  { id: 'bakery', name: 'Non', icon: '🍞' },
  { id: 'meat', name: "Go'sht", icon: '🥩' },
  { id: 'fruits', name: 'Mevalar', icon: '🍎' },
  { id: 'vegetables', name: 'Sabzavot', icon: '🥬' },
  { id: 'other', name: 'Boshqa', icon: '📦' },
]

// Транслитерация городов: латиница -> кириллица (для API)
const CITY_TO_CYRILLIC = {
  'toshkent': 'Ташкент',
  'tashkent': 'Ташкент',
  'samarqand': 'Самарканд',
  'samarkand': 'Самарканд',
  'buxoro': 'Бухара',
  'bukhara': 'Бухара',
  "farg'ona": 'Фергана',
  'fergana': 'Фергана',
  'andijon': 'Андижан',
  'andijan': 'Андижан',
  'namangan': 'Наманган',
  'navoiy': 'Навои',
  'navoi': 'Навои',
  'qarshi': 'Карши',
  'karshi': 'Карши',
  'nukus': 'Нукус',
  'urganch': 'Ургенч',
  'urgench': 'Ургенч',
  'jizzax': 'Джизак',
  'jizzakh': 'Джизак',
  'termiz': 'Термез',
  'termez': 'Термез',
  'guliston': 'Гулистан',
  'gulistan': 'Гулистан',
  'chirchiq': 'Чирчик',
  'chirchik': 'Чирчик',
  "kattaqo'rg'on": 'Каттакурган',
  'kattakurgan': 'Каттакурган',
  'kattaqurgan': 'Каттакурган',
  'olmaliq': 'Алмалык',
  'angren': 'Ангрен',
  'bekobod': 'Бекабад',
  'shahrisabz': 'Шахрисабз',
  "marg'ilon": 'Маргилан',
  "qo'qon": 'Коканд',
  'xiva': 'Хива',
  'khiva': 'Хива',
}

// Функция для транслитерации города в кириллицу
const transliterateCity = (city) => {
  if (!city) return city
  const cityLower = city.toLowerCase().trim()
  return CITY_TO_CYRILLIC[cityLower] || city
}

const DEFAULT_LOCATION = {
  city: "Toshkent, O'zbekiston",
  address: '',
  coordinates: null,
}

function HomePage({ onNavigate }) {
  const [offers, setOffers] = useState([])
  const [loading, setLoading] = useState(false)
  const [selectedCategory, setSelectedCategory] = useState('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [location, setLocation] = useState(() => {
    try {
      const saved = localStorage.getItem('fudly_location')
      return saved ? JSON.parse(saved) : DEFAULT_LOCATION
    } catch {
      return DEFAULT_LOCATION
    }
  })
  const [isLocating, setIsLocating] = useState(false)
  const [locationError, setLocationError] = useState('')
  const [showAddressModal, setShowAddressModal] = useState(false)
  const [manualCity, setManualCity] = useState(location.city)
  const [manualAddress, setManualAddress] = useState(location.address)
  // Cart хранит: { offerId: { offer, quantity } }
  const [cart, setCart] = useState(() => {
    try {
      const saved = localStorage.getItem('fudly_cart_v2')
      return saved ? JSON.parse(saved) : {}
    } catch {
      return {}
    }
  })
  const [hasMore, setHasMore] = useState(true)
  const [offset, setOffset] = useState(0)
  const [bannerIndex, setBannerIndex] = useState(0)
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
  const autoLocationAttempted = useRef(false)

  // Извлекаем название города для API (без страны) и транслитерируем в кириллицу
  const cityRaw = location.city
    ? location.city.split(',')[0].trim()
    : 'Toshkent'
  const cityForApi = transliterateCity(cityRaw)

  useEffect(() => {
    localStorage.setItem('fudly_location', JSON.stringify(location))
  }, [location])

  // Автоопределение локации при первом запуске
  useEffect(() => {
    if (autoLocationAttempted.current) return
    autoLocationAttempted.current = true

    // Если уже есть сохранённый адрес - не запрашиваем
    if (location.address || location.coordinates) return

    // Пытаемся определить автоматически
    if (navigator.geolocation) {
      setIsLocating(true)
      navigator.geolocation.getCurrentPosition(
        (position) => {
          const { latitude, longitude } = position.coords
          reverseGeocodeAuto(latitude, longitude)
        },
        (error) => {
          console.log('Auto-geolocation denied or failed:', error.message)
          setIsLocating(false)
          // Если отклонил - показываем модалку ручного ввода
          if (error.code === error.PERMISSION_DENIED) {
            setShowAddressModal(true)
          }
        },
        { enableHighAccuracy: true, timeout: 10000, maximumAge: 300000 }
      )
    }
  }, [])

  // Функция для автоматического геокодирования (при старте)
  const reverseGeocodeAuto = async (lat, lon) => {
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
  }

  const [showingAllCities, setShowingAllCities] = useState(false)

  // Load offers - сначала по городу, если пусто - из всех городов
  const loadOffers = useCallback(async (reset = false, forceAllCities = false) => {
    if (loading) return

    setLoading(true)
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
    } finally {
      setLoading(false)
    }
  }, [selectedCategory, searchQuery, offset, loading, cityForApi, showingAllCities])

  // Initial load and search with debounce
  useEffect(() => {
    setShowingAllCities(false) // Сбрасываем при смене города/фильтров
    const timer = setTimeout(() => {
      loadOffers(true)
    }, searchQuery ? 500 : 0)

    return () => clearTimeout(timer)
  }, [selectedCategory, searchQuery, cityForApi])

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

  // Save cart to localStorage
  useEffect(() => {
    localStorage.setItem('fudly_cart_v2', JSON.stringify(cart))
  }, [cart])

  // Banner auto-slide
  useEffect(() => {
    const timer = setInterval(() => {
      setBannerIndex(prev => (prev + 1) % 3)
    }, 4000)
    return () => clearInterval(timer)
  }, [])

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

  const addToCart = (offer) => {
    setCart(prev => {
      const key = String(offer.id)
      const existing = prev[key]
      return {
        ...prev,
        [key]: {
          offer: {
            id: offer.id,
            title: offer.title,
            photo: offer.photo,
            discount_price: offer.discount_price,
            original_price: offer.original_price,
            store_name: offer.store_name,
          },
          quantity: (existing?.quantity || 0) + 1
        }
      }
    })
  }

  const removeFromCart = (offer) => {
    setCart(prev => {
      const key = String(offer.id)
      const existing = prev[key]
      if (!existing || existing.quantity <= 1) {
        const { [key]: _, ...rest } = prev
        return rest
      }
      return {
        ...prev,
        [key]: { ...existing, quantity: existing.quantity - 1 }
      }
    })
  }

  const getCartQuantity = (offerId) => {
    return cart[String(offerId)]?.quantity || 0
  }

  const cartCount = Object.values(cart).reduce((sum, item) => sum + item.quantity, 0)

  return (
    <div className="home-page">
      {/* Header */}
      <header className="header">
        <div className="header-content">
          <div className="brand-row">
            <div className="brand-mark" aria-label="Fudly">
              <img src={fudlyLogo} alt="Fudly" className="brand-logo" />
            </div>
            <button className="brand-location" onClick={openAddressModal}>
              <span className="brand-location-label">📍</span>
              <span className="brand-location-city">{cityRaw}</span>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" className="brand-location-arrow">
                <path d="M6 9l6 6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </div>
          <div className="search-container">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" className="search-icon">
              <circle cx="11" cy="11" r="8" stroke="#7C7C7C" strokeWidth="2"/>
              <path d="M21 21l-4.35-4.35" stroke="#7C7C7C" strokeWidth="2" strokeLinecap="round"/>
            </svg>
            <input
              type="text"
              className="search-input"
              placeholder="Mahsulot qidirish..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            {searchQuery && (
              <button className="search-clear" onClick={() => setSearchQuery('')}>
                ✕
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Banner Slider */}
      <div className="banner-slider">
        <div className="banner-track" style={{ transform: `translateX(-${bannerIndex * 100}%)` }}>
          <div className="banner-slide gradient-green">
            <div className="banner-content">
              <div className="banner-left">
                <div className="banner-badge">🔥 Chegirma</div>
                <h2 className="banner-title">Yangi Takliflar</h2>
                <p className="banner-subtitle">40% gacha</p>
                <button className="banner-btn">Ko'rish</button>
              </div>
              <div className="banner-emoji">🥬🥕🍅</div>
            </div>
          </div>
          <div className="banner-slide gradient-orange">
            <div className="banner-content">
              <div className="banner-left">
                <div className="banner-badge">⚡ Tezkor</div>
                <h2 className="banner-title">Kunlik Mahsulot</h2>
                <p className="banner-subtitle">Yaqin do'kondan</p>
                <button className="banner-btn">Buyurtma</button>
              </div>
              <div className="banner-emoji">🍞🥛🧀</div>
            </div>
          </div>
          <div className="banner-slide gradient-purple">
            <div className="banner-content">
              <div className="banner-left">
                <div className="banner-badge">🎁 Bonus</div>
                <h2 className="banner-title">Meva & Sabzavot</h2>
                <p className="banner-subtitle">Har kuni yangi</p>
                <button className="banner-btn">Tanlash</button>
              </div>
              <div className="banner-emoji">🍎🍊🍋</div>
            </div>
          </div>
        </div>
        <div className="banner-dots">
          {[0, 1, 2].map(i => (
            <button
              key={i}
              className={`dot ${bannerIndex === i ? 'active' : ''}`}
              onClick={() => setBannerIndex(i)}
              aria-label={`Slide ${i + 1}`}
            />
          ))}
        </div>
      </div>

      {/* Categories */}
      <div className="categories-section">
        <div className="categories-scroll">
          {CATEGORIES.map(cat => (
            <button
              key={cat.id}
              className={`category-chip ${selectedCategory === cat.id ? 'active' : ''}`}
              onClick={() => setSelectedCategory(cat.id)}
            >
              <span className="category-icon">{cat.icon}</span>
              <span className="category-name">{cat.name}</span>
            </button>
          ))}
        </div>
        <div className="categories-fade" />
      </div>

      {/* Section Title */}
      <div className="section-header">
        <h2 className="section-title">
          {selectedCategory === 'all' ? 'Maxsus Takliflar' : CATEGORIES.find(c => c.id === selectedCategory)?.name}
        </h2>
        <span className="offers-count">{offers.length} ta</span>
      </div>

      {/* Info banner if showing all cities */}
      {showingAllCities && offers.length > 0 && (
        <div className="all-cities-banner">
          <span className="all-cities-icon">🌍</span>
          <span className="all-cities-text">
            {cityRaw} da mahsulot yo'q. Barcha shaharlardan ko'rsatilmoqda
          </span>
        </div>
      )}

      {/* Offers Grid */}
      <div className="offers-grid">
        {loading && offers.length === 0 ? (
          Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="offer-card skeleton">
              <div className="skeleton-image" />
              <div className="skeleton-text" />
              <div className="skeleton-text short" />
            </div>
          ))
        ) : offers.length === 0 ? (
          <div style={{ gridColumn: '1 / -1', textAlign: 'center', padding: '60px 20px' }}>
            <div style={{ fontSize: '64px', marginBottom: '16px' }}>🔍</div>
            <h3 style={{ fontSize: '20px', color: '#181725', marginBottom: '8px' }}>Hech narsa topilmadi</h3>
            <p style={{ color: '#7C7C7C' }}>Boshqa so'z bilan qidiring</p>
          </div>
        ) : (
          offers.map(offer => (
            <OfferCard
              key={offer.id}
              offer={offer}
              cartQuantity={getCartQuantity(offer.id)}
              onAddToCart={addToCart}
              onRemoveFromCart={removeFromCart}
              onNavigate={onNavigate}
            />
          ))
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
        onNavigate={onNavigate}
        cartCount={cartCount}
      />

      {showAddressModal && (
        <div className="address-modal-overlay" onClick={() => setShowAddressModal(false)}>
          <div className="address-modal" onClick={(e) => e.stopPropagation()}>
            <div className="address-modal-header">
              <h3>Manzilni kiriting</h3>
              <button className="address-modal-close" onClick={() => setShowAddressModal(false)} aria-label="Yopish">
                ×
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

            <div className="address-divider">
              <span>yoki</span>
            </div>

            <label className="address-label">
              Shahar yoki hudud
              <input
                type="text"
                value={manualCity}
                onChange={(e) => setManualCity(e.target.value)}
                className="address-input"
                placeholder="Masalan, Toshkent, O'zbekiston"
              />
            </label>
            <label className="address-label">
              Aniq manzil
              <textarea
                value={manualAddress}
                onChange={(e) => setManualAddress(e.target.value)}
                className="address-textarea"
                placeholder="Ko'cha, uy, blok, mo'ljal"
              />
            </label>
            <div className="address-modal-actions">
              <button className="address-btn secondary" onClick={() => setShowAddressModal(false)}>
                Bekor qilish
              </button>
              <button className="address-btn" onClick={handleSaveManualAddress}>
                Saqlash
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default HomePage

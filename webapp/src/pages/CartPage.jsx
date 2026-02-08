import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { ShoppingCart, Home, Sparkles, ChevronRight, Trash2, Plus, Minus, LocateFixed } from 'lucide-react'
import api, { API_BASE_URL, getTelegramInitData } from '../api/client'
import { useCart } from '../context/CartContext'
import { useToast } from '../context/ToastContext'
import { getUnitLabel, blurOnEnter, isValidPhone } from '../utils/helpers'
import { calcTotalPrice } from '../utils/orderMath'
import { getCurrentUser, getUserId, getStoredPhone, setStoredPhone, setStoredUser } from '../utils/auth'
import { readStorageItem, writeStorageItem } from '../utils/storage'
import { PLACEHOLDER_IMAGE, resolveOfferImageUrl } from '../utils/imageUtils'
import { buildLocationFromReverseGeocode, saveLocation, getSavedLocation } from '../utils/cityUtils'
import { getCurrentLocation } from '../utils/geolocation'
import { readPendingPayment, savePendingPayment, clearPendingPayment } from '../utils/pendingPayment'
import { getOfferAvailability, getTashkentNowMinutes } from '../utils/availability'
import BottomNav from '../components/BottomNav'
import './CartPage.css'

const LEAFLET_CDN = 'https://unpkg.com/leaflet@1.9.4/dist'
const DEFAULT_MAP_CENTER = { lat: 41.2995, lon: 69.2401 }
const DEFAULT_WORKING_HOURS = '08:00 - 23:00'
const DELIVERY_SLOT_STEP = 30
const DELIVERY_SLOT_DURATION = 30
const FAST_DELIVERY_BUFFER = 35

const parseTimeToMinutes = (value) => {
  if (!value) return null
  const match = String(value).match(/(\d{1,2}):(\d{2})/)
  if (!match) return null
  const hours = Number(match[1])
  const minutes = Number(match[2])
  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) return null
  return hours * 60 + minutes
}

const extractRangeFromText = (text) => {
  if (!text) return null
  const match = String(text).match(/(\d{1,2}:\d{2}).*(\d{1,2}:\d{2})/)
  if (!match) return null
  return { start: match[1], end: match[2] }
}

const formatMinutesLabel = (value) => {
  const total = ((value % 1440) + 1440) % 1440
  const hours = Math.floor(total / 60)
  const minutes = total % 60
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`
}

const isSlotWithinWindow = (start, duration, windowStart, windowEnd) => {
  if (windowStart == null || windowEnd == null) return true
  const slotEnd = start + duration
  if (windowStart <= windowEnd) {
    return start >= windowStart && slotEnd <= windowEnd
  }
  if (start >= windowStart) {
    return slotEnd <= 1440
  }
  return slotEnd <= windowEnd
}

const normalizeAddressLabel = (value) => {
  if (!value) return ''
  const parts = String(value)
    .split(',')
    .map(part => part.trim())
    .filter(Boolean)
  const seen = new Set()
  const unique = []
  for (const part of parts) {
    const key = part.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    unique.push(part)
  }
  return unique.join(', ')
}

function CartPage({ user }) {
  const navigate = useNavigate()
  const location = useLocation()
  const isCheckoutRoute = location.pathname === '/checkout'
  const { toast } = useToast()
  // Use cart from context
  const {
    cartItems,
    cartCount,
    cartTotal,
    isEmpty,
    addToCart,
    updateQuantity,
    updateOfferData,
    replaceCart,
    removeItem,
    clearCart
  } = useCart()

  const botUsername = import.meta.env.VITE_BOT_USERNAME || 'fudlyuzbot'
  const cachedUser = getCurrentUser()
  const canonicalPhone = (user?.phone || cachedUser?.phone || '').toString().trim()
  const userId = getUserId()

  const [orderLoading, setOrderLoading] = useState(false)
  const [cartValidationLoading, setCartValidationLoading] = useState(false)
  const [deliveryValidationLoading, setDeliveryValidationLoading] = useState(false)
  const [deliveryCheck, setDeliveryCheck] = useState(null)
  const [pendingPayment, setPendingPayment] = useState(() => readPendingPayment())
  const [pendingActionLoading, setPendingActionLoading] = useState(false)
  const [pendingPulse, setPendingPulse] = useState(false)
  const pendingPulseRef = useRef(null)
  const addressInputRef = useRef(null)
  const commentInputRef = useRef(null)
  const lastDeliveryCheckRef = useRef({ address: '', storeId: null, city: '' })

  // Checkout form
  const [showCheckout, setShowCheckout] = useState(() => isCheckoutRoute)
  const [phone, setPhone] = useState(() => canonicalPhone || getStoredPhone() || '')
  const [address, setAddress] = useState(() => {
    try {
      const loc = JSON.parse(localStorage.getItem('fudly_location') || '{}')
      return normalizeAddressLabel(loc.address || '')
    } catch { return '' }
  })
  const [comment, setComment] = useState('')

  // Delivery type: 'pickup' or 'delivery'
  const [orderType, setOrderType] = useState('pickup')
  const [orderTypeTouched, setOrderTypeTouched] = useState(false)
  const [deliveryFee, setDeliveryFee] = useState(0)
  const [minOrderAmount, setMinOrderAmount] = useState(0)
  const [storeDeliveryEnabled, setStoreDeliveryEnabled] = useState(false)
  const [storeCity, setStoreCity] = useState('')
  const [storeWorkingHours, setStoreWorkingHours] = useState('')
  const [storeInfoLoading, setStoreInfoLoading] = useState(false)

  // Payment step for delivery
  const [checkoutStep, setCheckoutStep] = useState('details') // details only (no manual proof)
  const [paymentProviders, setPaymentProviders] = useState([])
  const [selectedPaymentMethod, setSelectedPaymentMethod] = useState('cash') // 'cash' | 'click'
  const [showPaymentSheet, setShowPaymentSheet] = useState(false)
  const [deliverySlot, setDeliverySlot] = useState('fast')
  const [orderItemsExpanded, setOrderItemsExpanded] = useState(false)
  const [showMapEditor, setShowMapEditor] = useState(false)
  const [addressMeta, setAddressMeta] = useState(() => {
    try {
      const raw = readStorageItem('fudly_address_meta')
      return raw ? JSON.parse(raw) : {}
    } catch {
      return {}
    }
  })
  const [deliveryCoords, setDeliveryCoords] = useState(() => {
    try {
      const saved = JSON.parse(localStorage.getItem('fudly_location') || '{}')
      const coords = saved?.coordinates
      if (coords?.lat != null && coords?.lon != null) {
        return { lat: coords.lat, lon: coords.lon }
      }
    } catch {
      return null
    }
    return null
  })
  const [storeOffers, setStoreOffers] = useState([])
  const [storeOffersLoading, setStoreOffersLoading] = useState(false)
  const checkoutMapRef = useRef(null)
  const checkoutMapInstanceRef = useRef(null)
  const checkoutMapMarkerRef = useRef(null)
  const addressRef = useRef(address)
  const markerDraggingRef = useRef(false)
  const mapResolveTimeoutRef = useRef(null)
  const mapSearchCloseTimeoutRef = useRef(null)
  const mapResolveSeqRef = useRef(0)
  const mapResolveFailSafeRef = useRef(null)
  const mapUserEditingRef = useRef(false)
  const [mapLoaded, setMapLoaded] = useState(false)
  const [mapError, setMapError] = useState('')
  const [mapResolving, setMapResolving] = useState(false)
  const [mapQuery, setMapQuery] = useState('')
  const [mapSearchResults, setMapSearchResults] = useState([])
  const [mapSearchLoading, setMapSearchLoading] = useState(false)
  const [mapSearchOpen, setMapSearchOpen] = useState(false)

  const getSavedCoordinates = useCallback(() => {
    try {
      const saved = JSON.parse(localStorage.getItem('fudly_location') || '{}')
      const coords = saved?.coordinates
      if (coords?.lat != null && coords?.lon != null) {
        return { lat: coords.lat, lon: coords.lon }
      }
    } catch {
      return null
    }
    return null
  }, [])

  const saveCoordsFallback = useCallback((lat, lon) => {
    try {
      const saved = JSON.parse(localStorage.getItem('fudly_location') || '{}')
      saveLocation({
        ...saved,
        coordinates: { lat, lon },
        source: saved?.source || 'geo',
      })
    } catch {
      saveLocation({ coordinates: { lat, lon }, source: 'geo' })
    }
  }, [])

  const updateAddressFromCoords = useCallback(async (lat, lon, options = {}) => {
    const { force = false } = options
    const requestId = ++mapResolveSeqRef.current
    setMapResolving(true)
    setMapError('')
    if (Number.isFinite(lat) && Number.isFinite(lon)) {
      setDeliveryCoords({ lat, lon })
    }

    if (mapResolveFailSafeRef.current) {
      clearTimeout(mapResolveFailSafeRef.current)
    }
    mapResolveFailSafeRef.current = setTimeout(() => {
      if (mapResolveSeqRef.current === requestId) {
        setMapResolving(false)
      }
    }, 8000)

    let resolved = null

    try {
      const apiData = await api.reverseGeocode(lat, lon, 'uz')
      if (apiData) {
        resolved = buildLocationFromReverseGeocode(apiData, lat, lon)
      }
    } catch (error) {
      console.warn('API reverse error:', error)
    }

    if (requestId !== mapResolveSeqRef.current) {
      return
    }

    if (resolved?.address) {
      const normalizedAddress = normalizeAddressLabel(resolved.address)
      setAddress(normalizedAddress)
      if (!mapUserEditingRef.current || force) {
        setMapQuery(normalizedAddress)
      }
      saveLocation({ ...resolved, address: normalizedAddress })
    } else {
      setMapError('Manzilni aniqlab bo\'lmadi')
      saveCoordsFallback(lat, lon)
    }

    if (mapResolveFailSafeRef.current) {
      clearTimeout(mapResolveFailSafeRef.current)
      mapResolveFailSafeRef.current = null
    }
    setMapResolving(false)
  }, [saveCoordsFallback])

  const showCheckoutSheet = showCheckout || isCheckoutRoute
  const mapEnabled = showCheckoutSheet && orderType === 'delivery' && showMapEditor
  const isMapLoading = mapEnabled && !mapLoaded && !mapError
  const isMapResolving = mapEnabled && mapResolving

  useEffect(() => {
    if (!mapEnabled) {
      setMapSearchOpen(false)
      return
    }
    setMapError('')
    setMapResolving(false)
  }, [mapEnabled])

  useEffect(() => {
    addressRef.current = address
  }, [address])

  useEffect(() => {
    if (mapSearchOpen) return
    setMapQuery(address || '')
  }, [address, mapSearchOpen])

  useEffect(() => {
    if (!mapEnabled || !mapSearchOpen) {
      setMapSearchResults([])
      setMapSearchLoading(false)
      return
    }

    const query = mapQuery.trim()
    if (query.length < 3) {
      setMapSearchResults([])
      setMapSearchLoading(false)
      return
    }

    let isActive = true
    const timeout = setTimeout(async () => {
      setMapSearchLoading(true)
      try {
        const response = await api.searchLocations(query, {
          lang: 'uz',
          limit: 6,
          lat: deliveryCoords?.lat,
          lon: deliveryCoords?.lon,
        })
        const data = Array.isArray(response?.items)
          ? response.items
          : (Array.isArray(response) ? response : [])
        if (!isActive) return
        setMapSearchResults(data)
      } catch (error) {
        console.warn('Map search error:', error)
        if (isActive) {
          setMapSearchResults([])
        }
      } finally {
        if (isActive) {
          setMapSearchLoading(false)
        }
      }
    }, 350)

    return () => {
      isActive = false
      clearTimeout(timeout)
    }
  }, [mapEnabled, mapQuery, mapSearchOpen, deliveryCoords?.lat, deliveryCoords?.lon])

  useEffect(() => {
    if (!mapEnabled) return
    if (window.L) {
      setMapLoaded(true)
      return
    }

    let isActive = true
    const cssHref = `${LEAFLET_CDN}/leaflet.css`
    if (!document.querySelector(`link[href="${cssHref}"]`)) {
      const link = document.createElement('link')
      link.rel = 'stylesheet'
      link.href = cssHref
      document.head.appendChild(link)
    }

    const scriptSrc = `${LEAFLET_CDN}/leaflet.js`
    const existingScript = document.querySelector(`script[src="${scriptSrc}"]`)
    const handleLoad = () => {
      if (!isActive) return
      setMapLoaded(true)
    }
    const handleError = () => {
      if (!isActive) return
      setMapError('Xarita yuklanmadi')
    }

    if (existingScript) {
      existingScript.addEventListener('load', handleLoad)
      existingScript.addEventListener('error', handleError)
      return () => {
        isActive = false
        existingScript.removeEventListener('load', handleLoad)
        existingScript.removeEventListener('error', handleError)
      }
    }

    const script = document.createElement('script')
    script.src = scriptSrc
    script.async = true
    script.onload = handleLoad
    script.onerror = handleError
    document.body.appendChild(script)

    return () => {
      isActive = false
    }
  }, [mapEnabled])

  useEffect(() => {
    if (!mapEnabled) {
      if (checkoutMapInstanceRef.current) {
        checkoutMapInstanceRef.current.remove()
        checkoutMapInstanceRef.current = null
      }
      if (checkoutMapMarkerRef.current) {
        checkoutMapMarkerRef.current = null
      }
      if (mapResolveTimeoutRef.current) {
        clearTimeout(mapResolveTimeoutRef.current)
        mapResolveTimeoutRef.current = null
      }
      if (mapSearchCloseTimeoutRef.current) {
        clearTimeout(mapSearchCloseTimeoutRef.current)
        mapSearchCloseTimeoutRef.current = null
      }
      return
    }

    if (!mapLoaded || !checkoutMapRef.current || checkoutMapInstanceRef.current) {
      if (checkoutMapInstanceRef.current) {
        checkoutMapInstanceRef.current.invalidateSize()
      }
      return
    }

    const leaflet = window.L
    if (!leaflet) return

    const savedCoords = getSavedCoordinates()
    const startLat = savedCoords?.lat ?? DEFAULT_MAP_CENTER.lat
    const startLon = savedCoords?.lon ?? DEFAULT_MAP_CENTER.lon
    const startZoom = savedCoords ? 16 : 12

    const map = leaflet.map(checkoutMapRef.current, {
      center: [startLat, startLon],
      zoom: startZoom,
      zoomControl: false,
      attributionControl: true,
      tap: false,
    })

    leaflet.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors',
    }).addTo(map)

    checkoutMapInstanceRef.current = map

    const markerIcon = leaflet.divIcon({
      className: 'checkout-map-marker',
      html: '<span></span>',
      iconSize: [36, 36],
      iconAnchor: [18, 34],
    })
    const marker = leaflet.marker([startLat, startLon], {
      draggable: true,
      icon: markerIcon,
    }).addTo(map)
    checkoutMapMarkerRef.current = marker

    const scheduleResolve = (lat, lon) => {
      if (mapResolveTimeoutRef.current) {
        clearTimeout(mapResolveTimeoutRef.current)
      }
      mapResolveTimeoutRef.current = setTimeout(() => {
        mapUserEditingRef.current = false
        updateAddressFromCoords(lat, lon, { force: true })
      }, 300)
    }

    const handleMove = () => {
      if (markerDraggingRef.current) return
      const center = map.getCenter()
      if (checkoutMapMarkerRef.current) {
        checkoutMapMarkerRef.current.setLatLng(center)
      }
    }

    const handleMoveEnd = () => {
      if (markerDraggingRef.current) return
      const center = map.getCenter()
      if (checkoutMapMarkerRef.current) {
        checkoutMapMarkerRef.current.setLatLng(center)
      }
      scheduleResolve(center.lat, center.lng)
    }

    map.on('move', handleMove)
    map.on('moveend', handleMoveEnd)
    map.on('dragend', handleMoveEnd)
    map.on('zoomend', handleMoveEnd)
    map.on('click', (event) => {
      if (checkoutMapMarkerRef.current) {
        checkoutMapMarkerRef.current.setLatLng(event.latlng)
      }
      map.panTo(event.latlng)
      scheduleResolve(event.latlng.lat, event.latlng.lng)
    })

    marker.on('dragstart', () => {
      markerDraggingRef.current = true
    })
    marker.on('dragend', () => {
      markerDraggingRef.current = false
      const pos = marker.getLatLng()
      map.panTo(pos)
      updateAddressFromCoords(pos.lat, pos.lng, { force: true })
    })

    const hasAddress = addressRef.current?.trim()
    if (savedCoords && !hasAddress) {
      scheduleResolve(savedCoords.lat, savedCoords.lon)
    }

    if (!savedCoords) {
      getCurrentLocation()
        .then(({ latitude, longitude }) => {
          map.setView([latitude, longitude], 16)
          if (checkoutMapMarkerRef.current) {
            checkoutMapMarkerRef.current.setLatLng([latitude, longitude])
          }
          scheduleResolve(latitude, longitude)
        })
        .catch(() => {
          setMapError('Geolokatsiyani aniqlab bo\'lmadi')
        })
    }

    requestAnimationFrame(() => {
      map.invalidateSize()
    })

    return () => {
      map.off('move', handleMove)
      map.off('moveend', handleMoveEnd)
      map.off('dragend', handleMoveEnd)
      map.off('zoomend', handleMoveEnd)
      map.off('click')
      marker.off('dragstart')
      marker.off('dragend')
      markerDraggingRef.current = false
      if (mapResolveTimeoutRef.current) {
        clearTimeout(mapResolveTimeoutRef.current)
        mapResolveTimeoutRef.current = null
      }
      if (mapResolveFailSafeRef.current) {
        clearTimeout(mapResolveFailSafeRef.current)
        mapResolveFailSafeRef.current = null
      }
    }
  }, [
    mapEnabled,
    mapLoaded,
    getSavedCoordinates,
    getCurrentLocation,
    updateAddressFromCoords,
  ])

  useEffect(() => {
    if (!mapEnabled || !checkoutMapInstanceRef.current) return
    const map = checkoutMapInstanceRef.current
    const timer = setTimeout(() => {
      map.invalidateSize()
    }, 180)
    return () => clearTimeout(timer)
  }, [mapEnabled, showCheckoutSheet])

  const handleMapResultSelect = (result) => {
    const lat = Number(result?.lat)
    const lon = Number(result?.lon)
    const label = result?.display_name || ''
    if (label) {
      const normalizedLabel = normalizeAddressLabel(label)
      setAddress(normalizedLabel)
      setMapQuery(normalizedLabel)
    }
    setMapSearchOpen(false)
    setMapSearchResults([])
    mapUserEditingRef.current = false
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return
    if (checkoutMapInstanceRef.current) {
      checkoutMapInstanceRef.current.setView([lat, lon], 16)
    }
    if (checkoutMapMarkerRef.current) {
      checkoutMapMarkerRef.current.setLatLng([lat, lon])
    }
    updateAddressFromCoords(lat, lon, { force: true })
  }

  const handleLocateMe = () => {
    setMapError('')
    setMapSearchOpen(false)
    mapUserEditingRef.current = false
    getCurrentLocation()
      .then(({ latitude, longitude }) => {
        if (checkoutMapInstanceRef.current) {
          checkoutMapInstanceRef.current.setView([latitude, longitude], 16)
        }
        if (checkoutMapMarkerRef.current) {
          checkoutMapMarkerRef.current.setLatLng([latitude, longitude])
        }
        updateAddressFromCoords(latitude, longitude, { force: true })
      })
      .catch(() => {
        setMapError('Geolokatsiyani aniqlab bo\'lmadi')
      })
  }

  // Success/Error modals
  const [orderResult, setOrderResult] = useState(null)

  // Keep phone in sync with server profile (bot registration is the single source)
  useEffect(() => {
    if (canonicalPhone && canonicalPhone !== phone) {
      setPhone(canonicalPhone)
      setStoredPhone(canonicalPhone)
    }
  }, [canonicalPhone, phone])

  const { entrance = '', floor = '', apartment = '' } = addressMeta

  useEffect(() => {
    writeStorageItem('fudly_address_meta', JSON.stringify(addressMeta))
  }, [addressMeta])

  const updateAddressMeta = useCallback((key, value) => {
    setAddressMeta(prev => ({ ...prev, [key]: value }))
  }, [])

  const cartStoreIds = useMemo(
    () => [...new Set(cartItems.map(item => item.offer?.store_id).filter(Boolean))],
    [cartItems]
  )
  const cartStoreId = cartStoreIds[0] || null
  const hasMultipleStores = cartStoreIds.length > 1
  const multiStoreMessage = "Savatda faqat bitta do'kondan mahsulot bo'lishi mumkin. Savatni tozalab qayta urinib ko'ring."
  const storeName =
    cartItems[0]?.offer?.store_name ||
    cartItems[0]?.offer?.store?.name ||
    "Do'kon"
  const recommendedOffers = useMemo(() => {
    if (!storeOffers.length) return []
    const cartOfferIds = new Set(
      cartItems.map(item => String(item.offer?.id)).filter(Boolean)
    )
    return storeOffers
      .filter(offer => {
        const offerId = offer?.id || offer?.offer_id
        if (!offerId) return false
        return !cartOfferIds.has(String(offerId))
      })
      .slice(0, 3)
  }, [storeOffers, cartItems])

  // Load payment providers for the current store (fallback to platform if needed)
  useEffect(() => {
    let isActive = true
    const loadProviders = async () => {
      if (!cartStoreId) {
        if (isActive) {
          setPaymentProviders([])
        }
        return
      }
      try {
        const providers = await api.getPaymentProviders(cartStoreId)
        if (isActive) {
          setPaymentProviders(providers)
        }
      } catch (e) {
        console.warn('Could not load payment providers:', e)
        if (isActive) {
          setPaymentProviders([])
        }
      }
    }
    loadProviders()
    return () => {
      isActive = false
    }
  }, [cartStoreId])

  // Check if stores in cart support delivery
  useEffect(() => {
    let isActive = true
    const checkDeliveryAvailability = async () => {
        if (!cartStoreId) {
          setStoreDeliveryEnabled(false)
          setDeliveryFee(0)
          setMinOrderAmount(0)
          setStoreCity('')
          setStoreWorkingHours('')
          setStoreInfoLoading(false)
          return
        }

      setStoreInfoLoading(true)
      try {
        const cartStore = await api.getStore(cartStoreId)

          if (cartStore && isActive) {
            setStoreDeliveryEnabled(!!cartStore.delivery_enabled)
            setDeliveryFee(cartStore.delivery_price || 0)
            setMinOrderAmount(cartStore.min_order_amount || 0)
            setStoreCity(
              cartStore.city ||
              cartStore.store_city ||
              cartStore.region ||
              cartStore.city_name ||
              ''
            )
            const hoursRaw =
              cartStore.working_hours ||
              cartStore.work_time ||
              (cartStore.open_time && cartStore.close_time
                ? `${cartStore.open_time} - ${cartStore.close_time}`
                : '')
            setStoreWorkingHours(hoursRaw || '')
          }
        } catch (e) {
          console.warn('Could not fetch store info:', e)
          if (isActive) {
            setStoreDeliveryEnabled(false)
            setDeliveryFee(0)
            setMinOrderAmount(0)
            setStoreCity('')
            setStoreWorkingHours('')
          }
      } finally {
        if (isActive) {
          setStoreInfoLoading(false)
        }
      }
    }

    checkDeliveryAvailability()
    return () => {
      isActive = false
    }
  }, [cartStoreId])

  useEffect(() => {
    let isActive = true
    const loadStoreOffers = async () => {
      if (!cartStoreId) {
        setStoreOffers([])
        setStoreOffersLoading(false)
        return
      }
      setStoreOffersLoading(true)
      try {
        const offers = await api.getStoreOffers(cartStoreId)
        if (!isActive) return
        const normalized = Array.isArray(offers)
          ? offers
          : (offers?.offers || offers?.items || [])
        setStoreOffers(normalized.filter(Boolean))
      } catch (error) {
        console.warn('Could not fetch store offers:', error)
        if (isActive) {
          setStoreOffers([])
        }
      } finally {
        if (isActive) {
          setStoreOffersLoading(false)
        }
      }
    }

    loadStoreOffers()
    return () => {
      isActive = false
    }
  }, [cartStoreId])

  // Calculate totals using context values
  const subtotal = cartTotal
  const total = calcTotalPrice(
    subtotal,
    orderType === 'delivery' ? deliveryFee : 0
  )
  const serviceFee = 0
  const checkoutTotal = calcTotalPrice(total, serviceFee)
  const itemsCount = cartCount
  const unavailableCartItems = useMemo(() => {
    return cartItems.filter((item) => {
      const availability = getOfferAvailability(item.offer)
      return availability.timeRange && !availability.isAvailableNow
    })
  }, [cartItems])
  const hasUnavailableItems = unavailableCartItems.length > 0
  const unavailableTimeRange = useMemo(() => {
    if (!hasUnavailableItems) return ''
    const availability = getOfferAvailability(unavailableCartItems[0]?.offer)
    return availability.timeRange || ''
  }, [hasUnavailableItems, unavailableCartItems])
  const savingsTotal = useMemo(() => {
    return cartItems.reduce((sum, item) => {
      const original = Number(item.offer.original_price)
      const discount = Number(item.offer.discount_price)
      if (!Number.isFinite(original) || !Number.isFinite(discount)) {
        return sum
      }
      if (original <= discount) {
        return sum
      }
      return sum + (original - discount) * item.quantity
    }, 0)
  }, [cartItems])
  const formatSum = (value) => Math.round(value || 0).toLocaleString('ru-RU')
  const originalTotal = calcTotalPrice(subtotal, savingsTotal)
  const savingsLabel = savingsTotal > 0 ? `-${formatSum(savingsTotal)} so'm` : `0 so'm`
    const deliveryOptions = useMemo(() => {
      const hoursRaw = storeWorkingHours || DEFAULT_WORKING_HOURS
      const range = extractRangeFromText(hoursRaw)
      const startMinutes = parseTimeToMinutes(range?.start || hoursRaw)
      const endMinutes = parseTimeToMinutes(range?.end || hoursRaw)
      const nowMinutes = getTashkentNowMinutes()

      if (startMinutes == null || endMinutes == null) {
        return [
          { id: 'fast', label: 'Tezda', time: '25-35 daqiqa' },
          { id: 'slot-1', label: 'Bugun', time: '18:00 - 18:30' },
          { id: 'slot-2', label: 'Bugun', time: '19:00 - 19:30' },
        ]
      }

      const options = []
      const canFast = isSlotWithinWindow(
        nowMinutes,
        FAST_DELIVERY_BUFFER,
        startMinutes,
        endMinutes
      )
      options.push({
        id: 'fast',
        label: 'Tezda',
        time: '25-35 daqiqa',
        disabled: !canFast,
      })

      const buildSlotsForDay = (dayOffset, startAtMinutes) => {
        const label = dayOffset === 0 ? 'Bugun' : 'Ertaga'
        const slots = []
        for (
          let start = startAtMinutes;
          start <= 1440 - DELIVERY_SLOT_DURATION;
          start += DELIVERY_SLOT_STEP
        ) {
          if (!isSlotWithinWindow(start, DELIVERY_SLOT_DURATION, startMinutes, endMinutes)) {
            continue
          }
          slots.push({
            id: `slot-${dayOffset}-${start}`,
            label,
            time: `${formatMinutesLabel(start)} - ${formatMinutesLabel(start + DELIVERY_SLOT_DURATION)}`,
          })
          if (slots.length >= 2) break
        }
        return slots
      }

      const baseStart = Math.ceil(nowMinutes / DELIVERY_SLOT_STEP) * DELIVERY_SLOT_STEP
      const slots = baseStart < 1440 ? buildSlotsForDay(0, baseStart) : []
      if (slots.length < 2) {
        slots.push(...buildSlotsForDay(1, 0))
      }

      return options.concat(slots)
    }, [storeWorkingHours])
    const deliverySlotLabel = useMemo(() => {
      const option = deliveryOptions.find(item => item.id === deliverySlot)
      if (!option) return ''
      if (option.id === 'fast') {
        return option.time || option.label || ''
      }
      if (option.label && option.time) {
        return `${option.label} ${option.time}`
      }
      return option.time || option.label || ''
    }, [deliveryOptions, deliverySlot])
  const autoOrderType = useMemo(() => {
    if (storeInfoLoading) return orderType
    if (!storeDeliveryEnabled) return 'pickup'
    return 'delivery'
  }, [storeDeliveryEnabled, storeInfoLoading, orderType])
  const deliveryOptionDisabled = storeInfoLoading || !storeDeliveryEnabled
  const deliverySummaryCost = deliveryCheck?.deliveryCost ?? (Number.isFinite(deliveryFee) ? deliveryFee : null)
  const deliverySummaryMin = deliveryCheck?.minOrderAmount ?? (Number.isFinite(minOrderAmount) ? minOrderAmount : null)
  const deliverySummaryEta = deliveryCheck?.estimatedTime || ''
  const deliveryMinNotMet = Number.isFinite(minOrderAmount) && minOrderAmount > 0 && subtotal < minOrderAmount
  const deliveryStatus = useMemo(() => {
    if (orderType !== 'delivery') return null
    if (deliveryValidationLoading) {
      return {
        status: 'pending',
        label: 'Tekshirilmoqda...',
        message: 'Manzil tekshirilmoqda...',
      }
    }

    if (!storeInfoLoading && !storeDeliveryEnabled) {
      return {
        status: 'error',
        label: 'Mavjud emas',
        message: 'Yetkazib berish mavjud emas',
      }
    }

    const trimmedAddress = address.trim()
    if (!trimmedAddress) {
      return {
        status: 'warn',
        label: 'Manzil kiritilmagan',
        message: 'Manzil kiritilmagan',
      }
    }

    if (deliveryCheck) {
      if (!deliveryCheck.canDeliver) {
        return {
          status: deliveryCheck.status || 'error',
          label: deliveryCheck.label || 'Mavjud emas',
          message: deliveryCheck.message || 'Yetkazib berish mavjud emas',
        }
      }
      if (deliveryMinNotMet) {
        return {
          status: 'warn',
          label: 'Minimal buyurtma talab qilinadi',
          message: deliveryCheck.message || 'Minimal buyurtma talab qilinadi',
        }
      }
      return {
        status: deliveryCheck.status || 'ok',
        label: deliveryCheck.label || 'Mavjud',
        message: deliveryCheck.message || '',
      }
    }

    if (deliveryMinNotMet) {
      return {
        status: 'warn',
        label: 'Minimal buyurtma talab qilinadi',
        message: 'Minimal buyurtma talab qilinadi',
      }
    }

    if (storeInfoLoading) {
      return {
        status: 'pending',
        label: 'Tekshirilmoqda...',
        message: 'Yetkazib berish shartlari tekshirilmoqda...',
      }
    }

    return {
      status: 'pending',
      label: 'Tekshirilmoqda...',
      message: 'Manzil tekshirilmoqda...',
    }
  }, [
    address,
    deliveryCheck,
    deliveryMinNotMet,
    deliveryValidationLoading,
    orderType,
    storeDeliveryEnabled,
    storeInfoLoading,
  ])
  const pendingItemsCount = useMemo(() => {
    const cart = pendingPayment?.cart
    if (!cart || typeof cart !== 'object') return 0
    return Object.values(cart).reduce((sum, item) => sum + Number(item?.quantity || 0), 0)
  }, [pendingPayment])
  const hasPendingPayment = Boolean(pendingPayment?.orderId)

  // Check if minimum order met for delivery
  const canDelivery = subtotal >= minOrderAmount
  const isProviderAvailable = (provider) => paymentProviders.includes(provider)
  const hasOnlineProviders = paymentProviders.includes('click')
  const hasPrepayProviders = hasOnlineProviders
  const deliveryCashEnabled = ['1', 'true', 'yes', 'on'].includes(
    String(import.meta.env.VITE_DELIVERY_CASH_ENABLED ?? '0').toLowerCase()
  )
  const deliveryRequiresPrepay = orderType === 'delivery' && !deliveryCashEnabled
  const checkoutTitle = "Buyurtmani rasmiylashtirish"
  const paymentOptions = [
    {
      id: 'click',
      label: 'Click',
      icon: 'click',
      disabled: !isProviderAvailable('click'),
    },
    {
      id: 'cash',
      label: 'Naqd pul',
      icon: 'cash',
      disabled: deliveryRequiresPrepay,
    },
  ]
  const paymentIconLabels = {
    click: 'Click',
    cash: 'Naqd',
  }
  const checkoutBusy = orderLoading || cartValidationLoading || deliveryValidationLoading
  const checkoutButtonLabel = orderLoading
    ? 'Buyurtma yuborilmoqda...'
    : cartValidationLoading
      ? 'Savat tekshirilmoqda...'
      : deliveryValidationLoading
        ? 'Manzil tekshirilmoqda...'
        : 'Buyurtmani tasdiqlash'

  useEffect(() => {
    if (!deliveryRequiresPrepay) return
    if (selectedPaymentMethod !== 'cash') return
    if (hasOnlineProviders) {
      setSelectedPaymentMethod('click')
    }
  }, [deliveryRequiresPrepay, hasOnlineProviders, selectedPaymentMethod])

  useEffect(() => {
    if (storeInfoLoading) return
    if (!storeDeliveryEnabled && orderType === 'delivery') {
      setOrderType('pickup')
      setOrderTypeTouched(false)
      return
    }
    if (orderTypeTouched) return
    if (orderType !== autoOrderType) {
      setOrderType(autoOrderType)
    }
  }, [autoOrderType, orderType, orderTypeTouched, storeDeliveryEnabled, storeInfoLoading])

  useEffect(() => {
    if (!deliveryOptions.length) return
    const current = deliveryOptions.find(option => option.id === deliverySlot && !option.disabled)
    if (current) return
    const next = deliveryOptions.find(option => !option.disabled) || deliveryOptions[0]
    if (next && next.id !== deliverySlot) {
      setDeliverySlot(next.id)
    }
  }, [deliveryOptions, deliverySlot])

  useEffect(() => {
    if (orderType !== 'delivery' && showMapEditor) {
      setShowMapEditor(false)
    }
  }, [orderType, showMapEditor])

  useEffect(() => {
    if (!isCheckoutRoute) {
      return
    }
    setShowCheckout(true)
    setCheckoutStep('details')
    setShowPaymentSheet(false)
  }, [isCheckoutRoute])

  useEffect(() => {
    const syncPending = () => setPendingPayment(readPendingPayment())
    syncPending()
    window.addEventListener('focus', syncPending)
    document.addEventListener('visibilitychange', syncPending)
    return () => {
      window.removeEventListener('focus', syncPending)
      document.removeEventListener('visibilitychange', syncPending)
    }
  }, [])

  const selectPaymentMethod = (method) => {
    setSelectedPaymentMethod(method)
  }

  const closeCheckout = () => {
    if (orderLoading || cartValidationLoading || deliveryValidationLoading) return
    setShowCheckout(false)
    setShowPaymentSheet(false)
    setOrderTypeTouched(false)
    setOrderItemsExpanded(false)
    setShowMapEditor(false)
    setMapSearchOpen(false)
    if (isCheckoutRoute) {
      navigate('/cart')
    }
  }

  const handleClearCart = useCallback(() => {
    const message = "Savatni tozalashni xohlaysizmi?"
    const tg = window.Telegram?.WebApp
    if (tg?.showConfirm) {
      tg.showConfirm(message, (confirmed) => {
        if (confirmed) {
          clearCart()
        }
      })
      return
    }
    if (window.confirm(message)) {
      clearCart()
    }
  }, [clearCart])

  const handleRestorePendingCart = useCallback(() => {
    if (!pendingPayment?.cart) {
      toast.error("Savatni tiklab bo'lmadi")
      return
    }
    if (!isEmpty) {
      const message = "Joriy savat almashtiriladi. Davom etasizmi?"
      const tg = window.Telegram?.WebApp
      if (tg?.showConfirm) {
        tg.showConfirm(message, (confirmed) => {
          if (!confirmed) return
          replaceCart(pendingPayment.cart)
          clearPendingPayment()
          setPendingPayment(null)
          toast.success("Savat tiklandi")
        })
        return
      }
      if (!window.confirm(message)) {
        return
      }
    }
    replaceCart(pendingPayment.cart)
    clearPendingPayment()
    setPendingPayment(null)
    toast.success("Savat tiklandi")
  }, [pendingPayment, replaceCart, toast, isEmpty])

  const handleResumePayment = useCallback(async () => {
    if (!pendingPayment?.orderId) return
    if (pendingActionLoading) return
    setPendingActionLoading(true)
    try {
      const status = await api.getOrderStatus(pendingPayment.orderId)
      const orderStatus = String(status?.status || status?.order_status || '').toLowerCase()
      const paymentStatus = String(status?.payment_status || '').toLowerCase()
      const doneStatuses = new Set(['completed', 'delivering', 'ready', 'preparing'])
      if (paymentStatus && paymentStatus !== 'awaiting_payment') {
        clearPendingPayment()
        setPendingPayment(null)
        toast.info("To'lov allaqachon yakunlangan")
        return
      }
      if (['cancelled', 'rejected'].includes(orderStatus)) {
        toast.error("Buyurtma bekor qilingan")
        return
      }
      if (doneStatuses.has(orderStatus)) {
        clearPendingPayment()
        setPendingPayment(null)
        toast.info("Buyurtma allaqachon tasdiqlangan")
        return
      }

      const storeId = pendingPayment.storeId || cartItems[0]?.offer?.store_id || null
      const returnUrl = `${window.location.origin}/order/${pendingPayment.orderId}/details`
      const paymentData = await api.createPaymentLink(
        pendingPayment.orderId,
        pendingPayment.provider || 'click',
        returnUrl,
        storeId,
        pendingPayment.total ?? null
      )
      if (paymentData?.payment_url) {
        if (window.Telegram?.WebApp?.openLink) {
          window.Telegram?.WebApp?.openLink?.(paymentData.payment_url)
        } else {
          window.location.href = paymentData.payment_url
        }
      } else {
        toast.error("To'lov havolasi olinmadi")
      }
    } catch (error) {
      toast.error("To'lovni davom ettirib bo'lmadi")
    } finally {
      setPendingActionLoading(false)
    }
  }, [pendingActionLoading, pendingPayment, toast, cartItems])

  const refreshPendingStatus = useCallback(async () => {
    if (!pendingPayment?.orderId) return
    try {
      const data = await api.getOrderStatus(pendingPayment.orderId)
      const orderStatus = String(data?.status || data?.order_status || '').toLowerCase()
      const paymentStatus = String(data?.payment_status || '').toLowerCase()
      const awaiting = paymentStatus === 'awaiting_payment' || orderStatus === 'awaiting_payment'
      const doneStatuses = new Set(['completed', 'cancelled', 'rejected', 'delivering', 'ready', 'preparing'])
      if (!awaiting && (doneStatuses.has(orderStatus) || paymentStatus === 'confirmed')) {
        clearPendingPayment()
        setPendingPayment(null)
      }
    } catch (error) {
      // ignore status check errors
    }
  }, [pendingPayment?.orderId])

  const buildCartSnapshot = useCallback(() => {
    const snapshot = {}
    cartItems.forEach((item) => {
      const offerId = item.offer?.id
      if (!offerId) return
      snapshot[String(offerId)] = {
        offer: item.offer,
        quantity: item.quantity,
      }
    })
    return snapshot
  }, [cartItems])

  useEffect(() => {
    if (!pendingPayment?.orderId) return

    refreshPendingStatus()
    const interval = setInterval(() => {
      refreshPendingStatus()
    }, 15000)

    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        refreshPendingStatus()
      }
    }

    window.addEventListener('focus', handleVisibility)
    document.addEventListener('visibilitychange', handleVisibility)

    return () => {
      clearInterval(interval)
      window.removeEventListener('focus', handleVisibility)
      document.removeEventListener('visibilitychange', handleVisibility)
    }
  }, [pendingPayment?.orderId, refreshPendingStatus])

  useEffect(() => {
    if (!pendingPayment?.orderId) {
      pendingPulseRef.current = null
      setPendingPulse(false)
      return
    }
    if (pendingPulseRef.current !== pendingPayment.orderId) {
      setPendingPulse(true)
      const timer = setTimeout(() => setPendingPulse(false), 420)
      pendingPulseRef.current = pendingPayment.orderId
      return () => clearTimeout(timer)
    }
    return undefined
  }, [pendingPayment?.orderId])

  useEffect(() => {
    if (!userId || !pendingPayment?.orderId) return

    const buildWsUrl = () => {
      const envBase = import.meta.env.VITE_WS_URL
      const baseSource = (envBase || API_BASE_URL || '').trim()
      if (!baseSource) return ''

      let base = baseSource
      if (!base.startsWith('ws://') && !base.startsWith('wss://')) {
        base = base.replace(/^http/, 'ws')
      }
      base = base.replace(/\/api\/v1\/?$/, '')
      base = base.replace(/\/+$/, '')

      let wsEndpoint = ''
      if (base.endsWith('/ws/notifications')) {
        wsEndpoint = base
      } else if (base.endsWith('/ws')) {
        wsEndpoint = `${base}/notifications`
      } else {
        wsEndpoint = `${base}/ws/notifications`
      }

      const params = new URLSearchParams()
      if (userId) {
        params.set('user_id', userId)
      }
      const initData = getTelegramInitData()
      if (initData) {
        params.set('init_data', initData)
      }
      const query = params.toString()
      return `${wsEndpoint}${query ? `?${query}` : ''}`
    }

    const wsUrl = buildWsUrl()
    if (!wsUrl) return

    let ws
    try {
      ws = new WebSocket(wsUrl)
    } catch (error) {
      console.warn('WebSocket init failed:', error)
      return
    }

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data)
        const type = payload?.type
        const data =
          payload?.payload?.data ||
          payload?.payload ||
          payload?.data ||
          {}
        const eventOrderId = data?.order_id || data?.booking_id

        if (type === 'order_status_changed' || type === 'order_created') {
          if (!eventOrderId || Number(eventOrderId) === Number(pendingPayment?.orderId)) {
            refreshPendingStatus()
          }
        }
      } catch (error) {
        console.warn('Failed to parse order update:', error)
      }
    }

    return () => {
      if (ws) {
        ws.close()
      }
    }
  }, [userId, pendingPayment?.orderId, refreshPendingStatus])

  // Handle quantity change with delta (+1 or -1)
  const handleQuantityChange = (offerId, delta) => {
    const item = cartItems.find(i => i.offer.id === offerId)
    if (item) {
      const newQty = item.quantity + delta
      if (newQty <= 0) {
        removeItem(offerId)
      } else {
        updateQuantity(offerId, newQty)
      }
    }
  }

  const refreshProfilePhone = useCallback(async () => {
    try {
      const profile = await api.getProfile({ force: true })
      const profilePhone = (profile?.phone || '').toString().trim()
      if (!profilePhone) {
        return ''
      }
      const mergedUser = { ...(getCurrentUser() || {}), ...profile }
      setStoredUser(mergedUser)
      setStoredPhone(profilePhone)
      setPhone(profilePhone)
      return profilePhone
    } catch (error) {
      console.warn('Could not refresh profile phone:', error)
      return ''
    }
  }, [setPhone])

  const requireVerifiedPhone = async () => {
    let verifiedPhone = canonicalPhone
    if (!verifiedPhone) {
      verifiedPhone = await refreshProfilePhone()
    }
    if (!verifiedPhone) {
      toast.error('Telefon raqamingiz botda tasdiqlanmagan. Botga o\'ting va raqamni yuboring.')
      if (botUsername) {
        const tg = window.Telegram?.WebApp
        const url = `https://t.me/${botUsername}?start=register`
        if (tg?.openTelegramLink) {
          tg.openTelegramLink(url)
        } else {
          window.open(url, '_blank', 'noopener,noreferrer')
        }
      }
      return ''
    }
    return verifiedPhone
  }

  const resolveDeliveryCity = useCallback(() => {
    const savedLocation = getSavedLocation()
    const candidate =
      savedLocation?.city ||
      user?.city ||
      cachedUser?.city ||
      storeCity ||
      ''
    return String(candidate || '').trim()
  }, [cachedUser?.city, storeCity, user?.city])

  useEffect(() => {
    if (orderType !== 'delivery') {
      setDeliveryCheck(null)
      return
    }
    setDeliveryCheck(null)
  }, [address, orderType, cartStoreId])


  const validateCartWithServer = useCallback(async () => {
    if (isEmpty) {
      return { ok: false, reason: 'empty' }
    }

    const payload = cartItems
      .map((item) => ({
        offerId: item.offer?.id,
        quantity: item.quantity,
      }))
      .filter((item) => item.offerId && item.quantity > 0)

    if (payload.length === 0) {
      toast.error("Savat bo'sh yoki mahsulotlar topilmadi")
      return { ok: false, reason: 'invalid' }
    }

    try {
      const response = await api.calculateCart(payload)
      const serverItems = Array.isArray(response?.items) ? response.items : []

      if (serverItems.length === 0) {
        toast.error("Savatdagi mahsulotlar endi mavjud emas")
        return { ok: false, reason: 'missing' }
      }

      const serverMap = new Map(
        serverItems.map((item) => [String(item.offer_id), item])
      )

      const missingIds = []
      const updates = []

      cartItems.forEach((item) => {
        const offerId = item.offer?.id
        if (!offerId) return
        const serverItem = serverMap.get(String(offerId))
        if (!serverItem) {
          missingIds.push(offerId)
          return
        }

        const serverPrice = Number(serverItem.price ?? 0)
        const localPrice = Number(
          item.offer?.discount_price ?? item.offer?.original_price ?? 0
        )

        if (Number.isFinite(serverPrice) && serverPrice > 0) {
          const priceChanged =
            !Number.isFinite(localPrice) || Math.round(serverPrice) !== Math.round(localPrice)
          if (priceChanged) {
            updates.push({
              offerId,
              patch: {
                discount_price: serverPrice,
                title: serverItem.title || item.offer?.title,
                photo: serverItem.photo || item.offer?.photo,
              },
            })
          }
        }
      })

      if (missingIds.length > 0) {
        missingIds.forEach((id) => removeItem(id))
      }
      if (updates.length > 0) {
        updateOfferData(updates)
      }

      if (missingIds.length > 0 || updates.length > 0) {
        toast.warning("Savat yangilandi. Iltimos, qayta tekshiring.")
        return { ok: false, reason: 'updated' }
      }

      return { ok: true }
    } catch (error) {
      console.warn('Cart validation failed:', error)
      toast.error("Savatni tekshirib bo'lmadi. Qayta urinib ko'ring.")
      return { ok: false, reason: 'error' }
    }
  }, [cartItems, isEmpty, removeItem, toast, updateOfferData])

  const validateDeliveryWithServer = useCallback(async () => {
    if (orderType !== 'delivery') {
      return { ok: true }
    }
    const shouldToast = !showCheckoutSheet
    if (!storeDeliveryEnabled) {
      if (shouldToast) {
        toast.error('Yetkazib berish mavjud emas')
      }
      setDeliveryCheck({
        status: 'error',
        canDeliver: false,
        label: 'Mavjud emas',
        message: 'Yetkazib berish mavjud emas',
      })
      return { ok: false, reason: 'disabled' }
    }
    if (!cartStoreId) {
      if (shouldToast) {
        toast.error('Do\'kon topilmadi')
      }
      setDeliveryCheck({
        status: 'error',
        canDeliver: false,
        label: 'Mavjud emas',
        message: 'Do\'kon topilmadi',
      })
      return { ok: false, reason: 'store' }
    }

    const trimmedAddress = address.trim()
    if (!trimmedAddress) {
      if (shouldToast) {
        toast.warning('Yetkazib berish manzilini kiriting')
      }
      setDeliveryCheck({
        status: 'warn',
        canDeliver: false,
        label: 'Manzil kiritilmagan',
        message: 'Manzil kiritilmagan',
      })
      return { ok: false, reason: 'address' }
    }

    const city = resolveDeliveryCity()
    lastDeliveryCheckRef.current = { address: trimmedAddress, storeId: cartStoreId, city }
    if (!city) {
      if (shouldToast) {
        toast.warning('Shaharni tanlang')
      }
      setDeliveryCheck({
        status: 'warn',
        canDeliver: false,
        label: 'Shahar tanlanmagan',
        message: 'Shaharni tanlang',
      })
      return { ok: false, reason: 'city' }
    }

    try {
      const response = await new Promise((resolve, reject) => {
        const timer = setTimeout(() => {
          reject(new Error('Delivery validation timeout'))
        }, 8000)
        api.calculateDelivery({
          city,
          address: trimmedAddress,
          store_id: cartStoreId,
        })
          .then((data) => {
            clearTimeout(timer)
            resolve(data)
          })
          .catch((error) => {
            clearTimeout(timer)
            reject(error)
          })
      })

      const canDeliver = Boolean(
        response?.can_deliver ??
        response?.canDeliver ??
        response?.ok
      )

      if (!canDeliver) {
        if (shouldToast) {
          toast.error(response?.message || 'Yetkazib berish mavjud emas')
        }
        setDeliveryCheck({
          status: 'error',
          canDeliver: false,
          label: 'Mavjud emas',
          message: response?.message || 'Yetkazib berish mavjud emas',
        })
        return { ok: false, reason: 'unavailable' }
      }

      const serverFee = Number(
        response?.delivery_cost ??
        response?.delivery_fee ??
        response?.deliveryPrice ??
        response?.delivery_price ??
        deliveryFee
      )
      const serverMin = Number(
        response?.min_order_amount ??
        response?.minOrderAmount ??
        minOrderAmount
      )
      const estimatedTime =
        response?.estimated_time ??
        response?.estimatedTime ??
        response?.eta ??
        ''

      let updated = false
      if (Number.isFinite(serverFee) && Math.round(serverFee) !== Math.round(Number(deliveryFee || 0))) {
        setDeliveryFee(serverFee)
        updated = true
      }
      if (Number.isFinite(serverMin) && Math.round(serverMin) !== Math.round(Number(minOrderAmount || 0))) {
        setMinOrderAmount(serverMin)
        updated = true
      }

      setDeliveryCheck({
        status: updated ? 'warn' : 'ok',
        canDeliver: true,
        deliveryCost: Number.isFinite(serverFee) ? serverFee : null,
        minOrderAmount: Number.isFinite(serverMin) ? serverMin : null,
        estimatedTime,
        label: 'Mavjud',
        message: response?.message || '',
      })

      if (updated) {
        if (shouldToast) {
          toast.warning("Yetkazib berish shartlari yangilandi. Iltimos, qayta tekshiring.")
        }
        return { ok: false, reason: 'updated' }
      }

      if (Number.isFinite(serverMin) && serverMin > 0 && subtotal < serverMin) {
        if (shouldToast) {
          toast.warning(
            `Yetkazib berish uchun minimum ${formatSum(serverMin)} so'm buyurtma qiling`
          )
        }
        setDeliveryCheck((prev) => ({
          ...(prev || {}),
          status: 'warn',
          message: 'Minimal buyurtma talab qilinadi',
        }))
        return { ok: false, reason: 'min' }
      }

      return { ok: true }
    } catch (error) {
      console.warn('Delivery validation failed:', error)
      if (shouldToast) {
        toast.error("Yetkazib berish narxini tekshirib bo'lmadi. Qayta urinib ko'ring.")
      }
      setDeliveryCheck({
        status: 'error',
        canDeliver: false,
        message: "Tekshirib bo'lmadi",
      })
      return { ok: false, reason: 'error' }
    }
  }, [
    address,
    cartStoreId,
    deliveryFee,
    formatSum,
    minOrderAmount,
    orderType,
    resolveDeliveryCity,
    showCheckoutSheet,
    storeDeliveryEnabled,
    subtotal,
    toast,
  ])

  const pendingPaymentCard = hasPendingPayment ? (
    <div className={`pending-payment-card animate-in`}>
      <div className="pending-payment-header">
        <div>
          <p className="pending-payment-title">To'lov kutilmoqda</p>
          <p className="pending-payment-subtitle">
            Buyurtma #{pendingPayment.orderId}
            {pendingItemsCount > 0 ? ` - ${pendingItemsCount} dona` : ''}
            {pendingPayment.total ? ` - ${formatSum(pendingPayment.total)} so'm` : ''}
          </p>
        </div>
        <span className={`pending-payment-badge ${pendingPulse ? 'pulse' : ''}`}>
          {String(pendingPayment.provider || 'click').toUpperCase()}
        </span>
      </div>
      <div className="pending-payment-actions">
        <button
          type="button"
          className="pending-payment-btn primary"
          onClick={handleResumePayment}
          disabled={pendingActionLoading}
        >
          {pendingActionLoading ? "Tekshirilmoqda..." : "To'lovni davom ettirish"}
        </button>
        <button
          type="button"
          className="pending-payment-btn secondary"
          onClick={handleRestorePendingCart}
          disabled={pendingActionLoading}
        >
          Savatni tiklash
        </button>
      </div>
    </div>
  ) : null

  useEffect(() => {
    if (!showCheckoutSheet) return
    if (orderType !== 'delivery') return
    if (!storeDeliveryEnabled || !cartStoreId) return
    if (deliveryValidationLoading || orderLoading) return

    const trimmedAddress = address.trim()
    if (trimmedAddress.length < 3) return

    const city = resolveDeliveryCity()

    const lastCheck = lastDeliveryCheckRef.current
    if (
      lastCheck.address === trimmedAddress &&
      lastCheck.storeId === cartStoreId &&
      lastCheck.city === city
    ) {
      return
    }

    const timer = setTimeout(async () => {
      if (deliveryValidationLoading || orderLoading) return
      setDeliveryValidationLoading(true)
      await validateDeliveryWithServer()
      setDeliveryValidationLoading(false)
    }, 650)

    return () => clearTimeout(timer)
  }, [
    address,
    cartStoreId,
    deliveryValidationLoading,
    orderLoading,
    orderType,
    resolveDeliveryCity,
    showCheckoutSheet,
    storeDeliveryEnabled,
    validateDeliveryWithServer,
  ])

  const handleCheckout = async () => {
    if (isEmpty) return
    if (hasMultipleStores) {
      toast.error(multiStoreMessage)
      return
    }
    const verifiedPhone = await requireVerifiedPhone()
    if (!verifiedPhone) {
      return
    }
    setOrderType(autoOrderType)
    setOrderTypeTouched(false)
    setOrderItemsExpanded(false)
    setShowMapEditor(false)
    setMapSearchOpen(false)
    setCheckoutStep('details')
    if (!isCheckoutRoute) {
      navigate('/checkout')
      return
    }
    setShowCheckout(true)
  }

  const getResolvedPhone = useCallback(
    () => (canonicalPhone || phone || '').trim(),
    [canonicalPhone, phone]
  )

  const normalizePhoneInput = (value) => value.replace(/[^\d+]/g, '')

  const ensurePhoneOrPrompt = () => {
    const resolved = getResolvedPhone()
    if (!resolved) {
      toast.error('Telefon raqamini kiriting yoki botda tasdiqlang.')
      if (botUsername) {
        const tg = window.Telegram?.WebApp
        const url = `https://t.me/${botUsername}?start=register`
        if (tg?.openTelegramLink) {
          tg.openTelegramLink(url)
        } else {
          window.open(url, '_blank', 'noopener,noreferrer')
        }
      }
      return ''
    }

    const normalized = normalizePhoneInput(resolved)
    if (!canonicalPhone && !isValidPhone(normalized)) {
      toast.error('Telefon formati: +998XXXXXXXXX')
      return ''
    }

    return normalized
  }

  const buildDeliveryAddress = useCallback(() => {
    if (orderType !== 'delivery') return null
    const trimmedAddress = address.trim()
    if (!trimmedAddress) return null
    const lines = [trimmedAddress]
    if (entrance.trim()) lines.push(`Kiraverish: ${entrance.trim()}`)
    if (floor.trim()) lines.push(`Qavat: ${floor.trim()}`)
    if (apartment.trim()) lines.push(`Xonadon: ${apartment.trim()}`)
    return lines.join('\n')
  }, [orderType, address, entrance, floor, apartment])

  const buildOrderComment = useCallback(() => {
    const lines = [orderType === 'pickup' ? "O'zi olib ketadi" : 'Yetkazib berish']
    if (orderType === 'delivery' && deliverySlotLabel) {
      lines.push(`Yetkazish vaqti: ${deliverySlotLabel}`)
    }
    if (comment.trim()) lines.push(comment.trim())
    return lines.join('\n').trim()
  }, [orderType, deliverySlotLabel, comment])

  // Proceed to payment
  const proceedToPayment = async () => {
    if (hasUnavailableItems) {
      const message = unavailableTimeRange
        ? `Buyurtma vaqti: ${unavailableTimeRange}`
        : 'Hozir buyurtma qilish mumkin emas'
      toast.warning(message)
      return
    }
    const resolvedPhone = ensurePhoneOrPrompt()
    if (!resolvedPhone) {
      return
    }
    if (orderType === 'delivery' && !address.trim()) {
      toast.warning('Yetkazib berish manzilini kiriting')
      return
    }
    if (deliveryRequiresPrepay && !hasOnlineProviders) {
      toast.error('Yetkazib berish uchun to\'lov usullari mavjud emas')
      return
    }

    if (orderLoading || cartValidationLoading || deliveryValidationLoading) return
    setCartValidationLoading(true)
    const validation = await validateCartWithServer()
    setCartValidationLoading(false)
    if (!validation.ok) {
      return
    }

    if (orderType === 'delivery') {
      setDeliveryValidationLoading(true)
      const deliveryValidation = await validateDeliveryWithServer()
      setDeliveryValidationLoading(false)
      if (!deliveryValidation.ok) {
        return
      }
    }

    if (selectedPaymentMethod === 'click') {
      await handleOnlinePayment()
      return
    }

    await placeOrder()
  }

  // Place order (cash/pickup)
  const placeOrder = async () => {
    if (isEmpty) return
    if (orderType === 'delivery' && storeDeliveryEnabled && !canDelivery) {
      toast.warning(
        `Yetkazib berish uchun minimum ${formatSum(minOrderAmount)} so'm buyurtma qiling`
      )
      return
    }

    setOrderLoading(true)

    try {
      const resolvedPhone = ensurePhoneOrPrompt()
      if (!resolvedPhone) {
        setOrderLoading(false)
        return
      }
      const deliveryAddress = orderType === 'delivery'
        ? (buildDeliveryAddress() || address.trim())
        : null
      const deliveryLat = orderType === 'delivery' ? (deliveryCoords?.lat ?? null) : null
      const deliveryLon = orderType === 'delivery' ? (deliveryCoords?.lon ?? null) : null
      const orderData = {
        items: cartItems.map(item => ({
          offer_id: item.offer.id,
          quantity: item.quantity,
        })),
        delivery_address: deliveryAddress,
        delivery_lat: deliveryLat,
        delivery_lon: deliveryLon,
        phone: resolvedPhone,
        comment: buildOrderComment(),
        order_type: orderType,
        delivery_fee: orderType === 'delivery' ? deliveryFee : 0,
        payment_method: selectedPaymentMethod,
      }

      setStoredPhone(resolvedPhone)

      const result = await api.createOrder(orderData)

      const isSuccess = !!(result?.success || result?.order_id)
      if (!isSuccess) {
        throw new Error(result?.message || result?.error || 'Order failed')
      }

      // Get order ID from response
      const orderId = result.order_id || result.bookings?.[0]?.booking_id

      clearCart()
      setShowCheckout(false)
      setShowPaymentSheet(false)
      setCheckoutStep('details')
      setOrderResult({
        success: true,
        orderId: orderId,
        bookingCode: result.bookings?.[0]?.booking_code,
        orderType: orderType,
        total: total
      })

      // Haptic feedback
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('success')

      window.Telegram?.WebApp?.sendData?.(JSON.stringify({
        action: 'order_placed',
        order_id: orderId,
        total: total,
        order_type: orderType,
      }))

    } catch (error) {
      console.error('Error placing order:', error)
      setOrderResult({ success: false, error: error.message })
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('error')
    } finally {
      setOrderLoading(false)
    }
  }

  // Handle online payment (Click)
  const handleOnlinePayment = async () => {
    if (!isProviderAvailable('click')) {
      toast.error("Click to'lovi vaqtincha mavjud emas. Boshqa to'lov usulini tanlang.")
      return
    }
    if (orderType === 'delivery' && storeDeliveryEnabled && !canDelivery) {
      toast.warning(
        `Yetkazib berish uchun minimum ${formatSum(minOrderAmount)} so'm buyurtma qiling`
      )
      return
    }

    setOrderLoading(true)
    let orderId = null
    try {
      const resolvedPhone = ensurePhoneOrPrompt()
      if (!resolvedPhone) {
        setOrderLoading(false)
        return
      }
      const deliveryAddress = orderType === 'delivery'
        ? (buildDeliveryAddress() || address.trim())
        : null
      const deliveryLat = orderType === 'delivery' ? (deliveryCoords?.lat ?? null) : null
      const deliveryLon = orderType === 'delivery' ? (deliveryCoords?.lon ?? null) : null
      // First create the order
      const orderData = {
        items: cartItems.map(item => ({
          offer_id: item.offer.id,
          quantity: item.quantity,
        })),
        delivery_address: deliveryAddress,
        delivery_lat: deliveryLat,
        delivery_lon: deliveryLon,
        phone: resolvedPhone,
        comment: buildOrderComment(),
        order_type: orderType,
        delivery_fee: orderType === 'delivery' ? deliveryFee : 0,
        payment_method: 'click',
      }

      setStoredPhone(resolvedPhone)
      const result = await api.createOrder(orderData)

      const isSuccess = !!(result?.success || result?.order_id)
      if (!isSuccess) {
        throw new Error(result?.message || result?.error || 'Order failed')
      }

      orderId = result.order_id || result.bookings?.[0]?.booking_id
      const storeId = cartItems[0]?.offer?.store_id || null
      const returnUrl = `${window.location.origin}/order/${orderId}/details`
      const pendingPayload = savePendingPayment({
        orderId,
        storeId,
        total,
        provider: 'click',
        cart: buildCartSnapshot(),
      })
      setPendingPayment(pendingPayload)

      // Create payment link
      const paymentData = await api.createPaymentLink(orderId, 'click', returnUrl, storeId, total)

      if (paymentData.payment_url) {
        clearCart()
        setShowCheckout(false)
        setShowPaymentSheet(false)
        // Open payment
        if (window.Telegram?.WebApp?.openLink) {
          window.Telegram?.WebApp?.openLink?.(paymentData.payment_url)
        } else {
          window.location.href = paymentData.payment_url
        }
      } else {
        throw new Error('Payment URL not received')
      }
    } catch (error) {
      console.error('Online payment error:', error)
      toast.error(`Click to'lovida xatolik: ` + (error.message || 'Noma\'lum xatolik'))
      if (orderId) {
        navigate(`/order/${orderId}`)
      }
    } finally {
      setOrderLoading(false)
    }
  }

  // Empty cart
  if (isEmpty) {
    return (
      <div className="cart-page cart-page--empty">
        <header className="cart-header">
          <div className="cart-header-inner">
            <div className="cart-header-spacer" aria-hidden="true" />
            <h1 className="cart-header-title">Savat</h1>
            <button
              className="cart-header-clear"
              type="button"
              onClick={handleClearCart}
              aria-label="Savatni tozalash"
              disabled
            >
              <Trash2 size={18} strokeWidth={1.8} />
            </button>
          </div>
        </header>

      <main className="cart-empty">
        <div className="cart-empty-content">
          {pendingPaymentCard}
          <div className="empty-card">
            <div className="empty-icon">
              <ShoppingCart size={72} strokeWidth={1.5} color="#0F766E" aria-hidden="true" />
            </div>
            <h2>Savatingiz bo'sh</h2>
            <p className="empty-description">
              Mahsulotlarni ko'rish va savatga qo'shish uchun bosh sahifaga o'ting.
            </p>
            <div className="empty-actions">
              <button className="btn-primary" onClick={() => navigate('/')}>
                <Home size={18} strokeWidth={2} aria-hidden="true" />
                <span>Bosh sahifaga o'tish</span>
              </button>
              <button className="btn-secondary" onClick={() => navigate('/stores')}>
                <Sparkles size={18} strokeWidth={2} aria-hidden="true" />
                <span>Do'konlarni ko'rish</span>
              </button>
            </div>
          </div>
        </div>
      </main>

        <BottomNav currentPage="cart" cartCount={0} />
      </div>
    )
  }

  return (
    <div className="cart-page">
      <header className="cart-header">
        <div className="cart-header-inner">
          <div className="cart-header-spacer" aria-hidden="true" />
          <h1 className="cart-header-title">Savat</h1>
          <button
            className="cart-header-clear"
            type="button"
            onClick={handleClearCart}
            aria-label="Savatni tozalash"
          >
            <Trash2 size={18} strokeWidth={1.8} />
          </button>
        </div>
      </header>

      <main className="cart-main">
        {pendingPaymentCard}
        {hasMultipleStores && (
          <div className="cart-alert" role="status">
            <p>{multiStoreMessage}</p>
            <button type="button" className="cart-alert-action" onClick={handleClearCart}>
              Savatni tozalash
            </button>
          </div>
        )}

        <section className="cart-store-card">
          <div className="cart-store-header">
            <div className="cart-store-title">
              <span className="cart-store-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" role="img" aria-hidden="true">
                  <path
                    d="M3.5 10.5L5 4h14l1.5 6.5"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.6"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                  <path
                    d="M4 10.5h16v8.5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.6"
                    strokeLinejoin="round"
                  />
                  <path
                    d="M9 20v-6h6v6"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.6"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                  <path
                    d="M7 10.5v2M12 10.5v2M17 10.5v2"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.6"
                    strokeLinecap="round"
                  />
                </svg>
              </span>
              <h2 className="cart-store-name">{storeName}</h2>
            </div>
            <ChevronRight size={16} strokeWidth={2} className="cart-store-arrow" aria-hidden="true" />
          </div>
          <div className="cart-store-items">
            {cartItems.map((item) => {
              const photoUrl = resolveOfferImageUrl(item.offer) || PLACEHOLDER_IMAGE
              const rawStockLimit = item.offer.stock ?? item.offer.quantity ?? 99
              const parsedStockLimit = Number(rawStockLimit)
              const stockLimit = Number.isFinite(parsedStockLimit) ? parsedStockLimit : 99
              const maxStock = item.offer.stock ?? item.offer.quantity
              const rawOriginalPrice = item.offer.original_price
              const rawDiscountPrice = item.offer.discount_price
              const parsedOriginalPrice = rawOriginalPrice == null ? NaN : Number(rawOriginalPrice)
              const parsedDiscountPrice = rawDiscountPrice == null ? NaN : Number(rawDiscountPrice)
              const originalPrice = Number.isFinite(parsedOriginalPrice) ? parsedOriginalPrice : null
              const discountPrice = Number.isFinite(parsedDiscountPrice) ? parsedDiscountPrice : null
              const unitPrice = discountPrice ?? originalPrice ?? 0
              const showOriginalPrice = discountPrice != null && originalPrice != null && originalPrice > discountPrice
              const subtitle = item.offer.description || item.offer.short_description || item.offer.store_address || ''
              const availability = getOfferAvailability(item.offer)
              const isUnavailableNow = availability.timeRange && !availability.isAvailableNow
              return (
                <div key={item.offer.id} className={`cart-item-row${isUnavailableNow ? ' is-unavailable' : ''}`}>
                  <div className="cart-item-thumb">
                    <img
                      src={photoUrl}
                      alt={item.offer.title}
                      className="cart-item-image"
                      loading="lazy"
                      decoding="async"
                      onError={(e) => {
                        if (!e.target.dataset.fallback) {
                          e.target.dataset.fallback = 'true'
                          e.target.src = PLACEHOLDER_IMAGE
                        }
                      }}
                    />
                  </div>
                  <div className="cart-item-body">
                    <h3 className="cart-item-title">{item.offer.title}</h3>
                    {subtitle && (
                      <p className="cart-item-subtitle">{subtitle}</p>
                    )}
                    <div className="cart-item-prices">
                      <span className="cart-item-price">
                        {formatSum(unitPrice)} so'm
                      </span>
                      {showOriginalPrice && (
                        <span className="cart-item-price-old">
                          {formatSum(originalPrice)}
                        </span>
                      )}
                    </div>
                    {maxStock != null && item.quantity >= maxStock && (
                      <p className="cart-item-stock-warning">
                        Maksimum: {maxStock} {getUnitLabel(item.offer.unit)}
                      </p>
                    )}
                    {isUnavailableNow && (
                      <p className="cart-item-availability">
                        Hozir yopiq - Buyurtma vaqti: {availability.timeRange}
                      </p>
                    )}
                  </div>
                  <div className="cart-item-qty">
                    <button
                      type="button"
                      onClick={() => handleQuantityChange(item.offer.id, 1)}
                      aria-label={`${item.offer.title} miqdorini oshirish`}
                      disabled={item.quantity >= stockLimit || isUnavailableNow}
                    >
                      <Plus size={20} strokeWidth={2} />
                    </button>
                    <span className="cart-item-qty-value">{item.quantity}</span>
                    <button
                      type="button"
                      onClick={() => handleQuantityChange(item.offer.id, -1)}
                      aria-label={`${item.offer.title} miqdorini kamaytirish`}
                    >
                      <Minus size={20} strokeWidth={2} />
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        </section>

        {storeOffersLoading && (
          <section className="cart-recommendations" aria-hidden="true">
            <h3 className="cart-recommendations-title">Tavsiya etamiz</h3>
            <div className="cart-recommendations-list">
              {Array.from({ length: 3 }).map((_, index) => (
                <div key={index} className="cart-recommendation-card is-skeleton">
                  <div className="cart-recommendation-thumb skeleton-box"></div>
                  <div className="cart-recommendation-line skeleton-box"></div>
                  <div className="cart-recommendation-meta">
                    <div className="cart-recommendation-price skeleton-box"></div>
                    <div className="cart-recommendation-add skeleton-box"></div>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {!storeOffersLoading && recommendedOffers.length > 0 && (
          <section className="cart-recommendations">
            <h3 className="cart-recommendations-title">Tavsiya etamiz</h3>
            <div className="cart-recommendations-list">
              {recommendedOffers.map((offer) => {
                const offerId = offer?.id || offer?.offer_id
                if (!offerId) return null
                const normalizedOffer = offer.id ? offer : { ...offer, id: offerId }
                const photoUrl = resolveOfferImageUrl(offer) || PLACEHOLDER_IMAGE
                const price = Number(offer.discount_price ?? offer.original_price ?? 0)
                return (
                  <article key={offerId} className="cart-recommendation-card">
                    <div className="cart-recommendation-thumb">
                      <img
                        src={photoUrl}
                        alt={offer.title || 'Offer'}
                        loading="lazy"
                        decoding="async"
                        onError={(e) => {
                          if (!e.target.dataset.fallback) {
                            e.target.dataset.fallback = 'true'
                            e.target.src = PLACEHOLDER_IMAGE
                          }
                        }}
                      />
                    </div>
                    <p className="cart-recommendation-title">{offer.title || 'Mahsulot'}</p>
                    <div className="cart-recommendation-meta">
                      <span className="cart-recommendation-price">{formatSum(price)}</span>
                      <button
                        type="button"
                        className="cart-recommendation-add"
                        onClick={() => addToCart(normalizedOffer)}
                        aria-label={`${offer.title || 'Mahsulot'} savatga qo'shish`}
                      >
                        <Plus size={14} strokeWidth={2} />
                      </button>
                    </div>
                  </article>
                )
              })}
            </div>
          </section>
        )}
      </main>

      {!isCheckoutRoute && (
        <div className="cart-summary">
          <div className="cart-summary-card">
            <div className="cart-summary-rows">
              <div className="cart-summary-row">
                <span>Mahsulotlar ({itemsCount})</span>
                <span>{formatSum(originalTotal)} so'm</span>
              </div>
              <div className="cart-summary-row savings">
                <span>Tejamkorlik</span>
                <span>{savingsLabel}</span>
              </div>
              <div className="cart-summary-row total">
                <span>Umumiy</span>
                <span>{formatSum(subtotal)} so'm</span>
              </div>
            </div>
            <button
              className="cart-summary-btn"
              onClick={handleCheckout}
              disabled={hasMultipleStores}
            >
              To'lovga o'tish
            </button>
          </div>
        </div>
      )}

      {!isCheckoutRoute && (
        <BottomNav currentPage="cart" cartCount={itemsCount} />
      )}

      {/* Checkout Modal */}
      {showCheckoutSheet && (
        <div
          className="cart-modal-overlay checkout-overlay"
          onClick={isCheckoutRoute ? undefined : closeCheckout}
        >
          <div className="cart-modal checkout-modal" onClick={e => e.stopPropagation()}>
            <div className="checkout-topbar">
              <h2 className="checkout-title">{checkoutTitle}</h2>
            </div>

            <div className="cart-modal-body checkout-body">
              {/* Step 1: Order Details */}
              {checkoutStep === 'details' && (
                <div className="checkout-layout">
                  <section className="checkout-block">
                    <h3>Buyurtma turi</h3>
                    <div className="order-type-options">
                      <button
                        type="button"
                        className={`order-type-btn ${orderType === 'pickup' ? 'active' : ''}`}
                        onClick={() => {
                          setOrderType('pickup')
                          setOrderTypeTouched(true)
                        }}
                      >
                        <span className="order-type-icon" aria-hidden="true"></span>
                        <span className="order-type-text">O'zi olib ketish</span>
                        <span className="order-type-desc">Do'kondan olib ketasiz</span>
                      </button>
                      <button
                        type="button"
                        className={`order-type-btn ${orderType === 'delivery' ? 'active' : ''}${deliveryOptionDisabled ? ' disabled' : ''}`}
                        onClick={() => {
                          if (deliveryOptionDisabled) return
                          setOrderType('delivery')
                          setOrderTypeTouched(true)
                        }}
                        disabled={deliveryOptionDisabled}
                      >
                        <span className="order-type-icon" aria-hidden="true"></span>
                        <span className="order-type-text">Yetkazib berish</span>
                        <span className="order-type-desc">
                          {storeInfoLoading
                            ? 'Ma\'lumot yuklanmoqda'
                            : (storeDeliveryEnabled ? 'Kuryer orqali' : 'Mavjud emas')}
                        </span>
                      </button>
                    </div>
                  </section>
                  <section className="checkout-block">
                    <div className="checkout-block-header">
                      <h3>Yetkazib berish manzili</h3>
                      <button
                        type="button"
                        className="checkout-block-action"
                        onClick={() => {
                          if (orderType !== 'delivery') return
                          setShowMapEditor((prev) => {
                            const next = !prev
                            if (!next) {
                              setMapSearchOpen(false)
                            }
                            return next
                          })
                        }}
                        disabled={orderType !== 'delivery'}
                      >
                        {showMapEditor ? 'Yopish' : 'Xaritada o\'zgartirish'}
                      </button>
                    </div>
                    <div className={`checkout-address-card${orderType !== 'delivery' ? ' is-disabled' : ''}`}>
                      {showMapEditor && (
                        <div
                          className={`checkout-map${isMapLoading ? ' is-loading' : ''}${isMapResolving ? ' is-resolving' : ''}`}
                          aria-busy={isMapLoading || isMapResolving}
                        >
                          <div ref={checkoutMapRef} className="checkout-map-canvas" aria-hidden="true"></div>
                          {mapEnabled && mapSearchOpen && mapQuery.trim().length > 0 && mapQuery.trim().length < 3 && (
                            <div className="checkout-map-search-hint">
                              Kamida 3 ta belgi kiriting
                            </div>
                          )}
                          {mapEnabled && mapSearchOpen && mapQuery.trim().length >= 3 && (
                            <div
                              className="checkout-map-search-results"
                              onPointerDown={(event) => event.preventDefault()}
                            >
                              {mapSearchLoading && (
                                <div className="checkout-map-search-skeleton" aria-hidden="true">
                                  {Array.from({ length: 3 }).map((_, index) => (
                                    <div key={index} className="checkout-map-search-item skeleton"></div>
                                  ))}
                                </div>
                              )}
                              {mapSearchResults.length === 0 && !mapSearchLoading && (
                                <button
                                  type="button"
                                  className="checkout-map-search-item empty"
                                  disabled
                                >
                                  Manzil topilmadi
                                </button>
                              )}
                              {mapSearchResults.map((result) => (
                                <button
                                  key={`${result.place_id}-${result.lat}-${result.lon}`}
                                  type="button"
                                  className="checkout-map-search-item"
                                  onClick={() => handleMapResultSelect(result)}
                                >
                                  {result.display_name}
                                </button>
                              ))}
                            </div>
                          )}
                          <button
                            type="button"
                            className="checkout-map-locate"
                            onClick={handleLocateMe}
                            disabled={!mapEnabled}
                            aria-label="Mening joylashuvim"
                          >
                            <LocateFixed size={16} strokeWidth={2} />
                          </button>
                          {mapEnabled && !mapLoaded && !mapError && (
                            <div className="checkout-map-status">
                              Xarita yuklanmoqda...
                            </div>
                          )}
                          {mapEnabled && mapResolving && (
                            <div className="checkout-map-status">
                              Manzil aniqlanmoqda...
                            </div>
                          )}
                          {mapEnabled && mapError && (
                            <div className="checkout-map-status error">
                              {mapError}
                            </div>
                          )}
                        </div>
                      )}
                      <div className="checkout-address-body">
                        <input
                          ref={addressInputRef}
                          className="checkout-address-title"
                          placeholder="Manzilni kiriting"
                          value={address}
                          onChange={(event) => {
                            const nextValue = event.target.value
                            setAddress(nextValue)
                            setMapQuery(nextValue)
                            if (!mapSearchOpen) {
                              setMapSearchOpen(true)
                            }
                          }}
                          onFocus={() => {
                            if (mapSearchCloseTimeoutRef.current) {
                              clearTimeout(mapSearchCloseTimeoutRef.current)
                              mapSearchCloseTimeoutRef.current = null
                            }
                            mapUserEditingRef.current = true
                            setMapSearchOpen(true)
                          }}
                          onBlur={() => {
                            if (mapSearchCloseTimeoutRef.current) {
                              clearTimeout(mapSearchCloseTimeoutRef.current)
                            }
                            mapSearchCloseTimeoutRef.current = setTimeout(() => {
                              setMapSearchOpen(false)
                            }, 180)
                            mapUserEditingRef.current = false
                          }}
                          onKeyDown={blurOnEnter}
                          disabled={orderType !== 'delivery'}
                        />
                        <div className="checkout-address-meta">
                          <label className="checkout-address-col">
                            <span>Kiraverish</span>
                            <input
                              className="checkout-meta-input"
                              placeholder="-"
                              value={entrance}
                              onChange={e => updateAddressMeta('entrance', e.target.value)}
                              disabled={orderType !== 'delivery'}
                            />
                          </label>
                          <label className="checkout-address-col">
                            <span>Qavat</span>
                            <input
                              className="checkout-meta-input"
                              inputMode="numeric"
                              placeholder="-"
                              value={floor}
                              onChange={e => updateAddressMeta('floor', e.target.value)}
                              disabled={orderType !== 'delivery'}
                            />
                          </label>
                          <label className="checkout-address-col">
                            <span>Xonadon</span>
                            <input
                              className="checkout-meta-input"
                              inputMode="numeric"
                              placeholder="-"
                              value={apartment}
                              onChange={e => updateAddressMeta('apartment', e.target.value)}
                              disabled={orderType !== 'delivery'}
                            />
                          </label>
                        </div>
                      </div>
                    </div>

                    {orderType === 'delivery' && deliveryStatus && (
                      <div className={`checkout-delivery-result ${deliveryStatus.status || ''}`}>
                        <div className="checkout-delivery-result-row">
                          <span className={`checkout-delivery-badge ${deliveryStatus.status || ''}`}>
                            {deliveryStatus.label}
                          </span>
                        </div>

                        {deliveryStatus.message && deliveryStatus.message !== deliveryStatus.label && (
                          <div className="checkout-delivery-message">{deliveryStatus.message}</div>
                        )}

                        {storeDeliveryEnabled && (deliverySummaryCost != null || deliverySummaryMin != null || deliverySummaryEta) && (
                          <div className="checkout-delivery-meta">
                            {deliverySummaryCost != null && (
                              <div className="checkout-delivery-result-row">
                                <span>Narx</span>
                                <strong>{formatSum(deliverySummaryCost)} so'm</strong>
                              </div>
                            )}
                            {deliverySummaryMin != null && deliverySummaryMin > 0 && (
                              <div className="checkout-delivery-result-row">
                                <span>Minimal buyurtma</span>
                                <strong>{formatSum(deliverySummaryMin)} so'm</strong>
                              </div>
                            )}
                            {deliverySummaryEta && (
                              <div className="checkout-delivery-result-row">
                                <span>Vaqt</span>
                                <strong>{deliverySummaryEta}</strong>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )}

                    <input
                      className="checkout-input"
                      placeholder="Kuryer uchun izoh (masalan: domofon ishlamayapti)"
                      value={comment}
                      onChange={e => setComment(e.target.value)}
                      onKeyDown={blurOnEnter}
                      ref={commentInputRef}
                    />
                    {!canonicalPhone && (
                      <input
                        className="checkout-input"
                        type="tel"
                        placeholder="+998 90 123 45 67"
                        value={phone}
                        onChange={e => setPhone(e.target.value)}
                      />
                    )}
                  </section>

                  {orderType === 'delivery' && (
                    <section className="checkout-block">
                      <h3>Yetkazib berish vaqti</h3>
                      <div className="checkout-time-scroll">
                          {deliveryOptions.map(option => (
                            <button
                              key={option.id}
                              type="button"
                              className={`checkout-time-card ${deliverySlot === option.id ? 'active' : ''}`}
                              onClick={() => {
                                if (option.disabled) return
                                setDeliverySlot(option.id)
                              }}
                              disabled={option.disabled}
                            >
                              <span className="checkout-time-label">{option.label}</span>
                              <span className="checkout-time-value">{option.time}</span>
                            </button>
                          ))}
                      </div>
                    </section>
                  )}

                  <section className="checkout-block">
                    <h3>To'lov turi</h3>
                    <div className="checkout-payment-list">
                      {paymentOptions.map(option => {
                        const isActive = selectedPaymentMethod === option.id
                        return (
                          <button
                            key={option.id}
                            type="button"
                            className={`checkout-payment-option${isActive ? ' active' : ''}${option.disabled ? ' disabled' : ''}`}
                            onClick={() => {
                              if (option.disabled) return
                              selectPaymentMethod(option.id)
                            }}
                            disabled={option.disabled}
                          >
                            <div className="checkout-payment-info">
                              <div className={`checkout-payment-icon checkout-payment-icon--${option.id}`}>
                                <span>{paymentIconLabels[option.id] || option.label}</span>
                              </div>
                              <span className="checkout-payment-label">{option.label}</span>
                            </div>
                            <span className={`checkout-payment-radio${isActive ? ' active' : ''}`} aria-hidden="true"></span>
                          </button>
                        )
                      })}
                    </div>
                    {orderType === 'delivery' && deliveryRequiresPrepay && !hasPrepayProviders && (
                      <p className="checkout-hint">
                        Yetkazib berish uchun to'lov usullari mavjud emas
                      </p>
                    )}
                  </section>

                  <section className="checkout-block checkout-block--last">
                    <div className="checkout-order-header">
                      <h3>Sizning buyurtmangiz</h3>
                      <button
                        type="button"
                        className="checkout-order-toggle"
                        onClick={() => setOrderItemsExpanded(prev => !prev)}
                        aria-expanded={orderItemsExpanded}
                        aria-label="Sizning buyurtmangiz"
                      >
                        <span>{itemsCount} dona</span>
                        <ChevronRight
                          size={16}
                          strokeWidth={2}
                          className={`checkout-order-toggle-icon${orderItemsExpanded ? ' is-open' : ''}`}
                          aria-hidden="true"
                        />
                      </button>
                    </div>
                    {orderItemsExpanded && (
                      <div className="checkout-order-items">
                        {cartItems.map(item => {
                          const photoUrl = resolveOfferImageUrl(item.offer) || PLACEHOLDER_IMAGE
                          const rawOriginalPrice = item.offer.original_price
                          const rawDiscountPrice = item.offer.discount_price
                          const parsedOriginalPrice = rawOriginalPrice == null ? NaN : Number(rawOriginalPrice)
                          const parsedDiscountPrice = rawDiscountPrice == null ? NaN : Number(rawDiscountPrice)
                          const originalPrice = Number.isFinite(parsedOriginalPrice) ? parsedOriginalPrice : null
                          const discountPrice = Number.isFinite(parsedDiscountPrice) ? parsedDiscountPrice : null
                          const unitPrice = discountPrice ?? originalPrice ?? 0
                          const lineTotal = unitPrice * item.quantity
                          return (
                            <div key={item.offer.id} className="checkout-order-item">
                              <div className="checkout-order-info">
                                <img
                                  src={photoUrl}
                                  alt={item.offer.title}
                                  loading="lazy"
                                  decoding="async"
                                />
                                <div>
                                  <p className="checkout-order-title">{item.offer.title}</p>
                                  <p className="checkout-order-qty">{item.quantity} dona</p>
                                </div>
                              </div>
                              <span className="checkout-order-price">{formatSum(lineTotal)} so'm</span>
                            </div>
                          )
                        })}
                      </div>
                    )}
                    <div className="checkout-summary">
                      <div className="checkout-summary-row">
                        <span>Mahsulotlar</span>
                        <span>{formatSum(subtotal)} so'm</span>
                      </div>
                      {orderType === 'delivery' && (
                        <div className="checkout-summary-row">
                          <span>Yetkazib berish</span>
                          <span>{formatSum(deliveryFee)} so'm</span>
                        </div>
                      )}
                      <div className="checkout-summary-row">
                        <span>Xizmat haqi</span>
                        <span>{formatSum(serviceFee)} so'm</span>
                      </div>
                      <div className="checkout-summary-row total">
                        <span>Jami</span>
                        <span>{formatSum(checkoutTotal)} so'm</span>
                      </div>
                    </div>
                    {hasUnavailableItems && (
                      <p className="checkout-hint">
                        Hozir buyurtma qilish mumkin emas{unavailableTimeRange ? ` - ${unavailableTimeRange}` : ''}
                      </p>
                    )}
                  </section>
                </div>
              )}

            </div>

            {checkoutStep === 'details' && (
              <div className="checkout-footer">
                <button
                  className={`checkout-confirm${checkoutBusy ? ' is-loading' : ''}`}
                  onClick={proceedToPayment}
                  disabled={checkoutBusy || hasUnavailableItems || !getResolvedPhone() || (orderType === 'delivery' && !address.trim())}
                >
                  {checkoutBusy && <span className="checkout-confirm-spinner" aria-hidden="true"></span>}
                  <span>{checkoutButtonLabel}</span>
                  {!checkoutBusy && (
                    <span className="checkout-confirm-total">{formatSum(checkoutTotal)} so'm</span>
                  )}
                </button>
              </div>
            )}

          </div>
        </div>
      )}

      {/* Result Modal */}
      {orderResult && (
        <div className="cart-modal-overlay" onClick={() => setOrderResult(null)}>
          <div className="cart-modal result-modal" onClick={e => e.stopPropagation()}>
            {orderResult.success ? (
              <>
                <div className="result-icon success">OK</div>
                <h2>{orderResult.message || 'Buyurtma qabul qilindi!'}</h2>

                {orderResult.bookingCode && (
                  <p className="booking-code-display">
                    Kod: <strong>{orderResult.bookingCode}</strong>
                  </p>
                )}
                <p className="order-type-result">
                  {orderResult.orderType === 'pickup'
                    ? 'O\'zi olib ketish'
                    : 'Yetkazib berish'
                  }
                </p>
                <p className="order-total-result">
                  Jami: {Math.round(orderResult.total).toLocaleString()} so'm
                </p>

                <button className="btn-primary" onClick={() => {
                  setOrderResult(null)
                  navigate('/')
                }}>
                  Bosh sahifaga
                </button>
              </>
            ) : (
              <>
                <div className="result-icon error">ERR</div>
                <h2>Xatolik yuz berdi</h2>
                <p>{orderResult.error || 'Iltimos, qaytadan urinib ko\'ring'}</p>
                <button className="btn-primary" onClick={() => setOrderResult(null)}>
                  Yopish
                </button>
              </>
            )}
          </div>
        </div>
      )}

      {/* Payment Methods Sheet */}
      {showPaymentSheet && (
        <div className="cart-modal-overlay cart-payment-sheet-overlay" onClick={() => setShowPaymentSheet(false)}>
          <div className="cart-modal cart-payment-sheet" onClick={e => e.stopPropagation()}>
            <div className="sheet-handle"></div>
            <div className="cart-payment-sheet-header">
              <h3>To'lov usullari</h3>
              <button className="cart-modal-close" onClick={() => setShowPaymentSheet(false)}>x</button>
            </div>
            <div className="cart-payment-sheet-list">
              <button
                className={`cart-payment-sheet-item ${selectedPaymentMethod === 'cash' ? 'active' : ''} ${deliveryRequiresPrepay ? 'disabled' : ''}`}
                onClick={() => {
                  if (deliveryRequiresPrepay) return
                  selectPaymentMethod('cash')
                  setShowPaymentSheet(false)
                }}
                disabled={deliveryRequiresPrepay}
              >
                <span className="cart-payment-sheet-label">Naqd</span>
                <span className="cart-payment-sheet-radio" aria-hidden="true"></span>
              </button>
              <button
                className={`cart-payment-sheet-item ${selectedPaymentMethod === 'click' ? 'active' : ''} ${!isProviderAvailable('click') ? 'disabled' : ''}`}
                onClick={() => {
                  if (!isProviderAvailable('click')) return
                  selectPaymentMethod('click')
                  setShowPaymentSheet(false)
                }}
                disabled={!isProviderAvailable('click')}
              >
                <span className="cart-payment-sheet-label">Click</span>
                <span className="cart-payment-sheet-radio" aria-hidden="true"></span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default CartPage


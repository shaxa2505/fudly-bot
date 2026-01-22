import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { ShoppingCart, Home, Sparkles, ChevronRight, Trash2, Plus, Minus, Search, LocateFixed } from 'lucide-react'
import api from '../api/client'
import { useCart } from '../context/CartContext'
import { useToast } from '../context/ToastContext'
import { getUnitLabel, blurOnEnter, isValidPhone } from '../utils/helpers'
import { getCurrentUser } from '../utils/auth'
import { PLACEHOLDER_IMAGE, resolveOfferImageUrl } from '../utils/imageUtils'
import { buildLocationFromReverseGeocode, saveLocation } from '../utils/cityUtils'
import { getCurrentLocation } from '../utils/geolocation'
import BottomNav from '../components/BottomNav'
import './CartPage.css'

const LEAFLET_CDN = 'https://unpkg.com/leaflet@1.9.4/dist'
const DEFAULT_MAP_CENTER = { lat: 41.2995, lon: 69.2401 }
const AUTO_DELIVERY_THRESHOLD = 30000

function CartPage({ user }) {
  const navigate = useNavigate()
  const { toast } = useToast()
  // Use cart from context
  const {
    cartItems,
    cartCount,
    cartTotal,
    isEmpty,
    addToCart,
    updateQuantity,
    removeItem,
    clearCart
  } = useCart()

  const botUsername = import.meta.env.VITE_BOT_USERNAME || 'fudlyuzbot'
  const cachedUser = getCurrentUser()
  const canonicalPhone = (user?.phone || cachedUser?.phone || '').toString().trim()

  const [orderLoading, setOrderLoading] = useState(false)
  const addressInputRef = useRef(null)
  const commentInputRef = useRef(null)
  const paymentProofInputRef = useRef(null)
  const fileSelectHandlerRef = useRef(null)

  // Checkout form
  const [showCheckout, setShowCheckout] = useState(false)
  const [phone, setPhone] = useState(() => canonicalPhone || localStorage.getItem('fudly_phone') || '')
  const [address, setAddress] = useState(() => {
    try {
      const loc = JSON.parse(localStorage.getItem('fudly_location') || '{}')
      return loc.address || ''
    } catch { return '' }
  })
  const [comment, setComment] = useState('')

  // Delivery type: 'pickup' or 'delivery'
  const [orderType, setOrderType] = useState('pickup')
  const [orderTypeTouched, setOrderTypeTouched] = useState(false)
  const [deliveryFee, setDeliveryFee] = useState(0)
  const [minOrderAmount, setMinOrderAmount] = useState(0)
  const [storeDeliveryEnabled, setStoreDeliveryEnabled] = useState(false)

  // Payment step for delivery
  const [checkoutStep, setCheckoutStep] = useState('details') // 'details' | 'payment'
  const [paymentCard, setPaymentCard] = useState(null)
  const [paymentProof, setPaymentProof] = useState(null)
  const [paymentProofData, setPaymentProofData] = useState(null)
  const [paymentProofPreview, setPaymentProofPreview] = useState(null)
  const [createdOrderId, setCreatedOrderId] = useState(null)
  const [paymentProviders, setPaymentProviders] = useState([])
  const [selectedPaymentMethod, setSelectedPaymentMethod] = useState('cash') // 'cash' | 'card' | 'click' | 'payme'
  const [showPaymentSheet, setShowPaymentSheet] = useState(false)
  const [deliverySlot, setDeliverySlot] = useState('fast')
  const [addressMeta, setAddressMeta] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem('fudly_address_meta') || '{}')
    } catch {
      return {}
    }
  })
  const [storeOffers, setStoreOffers] = useState([])
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

    if (mapResolveFailSafeRef.current) {
      clearTimeout(mapResolveFailSafeRef.current)
    }
    mapResolveFailSafeRef.current = setTimeout(() => {
      if (mapResolveSeqRef.current === requestId) {
        setMapResolving(false)
      }
    }, 8000)

    const fetchApi = async () => {
      try {
        return await api.reverseGeocode(lat, lon, 'uz')
      } catch (error) {
        console.error('Reverse geocode error:', error)
        return null
      }
    }

    let resolved = null

    try {
      const apiData = await fetchApi()
      if (apiData) {
        resolved = buildLocationFromReverseGeocode(apiData, lat, lon)
      }
    } catch (error) {
      console.warn('API reverse error:', error)
    }

    if (!resolved?.address) {
      try {
        const params = new URLSearchParams({
          format: 'jsonv2',
          lat: String(lat),
          lon: String(lon),
          zoom: '18',
          addressdetails: '1',
          'accept-language': 'uz',
        })
        const response = await fetch(`https://nominatim.openstreetmap.org/reverse?${params}`)
        if (response.ok) {
          const nominatimData = await response.json()
          if (nominatimData) {
            resolved = buildLocationFromReverseGeocode(nominatimData, lat, lon)
          }
        }
      } catch (error) {
        console.warn('Nominatim reverse error:', error)
      }
    }

    if (requestId !== mapResolveSeqRef.current) {
      return
    }

    if (resolved?.address) {
      setAddress(resolved.address)
      if (!mapUserEditingRef.current || force) {
        setMapQuery(resolved.address)
      }
      saveLocation(resolved)
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

  const mapEnabled = showCheckout && orderType === 'delivery'

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
    const controller = new AbortController()
    const timeout = setTimeout(async () => {
      setMapSearchLoading(true)
      try {
        const params = new URLSearchParams({
          format: 'jsonv2',
          q: query,
          limit: '6',
          addressdetails: '1',
          'accept-language': 'uz',
        })
        const response = await fetch(`https://nominatim.openstreetmap.org/search?${params}`, {
          signal: controller.signal,
          headers: { 'Accept-Language': 'uz' },
        })
        if (!response.ok) {
          throw new Error('Search failed')
        }
        const data = await response.json()
        if (!isActive) return
        setMapSearchResults(Array.isArray(data) ? data : [])
      } catch (error) {
        if (error.name !== 'AbortError') {
          console.warn('Map search error:', error)
        }
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
      controller.abort()
    }
  }, [mapEnabled, mapQuery, mapSearchOpen])

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

    const L = window.L
    if (!L) return

    const savedCoords = getSavedCoordinates()
    const startLat = savedCoords?.lat ?? DEFAULT_MAP_CENTER.lat
    const startLon = savedCoords?.lon ?? DEFAULT_MAP_CENTER.lon
    const startZoom = savedCoords ? 16 : 12

    const map = L.map(checkoutMapRef.current, {
      center: [startLat, startLon],
      zoom: startZoom,
      zoomControl: false,
      attributionControl: false,
      tap: false,
    })

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
    }).addTo(map)

    checkoutMapInstanceRef.current = map

    const markerIcon = L.divIcon({
      className: 'checkout-map-marker',
      html: '<span></span>',
      iconSize: [36, 36],
      iconAnchor: [18, 34],
    })
    const marker = L.marker([startLat, startLon], {
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
  }, [mapEnabled, showCheckout])

  const handleMapResultSelect = (result) => {
    const lat = Number(result?.lat)
    const lon = Number(result?.lon)
    const label = result?.display_name || ''
    if (label) {
      setAddress(label)
      setMapQuery(label)
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

  // Load payment providers
  useEffect(() => {
    const loadProviders = async () => {
      try {
        const providers = await api.getPaymentProviders()
        setPaymentProviders(providers)
      } catch (e) {
        console.warn('Could not load payment providers:', e)
      }
    }
    loadProviders()
  }, [])

  // Keep phone in sync with server profile (bot registration is the single source)
  useEffect(() => {
    if (canonicalPhone && canonicalPhone !== phone) {
      setPhone(canonicalPhone)
      localStorage.setItem('fudly_phone', canonicalPhone)
    }
  }, [canonicalPhone, phone])

  const { entrance = '', floor = '', apartment = '' } = addressMeta

  useEffect(() => {
    localStorage.setItem('fudly_address_meta', JSON.stringify(addressMeta))
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
  // Check if stores in cart support delivery
  useEffect(() => {
    let isActive = true
    const checkDeliveryAvailability = async () => {
      if (!cartStoreId) {
        setStoreDeliveryEnabled(false)
        setDeliveryFee(0)
        setMinOrderAmount(0)
        return
      }

      try {
        const cartStore = await api.getStore(cartStoreId)

        if (cartStore && isActive) {
          setStoreDeliveryEnabled(!!cartStore.delivery_enabled)
          setDeliveryFee(cartStore.delivery_price || 0)
          setMinOrderAmount(cartStore.min_order_amount || 0)
        }
      } catch (e) {
        console.warn('Could not fetch store info:', e)
        if (isActive) {
          setStoreDeliveryEnabled(false)
          setDeliveryFee(0)
          setMinOrderAmount(0)
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
        return
      }
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
      }
    }

    loadStoreOffers()
    return () => {
      isActive = false
    }
  }, [cartStoreId])

  // Calculate totals using context values
  const subtotal = cartTotal
  const total = orderType === 'delivery' ? subtotal + deliveryFee : subtotal
  const serviceFee = 0
  const checkoutTotal = total + serviceFee
  const itemsCount = cartCount
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
  const originalTotal = subtotal + savingsTotal
  const savingsLabel = savingsTotal > 0 ? `-${formatSum(savingsTotal)} so'm` : `0 so'm`
  const deliveryOptions = [
    { id: 'fast', label: 'Tezda', time: '25-35 daqiqa' },
    { id: 'slot-1', label: 'Bugun', time: '18:00 - 18:30' },
    { id: 'slot-2', label: 'Bugun', time: '19:00 - 19:30' },
  ]
  const deliverySlotLabel = deliveryOptions.find(option => option.id === deliverySlot)?.time || ''
  const autoOrderType = useMemo(() => {
    if (!storeDeliveryEnabled) return 'pickup'
    return subtotal >= AUTO_DELIVERY_THRESHOLD ? 'delivery' : 'pickup'
  }, [storeDeliveryEnabled, subtotal])
  const deliveryOptionDisabled = !storeDeliveryEnabled || subtotal < AUTO_DELIVERY_THRESHOLD

  // Check if minimum order met for delivery
  const canDelivery = subtotal >= minOrderAmount
  const paymentMethodLabels = {
    cash: 'Naqd',
    card: 'Kartaga o\'tkazish',
    click: 'Click',
    payme: 'Payme',
  }
  const isProviderAvailable = (provider) => paymentProviders.includes(provider)
  const hasOnlineProviders = paymentProviders.includes('click') || paymentProviders.includes('payme')
  const hasCardProvider = paymentProviders.includes('card')
  const hasPrepayProviders = hasOnlineProviders || hasCardProvider
  const deliveryRequiresPrepay = orderType === 'delivery'
  const checkoutTitle = checkoutStep === 'payment' ? "To'lov" : "Buyurtmani rasmiylashtirish"
  const cardSuffix = paymentCard?.card_number ? paymentCard.card_number.slice(-4) : ''
  const paymentOptions = [
    {
      id: 'card',
      label: cardSuffix ? `Uzcard **** ${cardSuffix}` : 'Uzcard',
      icon: 'card',
      disabled: !isProviderAvailable('card'),
    },
    {
      id: 'click',
      label: 'Click',
      icon: 'click',
      disabled: !isProviderAvailable('click'),
    },
    {
      id: 'payme',
      label: 'Payme',
      icon: 'payme',
      disabled: !isProviderAvailable('payme'),
    },
    {
      id: 'cash',
      label: 'Naqd pul',
      icon: 'cash',
      disabled: deliveryRequiresPrepay,
    },
  ]
  const paymentIconLabels = {
    card: 'UZ',
    click: 'Click',
    payme: 'Pay',
    cash: 'Naqd',
  }

  useEffect(() => {
    if (!deliveryRequiresPrepay) return
    if (selectedPaymentMethod !== 'cash') return
    if (hasOnlineProviders) {
      const preferred = paymentProviders.includes('click') ? 'click' : 'payme'
      setSelectedPaymentMethod(preferred)
      return
    }
    if (hasCardProvider) {
      setSelectedPaymentMethod('card')
    }
  }, [deliveryRequiresPrepay, hasOnlineProviders, hasCardProvider, paymentProviders, selectedPaymentMethod])

  useEffect(() => {
    if (!storeDeliveryEnabled && orderType === 'delivery') {
      setOrderType('pickup')
      setOrderTypeTouched(false)
      return
    }
    if (orderTypeTouched) return
    if (orderType !== autoOrderType) {
      setOrderType(autoOrderType)
    }
  }, [autoOrderType, orderType, orderTypeTouched, storeDeliveryEnabled])

  const clearPaymentProof = () => {
    setPaymentProof(null)
    setPaymentProofData(null)
    setPaymentProofPreview(null)
    if (paymentProofInputRef.current) {
      paymentProofInputRef.current.value = ''
    }
    document.documentElement.classList.remove('file-picker-open')
  }

  const selectPaymentMethod = (method) => {
    setSelectedPaymentMethod(method)
    if (method !== 'card') {
      clearPaymentProof()
    }
  }

  const closeCheckout = () => {
    if (orderLoading) return
    setShowCheckout(false)
    setShowPaymentSheet(false)
    setOrderTypeTouched(false)
    setMapSearchOpen(false)
  }

  // Open the file picker synchronously on user click (iOS Safari safe).
  const openPaymentProofPicker = () => {
    if (orderLoading) return
    const input = paymentProofInputRef.current
    if (!input) return
    input.value = ''
    document.documentElement.classList.add('file-picker-open')
    input.click()
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
      localStorage.setItem('fudly_user', JSON.stringify(mergedUser))
      localStorage.setItem('fudly_phone', profilePhone)
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
          window.open(url, '_blank')
        }
      }
      return ''
    }
    return verifiedPhone
  }

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
    setMapSearchOpen(false)
    setCheckoutStep('details')
    setShowCheckout(true)
  }

  // Handle file selection for payment proof
  const handleFileSelect = useCallback((event) => {
    const file = event.target?.files?.[0]
    if (!file) return
    setPaymentProof(file)
    const reader = new FileReader()
    reader.onloadend = () => {
      setPaymentProofPreview(reader.result)
      setPaymentProofData(reader.result)
    }
    reader.readAsDataURL(file)
  }, [])

  useEffect(() => {
    fileSelectHandlerRef.current = handleFileSelect
  }, [handleFileSelect])

  useEffect(() => {
    if (paymentProofInputRef.current) return
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'image/*,image/jpeg,image/jpg,image/png'
    input.style.position = 'fixed'
    input.style.top = '-1000px'
    input.style.left = '0'
    input.style.width = '1px'
    input.style.height = '1px'
    input.style.opacity = '0'
    input.style.pointerEvents = 'none'
    input.setAttribute('aria-hidden', 'true')

    const handleChange = (event) => {
      document.documentElement.classList.remove('file-picker-open')
      fileSelectHandlerRef.current?.(event)
    }
    const handleWindowFocus = () => {
      document.documentElement.classList.remove('file-picker-open')
    }

    input.addEventListener('change', handleChange)
    window.addEventListener('focus', handleWindowFocus)
    document.body.appendChild(input)
    paymentProofInputRef.current = input

    return () => {
      input.removeEventListener('change', handleChange)
      window.removeEventListener('focus', handleWindowFocus)
      input.remove()
      if (paymentProofInputRef.current === input) {
        paymentProofInputRef.current = null
      }
      document.documentElement.classList.remove('file-picker-open')
    }
  }, [])

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
          window.open(url, '_blank')
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

  const buildOrderComment = useCallback(() => {
    const lines = [orderType === 'pickup' ? "O'zi olib ketadi" : 'Yetkazib berish']
    if (orderType === 'delivery') {
      if (entrance.trim()) lines.push(`Kiraverish: ${entrance.trim()}`)
      if (floor.trim()) lines.push(`Qavat: ${floor.trim()}`)
      if (apartment.trim()) lines.push(`Xonadon: ${apartment.trim()}`)
      if (deliverySlotLabel) lines.push(`Yetkazish vaqti: ${deliverySlotLabel}`)
    }
    if (comment.trim()) lines.push(comment.trim())
    return lines.join('\n').trim()
  }, [orderType, entrance, floor, apartment, deliverySlotLabel, comment])

  // Proceed to payment step (for delivery)
  const proceedToPayment = async () => {
    const resolvedPhone = ensurePhoneOrPrompt()
    if (!resolvedPhone) {
      return
    }
    if (orderType === 'delivery' && !address.trim()) {
      toast.warning('Yetkazib berish manzilini kiriting')
      return
    }
    if (deliveryRequiresPrepay && !hasPrepayProviders) {
      toast.error('Yetkazib berish uchun to\'lov usullari mavjud emas')
      return
    }

    if (['click', 'payme'].includes(selectedPaymentMethod)) {
      await handleOnlinePayment(selectedPaymentMethod)
      return
    }

    if (selectedPaymentMethod === 'cash') {
      await placeOrder()
      return
    }

    // If card transfer - fetch payment card and show payment step
    setOrderLoading(true)
    try {
      const storeId = cartItems[0]?.offer?.store_id || 0
      const cardData = await api.getPaymentCard(storeId)
      setPaymentCard(cardData)
      setCheckoutStep('payment')
    } catch (error) {
      console.error('Error fetching payment card:', error)
      toast.error('To\'lov rekvizitlarini olishda xatolik')
    } finally {
      setOrderLoading(false)
    }
  }

  // Place order (for pickup or after payment upload)
  const placeOrder = async () => {
    if (isEmpty) return

    setOrderLoading(true)

    try {
      const resolvedPhone = ensurePhoneOrPrompt()
      if (!resolvedPhone) {
        setOrderLoading(false)
        return
      }
      const orderData = {
        items: cartItems.map(item => ({
          offer_id: item.offer.id,
          quantity: item.quantity,
        })),
        delivery_address: orderType === 'delivery' ? address.trim() : null,
        phone: resolvedPhone,
        comment: buildOrderComment(),
        order_type: orderType,
        delivery_fee: orderType === 'delivery' ? deliveryFee : 0,
        payment_method: selectedPaymentMethod,
      }

      localStorage.setItem('fudly_phone', resolvedPhone)

      const result = await api.createOrder(orderData)

      const isSuccess = !!(result?.success || result?.order_id)
      if (!isSuccess) {
        throw new Error(result?.message || result?.error || 'Order failed')
      }

      // Get order ID from response
      const orderId = result.order_id || result.bookings?.[0]?.booking_id
      setCreatedOrderId(orderId)

      let paymentProofUploaded = false
      if (selectedPaymentMethod === 'card' && paymentProof && orderId) {
        try {
          await api.uploadPaymentProof(orderId, paymentProof)
          paymentProofUploaded = true
        } catch (e) {
          console.warn('Could not upload payment proof:', e)
        }
      }

      // Check if payment proof required (delivery + card)
      if (result.awaiting_payment && orderId) {
        clearCart()
        setShowCheckout(false)
        setShowPaymentSheet(false)
        setCheckoutStep('details')
        setPaymentCard(result.payment_card || null)
        setCreatedOrderId(orderId)
        setOrderResult({
          success: true,
          orderId: orderId,
          awaitingPayment: !paymentProofUploaded,
          orderType: orderType,
          total: total,
          paymentCard: result.payment_card,
          message: paymentProofUploaded
            ? 'Chek yuborildi! Admin tekshiradi.'
            : result.message || 'Buyurtma yaratildi! To\'lovni amalga oshiring.'
        })
        return
      }

      clearCart()
      setShowCheckout(false)
      setShowPaymentSheet(false)
      setCheckoutStep('details')
      clearPaymentProof()
      setPaymentCard(null)
      setOrderResult({
        success: true,
        orderId: orderId,
        bookingCode: result.bookings?.[0]?.booking_code,
        orderType: orderType,
        total: total
      })

      // Haptic feedback
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('success')

      if (window.Telegram?.WebApp) {
        window.Telegram.WebApp.sendData(JSON.stringify({
          action: 'order_placed',
          order_id: orderId,
          total: total,
          order_type: orderType,
        }))
      }

    } catch (error) {
      console.error('Error placing order:', error)
      setOrderResult({ success: false, error: error.message })
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('error')
    } finally {
      setOrderLoading(false)
    }
  }

  // Handle online payment (Click/Payme)
  const handleOnlinePayment = async (provider) => {
    if (!isProviderAvailable(provider)) {
      const providerLabel = paymentMethodLabels[provider] || provider
      toast.error(`${providerLabel} to\'lov vaqtincha mavjud emas. Boshqa to\'lov usulini tanlang.`)
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
      // First create the order
      const orderData = {
        items: cartItems.map(item => ({
          offer_id: item.offer.id,
          quantity: item.quantity,
        })),
        delivery_address: orderType === 'delivery' ? address.trim() : null,
        phone: resolvedPhone,
        comment: buildOrderComment(),
        order_type: orderType,
        delivery_fee: orderType === 'delivery' ? deliveryFee : 0,
        payment_method: provider,
      }

      localStorage.setItem('fudly_phone', resolvedPhone)
      const result = await api.createOrder(orderData)

      const isSuccess = !!(result?.success || result?.order_id)
      if (!isSuccess) {
        throw new Error(result?.message || result?.error || 'Order failed')
      }

      orderId = result.order_id || result.bookings?.[0]?.booking_id
      setCreatedOrderId(orderId)
      const storeId = cartItems[0]?.offer?.store_id || null
      const returnUrl = window.location.origin + '/profile'

      // Create payment link
      const paymentData = await api.createPaymentLink(orderId, provider, returnUrl, storeId, total)

      if (paymentData.payment_url) {
        clearCart()
        setShowCheckout(false)
        setShowPaymentSheet(false)
        // Open payment
        if (window.Telegram?.WebApp) {
          window.Telegram.WebApp.openLink(paymentData.payment_url)
        } else {
          window.location.href = paymentData.payment_url
        }
      } else {
        throw new Error('Payment URL not received')
      }
    } catch (error) {
      console.error('Online payment error:', error)
      const providerLabel = paymentMethodLabels[provider] || provider
      toast.error(`${providerLabel} to\'lovda xatolik: ` + (error.message || 'Noma\'lum xatolik'))
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
            <div className="cart-header-center">
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
          </div>
        </header>

        <main className="cart-empty">
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
        </main>

        <BottomNav currentPage="cart" cartCount={0} />
      </div>
    )
  }

  return (
    <div className="cart-page">
      <header className="cart-header">
        <div className="cart-header-inner">
          <div className="cart-header-center">
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
        </div>
      </header>

      <main className="cart-main">
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
              return (
                <div key={item.offer.id} className="cart-item-row">
                  <div className="cart-item-thumb">
                    <img
                      src={photoUrl}
                      alt={item.offer.title}
                      className="cart-item-image"
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
                  </div>
                  <div className="cart-item-qty">
                    <button
                      type="button"
                      onClick={() => handleQuantityChange(item.offer.id, 1)}
                      aria-label={`${item.offer.title} miqdorini oshirish`}
                      disabled={item.quantity >= stockLimit}
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

        {recommendedOffers.length > 0 && (
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

      <BottomNav currentPage="cart" cartCount={itemsCount} />

      {/* Checkout Modal */}
      {showCheckout && (
        <div className="modal-overlay checkout-overlay" onClick={closeCheckout}>
          <div className="modal checkout-modal" onClick={e => e.stopPropagation()}>
            <div className="checkout-topbar">
              <h2 className="checkout-title">{checkoutTitle}</h2>
            </div>

            <div className="modal-body checkout-body">
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
                        <span className="order-type-desc">Kuryer orqali</span>
                      </button>
                    </div>
                    {!storeDeliveryEnabled && (
                      <p className="checkout-hint">Yetkazib berish mavjud emas</p>
                    )}
                    {storeDeliveryEnabled && subtotal < AUTO_DELIVERY_THRESHOLD && (
                      <p className="checkout-hint">
                        Yetkazib berish {formatSum(AUTO_DELIVERY_THRESHOLD)} so'mdan boshlab
                      </p>
                    )}
                  </section>
                  <section className="checkout-block">
                    <div className="checkout-block-header">
                      <h3>Yetkazib berish manzili</h3>
                      <button
                        type="button"
                        className="checkout-block-action"
                        onClick={handleLocateMe}
                        disabled={!mapEnabled}
                      >
                        Avtoaniqlash
                      </button>
                    </div>
                    <div className={`checkout-address-card${orderType !== 'delivery' ? ' is-disabled' : ''}`}>
                      <div className="checkout-map">
                        <div ref={checkoutMapRef} className="checkout-map-canvas" aria-hidden="true"></div>
                        <div className="checkout-map-search">
                          <Search size={16} strokeWidth={2} aria-hidden="true" />
                          <input
                            className="checkout-map-search-input"
                            placeholder="Manzilni qidiring"
                            value={mapQuery}
                            onChange={(event) => {
                              const nextValue = event.target.value
                              setMapQuery(nextValue)
                              setAddress(nextValue)
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
                            disabled={!mapEnabled}
                          />
                          {mapSearchLoading && mapSearchOpen && mapEnabled && (
                            <span className="checkout-map-search-loading">Izlanmoqda...</span>
                          )}
                        </div>
                        {mapEnabled && mapSearchOpen && mapQuery.trim().length >= 3 && (
                          <div
                            className="checkout-map-search-results"
                            onPointerDown={(event) => event.preventDefault()}
                          >
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
                    {orderType === 'delivery' && !storeDeliveryEnabled && (
                      <p className="checkout-hint">Yetkazib berish mavjud emas</p>
                    )}
                    {orderType === 'delivery' && storeDeliveryEnabled && !canDelivery && (
                      <p className="checkout-hint">
                        Yetkazib berish uchun minimum {Math.round(minOrderAmount).toLocaleString()} so'm buyurtma qiling
                      </p>
                    )}
                    {orderType === 'delivery' && storeDeliveryEnabled && canDelivery && !hasPrepayProviders && (
                      <p className="checkout-hint">
                        Yetkazib berish uchun to'lov usullari mavjud emas
                      </p>
                    )}
                  </section>

                  <section className="checkout-block">
                    <h3>Yetkazib berish vaqti</h3>
                    <div className="checkout-time-scroll">
                      {deliveryOptions.map(option => (
                        <button
                          key={option.id}
                          type="button"
                          className={`checkout-time-card ${deliverySlot === option.id ? 'active' : ''}`}
                          onClick={() => setDeliverySlot(option.id)}
                          disabled={orderType !== 'delivery'}
                        >
                          <span className="checkout-time-label">{option.label}</span>
                          <span className="checkout-time-value">{option.time}</span>
                        </button>
                      ))}
                    </div>
                  </section>

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
                  </section>

                  <section className="checkout-block checkout-block--last">
                    <h3>Sizning buyurtmangiz</h3>
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
                              <img src={photoUrl} alt={item.offer.title} />
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
                  </section>
                </div>
              )}

              {/* Step 2: Payment (for delivery) */}
              {checkoutStep === 'payment' && (
                <div className="payment-step">
                  {/* Card Transfer UI */}
                  {selectedPaymentMethod === 'card' && paymentCard && (
                    <>
                      <div className="payment-info checkout-section">
                        <p className="payment-instruction">
                          Quyidagi kartaga {Math.round(total).toLocaleString()} so'm o'tkazing:
                        </p>

                        <div className="payment-card">
                          <div className="card-number">
                            <span className="card-label">Karta raqami:</span>
                            <span
                              className="card-value"
                              onClick={() => {
                                navigator.clipboard.writeText(paymentCard.card_number)
                                window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('success')
                                alert('Karta raqami nusxalandi!')
                              }}
                            >
                              {paymentCard.card_number} (nusxa)
                            </span>
                          </div>
                          {paymentCard.card_holder && (
                            <div className="card-holder">
                              <span className="card-label">Egasi:</span>
                              <span className="card-value">{paymentCard.card_holder}</span>
                            </div>
                          )}
                        </div>

                        {paymentCard.payment_instructions && (
                          <p className="payment-instructions">
                            {paymentCard.payment_instructions}
                          </p>
                        )}

                        <div className="payment-amount">
                          <span>To'lov summasi:</span>
                          <strong>{Math.round(total).toLocaleString()} so'm</strong>
                        </div>
                      </div>

                      <div className="upload-section checkout-section">
                        <p className="upload-label">
                          O'tkazma chekini yuklang (majburiy):
                        </p>

                        <div className="upload-area">
                          <button
                            type="button"
                            className={`upload-btn file-picker-btn${paymentProof ? ' is-hidden' : ''}${orderLoading ? ' is-disabled' : ''}`}
                            onClick={openPaymentProofPicker}
                            disabled={orderLoading}
                          >
                            Rasm tanlash
                          </button>
                        </div>

                        {paymentProofPreview && (
                          <div className="proof-preview">
                            <img src={paymentProofPreview} alt="Chek" />
                            <button
                              className="remove-proof"
                              onClick={() => {
                                clearPaymentProof()
                              }}
                            >
                              O'chirish
                            </button>
                          </div>
                        )}
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>

            {checkoutStep === 'details' && (
              <div className="checkout-footer">
                <button
                  className="checkout-confirm"
                  onClick={proceedToPayment}
                  disabled={orderLoading || !getResolvedPhone() || (orderType === 'delivery' && !address.trim())}
                >
                  <span>Buyurtmani tasdiqlash</span>
                  <span className="checkout-confirm-total">{formatSum(checkoutTotal)} so'm</span>
                </button>
              </div>
            )}

            {checkoutStep === 'payment' && (
              <div className="modal-footer payment-footer">
                <button
                  className="cancel-btn"
                  onClick={() => setCheckoutStep('details')}
                  disabled={orderLoading}
                >
                  Bekor qilish
                </button>
                <button
                  className="confirm-btn"
                  onClick={placeOrder}
                  disabled={orderLoading || !paymentProof}
                >
                  {orderLoading ? 'Yuborilmoqda...' : 'Buyurtma berish'}
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Result Modal */}
      {orderResult && (
        <div className="modal-overlay" onClick={() => setOrderResult(null)}>
          <div className="modal result-modal" onClick={e => e.stopPropagation()}>
            {orderResult.success ? (
              <>
                <div className="result-icon success">OK</div>
                <h2>{orderResult.message || 'Buyurtma qabul qilindi!'}</h2>

                {orderResult.awaitingPayment && (
                  <div className="payment-status-chip">
                    To'lov tasdiqlanishini kutyapti (chek yuborildi)
                  </div>
                )}

                {/* Payment card info for awaiting payment orders */}
                {orderResult.awaitingPayment && orderResult.paymentCard && (
                  <div className="payment-instructions">
                    <h3>To'lov ma'lumotlari</h3>
                    <div className="payment-card-info">
                      <p><strong>Karta raqami:</strong></p>
                      <p className="card-number">{orderResult.paymentCard.card_number}</p>
                      <p><strong>Egasi:</strong> {orderResult.paymentCard.card_holder}</p>
                    </div>
                    <div className="payment-steps">
                      <p><strong>Qadamlar:</strong></p>
                      <ol>
                        <li>Yuqoridagi kartaga pul o'tkazing</li>
                        <li>"Buyurtmalarim" bo'limiga o'ting</li>
                        <li>Buyurtmangizni toping va chekni yuklang</li>
                      </ol>
                    </div>
                  </div>
                )}

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

                {orderResult.awaitingPayment ? (
                  <>
                    <button className="btn-primary" onClick={() => {
                      setOrderResult(null)
                      navigate('/profile')
                    }}>
                      Buyurtmalarimga o'tish
                    </button>
                    <button className="btn-secondary" onClick={() => {
                      setOrderResult(null)
                      navigate('/')
                    }}>
                      Bosh sahifa
                    </button>
                  </>
                ) : (
                  <button className="btn-primary" onClick={() => {
                    setOrderResult(null)
                    navigate('/')
                  }}>
                    Bosh sahifaga
                  </button>
                )}
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
        <div className="modal-overlay payment-sheet-overlay" onClick={() => setShowPaymentSheet(false)}>
          <div className="modal payment-sheet" onClick={e => e.stopPropagation()}>
            <div className="payment-sheet-header">
              <h3>To'lov usullari</h3>
              <button className="modal-close" onClick={() => setShowPaymentSheet(false)}>x</button>
            </div>
            <div className="payment-sheet-list">
              <button
                className={`payment-sheet-item ${selectedPaymentMethod === 'cash' ? 'active' : ''} ${deliveryRequiresPrepay ? 'disabled' : ''}`}
                onClick={() => {
                  if (deliveryRequiresPrepay) return
                  selectPaymentMethod('cash')
                  setShowPaymentSheet(false)
                }}
                disabled={deliveryRequiresPrepay}
              >
                <span className="payment-sheet-label">Naqd</span>
                <span className="payment-sheet-radio" aria-hidden="true"></span>
              </button>
              <button
                className={`payment-sheet-item ${selectedPaymentMethod === 'card' ? 'active' : ''} ${!isProviderAvailable('card') ? 'disabled' : ''}`}
                onClick={() => {
                  if (!isProviderAvailable('card')) return
                  selectPaymentMethod('card')
                  setShowPaymentSheet(false)
                }}
                disabled={!isProviderAvailable('card')}
              >
                <span className="payment-sheet-label">Kartaga o'tkazish</span>
                <span className="payment-sheet-radio" aria-hidden="true"></span>
              </button>
              <button
                className={`payment-sheet-item ${selectedPaymentMethod === 'click' ? 'active' : ''} ${!isProviderAvailable('click') ? 'disabled' : ''}`}
                onClick={() => {
                  if (!isProviderAvailable('click')) return
                  selectPaymentMethod('click')
                  setShowPaymentSheet(false)
                }}
                disabled={!isProviderAvailable('click')}
              >
                <span className="payment-sheet-label">Click</span>
                <span className="payment-sheet-radio" aria-hidden="true"></span>
              </button>
              <button
                className={`payment-sheet-item ${selectedPaymentMethod === 'payme' ? 'active' : ''} ${!isProviderAvailable('payme') ? 'disabled' : ''}`}
                onClick={() => {
                  if (!isProviderAvailable('payme')) return
                  selectPaymentMethod('payme')
                  setShowPaymentSheet(false)
                }}
                disabled={!isProviderAvailable('payme')}
              >
                <span className="payment-sheet-label">Payme</span>
                <span className="payment-sheet-radio" aria-hidden="true"></span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default CartPage


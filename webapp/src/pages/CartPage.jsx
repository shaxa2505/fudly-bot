import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { ShoppingCart, Home, Sparkles, ChevronRight, ChevronLeft, ChevronDown, MoreHorizontal, X, Plus, Minus } from 'lucide-react'
import api from '../api/client'
import { useCart } from '../context/CartContext'
import { useToast } from '../context/ToastContext'
import { getUnitLabel, blurOnEnter, isValidPhone } from '../utils/helpers'
import { getCurrentUser } from '../utils/auth'
import { PLACEHOLDER_IMAGE, resolveOfferImageUrl } from '../utils/imageUtils'
import BottomNav from '../components/BottomNav'
import './CartPage.css'

function CartPage({ user }) {
  const navigate = useNavigate()
  const { toast } = useToast()
  // Use cart from context
  const {
    cartItems,
    cartCount,
    cartTotal,
    isEmpty,
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
  const formatSum = (value) => Math.round(value || 0).toLocaleString()
  const savingsLabel = savingsTotal > 0 ? `-${formatSum(savingsTotal)} so'm` : `0 so'm`
  const deliveryOptions = [
    { id: 'fast', label: 'Tezda', time: '25-35 daqiqa' },
    { id: 'slot-1', label: 'Bugun', time: '18:00 - 18:30' },
    { id: 'slot-2', label: 'Bugun', time: '19:00 - 19:30' },
  ]
  const deliverySlotLabel = deliveryOptions.find(option => option.id === deliverySlot)?.time || ''

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
    const shouldDelivery = storeDeliveryEnabled && canDelivery && hasPrepayProviders
    setOrderType(shouldDelivery ? 'delivery' : 'pickup')
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
            <button
              className="cart-header-back"
              type="button"
              onClick={() => navigate(-1)}
              aria-label="Назад"
            >
              <ChevronLeft size={18} strokeWidth={2} />
              <span>Назад</span>
            </button>
            <h1 className="cart-header-title">Savat</h1>
            <div className="cart-header-actions">
              <button
                className="cart-header-chip"
                type="button"
                aria-label="Pastga ochish"
                disabled
              >
                <ChevronDown size={18} strokeWidth={2} />
              </button>
              <button
                className="cart-header-chip"
                type="button"
                onClick={handleClearCart}
                aria-label="Savatni tozalash"
                disabled
              >
                <MoreHorizontal size={18} strokeWidth={2} />
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
          <button
            className="cart-header-back"
            type="button"
            onClick={() => navigate(-1)}
            aria-label="Назад"
          >
            <ChevronLeft size={18} strokeWidth={2} />
            <span>Назад</span>
          </button>
          <h1 className="cart-header-title">Savat</h1>
          <div className="cart-header-actions">
            <button
              className="cart-header-chip"
              type="button"
              aria-label="Pastga ochish"
            >
              <ChevronDown size={18} strokeWidth={2} />
            </button>
            <button
              className="cart-header-chip"
              type="button"
              onClick={handleClearCart}
              aria-label="Savatni tozalash"
            >
              <MoreHorizontal size={18} strokeWidth={2} />
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

        <div className="cart-items">
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
            const subtitle = item.offer.description || item.offer.short_description || item.offer.store_name || item.offer.title
            return (
              <article key={item.offer.id} className="cart-item-card">
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
                  <p className="cart-item-subtitle">{subtitle}</p>
                  <div className="cart-item-prices">
                    <span className="cart-item-price">
                      {formatSum(unitPrice)} so'm
                    </span>
                    {showOriginalPrice && (
                      <span className="cart-item-price-old">
                        {formatSum(originalPrice)} so'm
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
                    <Plus size={16} strokeWidth={2} />
                  </button>
                  <span className="cart-item-qty-value">{item.quantity}</span>
                  <button
                    type="button"
                    onClick={() => handleQuantityChange(item.offer.id, -1)}
                    aria-label={`${item.offer.title} miqdorini kamaytirish`}
                  >
                    <Minus size={16} strokeWidth={2} />
                  </button>
                </div>
              </article>
            )
          })}
        </div>
      </main>

      <div className="cart-summary">
        <div className="cart-summary-card">
          <div className="cart-summary-rows">
            <div className="cart-summary-row">
              <span>Mahsulotlar ({itemsCount})</span>
              <span>{formatSum(subtotal)} so'm</span>
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
              <button className="checkout-back" onClick={closeCheckout} aria-label="Назад">
                <ChevronLeft size={18} strokeWidth={2} />
              </button>
              <h2 className="checkout-title">{checkoutTitle}</h2>
              <span className="checkout-spacer" aria-hidden="true"></span>
            </div>

            <div className="modal-body checkout-body">
              {/* Step 1: Order Details */}
              {checkoutStep === 'details' && (
                <div className="checkout-layout">
                  <section className="checkout-block">
                    <div className="checkout-block-header">
                      <h3>Yetkazib berish manzili</h3>
                      <button
                        type="button"
                        className="checkout-block-action"
                        onClick={() => addressInputRef.current?.focus()}
                      >
                        O'zgartirish
                      </button>
                    </div>
                    <div className={`checkout-address-card${orderType !== 'delivery' ? ' is-disabled' : ''}`}>
                      <div className="checkout-map">
                        <img
                          src="https://lh3.googleusercontent.com/aida-public/AB6AXuBqNdr_LfQSh5ufgPTxOVDNmMdJyNl2Fg4V1Aig_N2HlthOdRDUo4RjOmtTo9KL2wx2QeSPQ0qv09bVl4iKOAsB3fwLjjJQpdT7ZjPKvTIlDWwrCDp9ZzEaN5_JqFau5_ZPG8h40wJK-D7niWEHbTi1cPNFrHYJts1TLftoeks9BgK5_MXf0cWkNHZGzqXNOqM-U4PPubAbORK2bd5St0P7tPptZ2RU_dNXF_TjZUr5hOVuJFRxfcmfNEr7kSkGIfKYs9WaFvxV_3bO"
                          alt="Map"
                        />
                        <div className="checkout-map-pin" aria-hidden="true"></div>
                      </div>
                      <div className="checkout-address-body">
                        <input
                          ref={addressInputRef}
                          className="checkout-address-title"
                          placeholder="Manzilni kiriting"
                          value={address}
                          onChange={e => setAddress(e.target.value)}
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


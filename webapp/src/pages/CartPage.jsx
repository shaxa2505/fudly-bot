import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { ShoppingCart, Home, Sparkles, ArrowLeft, Trash2, ChevronRight, X } from 'lucide-react'
import api from '../api/client'
import { useCart } from '../context/CartContext'
import { useToast } from '../context/ToastContext'
import { getUnitLabel, blurOnEnter, isValidPhone } from '../utils/helpers'
import { PLACEHOLDER_IMAGE, resolveOfferImageUrl } from '../utils/imageUtils'
import QuantityControl from '../components/QuantityControl'
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
  const canonicalPhone = (user?.phone || '').toString().trim()

  const [orderLoading, setOrderLoading] = useState(false)
  const commentInputRef = useRef(null)
  const [focusCommentOnOpen, setFocusCommentOnOpen] = useState(false)

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
  const [checkoutStep, setCheckoutStep] = useState('details') // 'details' | 'payment' | 'upload'
  const [paymentCard, setPaymentCard] = useState(null)
  const [paymentProof, setPaymentProof] = useState(null)
  const [paymentProofPreview, setPaymentProofPreview] = useState(null)
  const [createdOrderId, setCreatedOrderId] = useState(null)
  const [paymentProviders, setPaymentProviders] = useState([])
  const [selectedPaymentMethod, setSelectedPaymentMethod] = useState('cash') // 'cash' | 'card' | 'click' | 'payme'
  const [showPaymentSheet, setShowPaymentSheet] = useState(false)

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

  useEffect(() => {
    if (showCheckout && focusCommentOnOpen) {
      commentInputRef.current?.focus()
      setFocusCommentOnOpen(false)
    }
  }, [showCheckout, focusCommentOnOpen])

  // Keep phone in sync with server profile (bot registration is the single source)
  useEffect(() => {
    if (canonicalPhone && canonicalPhone !== phone) {
      setPhone(canonicalPhone)
      localStorage.setItem('fudly_phone', canonicalPhone)
    }
  }, [canonicalPhone, phone])

  // Check if stores in cart support delivery
  useEffect(() => {
    const checkDeliveryAvailability = async () => {
      // Get unique store IDs from cart
      const storeIds = [...new Set(cartItems.map(item => item.offer?.store_id).filter(Boolean))]

      if (storeIds.length === 0) return

      try {
        const storeId = storeIds[0]
        const cartStore = await api.getStore(storeId)

        if (cartStore) {
          setStoreDeliveryEnabled(!!cartStore.delivery_enabled)
          setDeliveryFee(cartStore.delivery_price || 0)
          setMinOrderAmount(cartStore.min_order_amount || 0)
        }
      } catch (e) {
        console.warn('Could not fetch store info:', e)
        setStoreDeliveryEnabled(false)
        setDeliveryFee(0)
        setMinOrderAmount(0)
      }
    }

    checkDeliveryAvailability()
  }, [cartItems])

  // Calculate totals using context values
  const subtotal = cartTotal
  const total = orderType === 'delivery' ? subtotal + deliveryFee : subtotal
  const itemsCount = cartCount

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

  const selectPaymentMethod = (method) => {
    setSelectedPaymentMethod(method)
    if (method !== 'card') {
      setPaymentProof(null)
      setPaymentProofPreview(null)
    }
  }

  const closeCheckout = () => {
    if (orderLoading) return
    setShowCheckout(false)
    setShowPaymentSheet(false)
  }

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

  const handleCheckout = () => {
    if (isEmpty) return
    if (!canonicalPhone) {
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
      return
    }
    const storeIds = new Set(cartItems.map(item => item.offer?.store_id).filter(Boolean))
    if (storeIds.size > 1) {
      toast.error('Checkout supports only one store. Clear the cart and try again.')
      return
    }
    setCheckoutStep('details')
    setShowCheckout(true)
  }

  const handleCommentShortcut = () => {
    if (isEmpty) return
    setCheckoutStep('details')
    setShowCheckout(true)
    setFocusCommentOnOpen(true)
  }

  // Handle file selection for payment proof
  const handleFileSelect = (e) => {
    const file = e.target.files?.[0]
    if (file) {
      setPaymentProof(file)
      const reader = new FileReader()
      reader.onloadend = () => {
        setPaymentProofPreview(reader.result)
      }
      reader.readAsDataURL(file)
    }
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
        comment: `${orderType === 'pickup' ? 'O\'zi olib ketadi' : 'Yetkazib berish'}\n${comment.trim()}`.trim(),
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
      setPaymentProof(null)
      setPaymentProofPreview(null)
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
        comment: `${orderType === 'pickup' ? 'O\'zi olib ketadi' : 'Yetkazib berish'}\n${comment.trim()}`.trim(),
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

      const orderId = result.order_id || result.bookings?.[0]?.booking_id
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
      if (createdOrderId) {
        navigate(`/order/${createdOrderId}`)
      }
    } finally {
      setOrderLoading(false)
    }
  }

  // Empty cart
  if (isEmpty) {
    return (
      <div className="cart-page">
        <header className="cart-header">
          <div className="cart-header-left">
        <button className="app-back-btn" onClick={() => navigate(-1)} aria-label="Orqaga">
          <ArrowLeft size={20} strokeWidth={2} />
        </button>
            <h1>Savat</h1>
          </div>
        </header>

        <div className="empty-cart">
          <div className="empty-icon">
            <ShoppingCart size={80} strokeWidth={1.5} color="#53B175" aria-hidden="true" />
          </div>
          <h2>Savatingiz bo'sh</h2>
          <p className="empty-description">
            Mahsulotlarni ko'rish va savatga qo'shish uchun bosh sahifaga o'ting.
            Eng yaxshi takliflarni o'tkazib yubormang!
          </p>
          <button className="btn-primary" onClick={() => navigate('/')}>
            <Home size={20} strokeWidth={2} aria-hidden="true" />
            <span>Bosh sahifaga o'tish</span>
          </button>
          <button className="btn-secondary" onClick={() => navigate('/stores')}>
            <Sparkles size={20} strokeWidth={2} aria-hidden="true" />
            <span>Do'konlarni ko'rish</span>
          </button>
        </div>

        <BottomNav currentPage="cart" cartCount={0} />
      </div>
    )
  }

  return (
    <div className="cart-page">
      <header className="cart-header">
        <div className="cart-header-left">
        <button className="app-back-btn" onClick={() => navigate(-1)} aria-label="Orqaga">
          <ArrowLeft size={20} strokeWidth={2} />
        </button>
          <div className="cart-header-title">
            <h1>Savat</h1>
            <span className="cart-header-count">{itemsCount} ta</span>
          </div>
        </div>
        <button className="clear-cart-btn" onClick={clearCart} aria-label="Savatni tozalash">
          <Trash2 size={18} strokeWidth={2} />
        </button>
      </header>

      <div className="cart-items">
        {cartItems.map(item => {
          const photoUrl = resolveOfferImageUrl(item.offer) || PLACEHOLDER_IMAGE
          const stockLimit = item.offer.stock || item.offer.quantity || 99
          const isMaxReached = item.quantity >= stockLimit
          return (
          <div key={item.offer.id} className="cart-item">
            <img
              src={photoUrl}
              alt={item.offer.title}
              className="cart-item-img"
              onError={(e) => {
                if (!e.target.dataset.fallback) {
                  e.target.dataset.fallback = 'true'
                  e.target.src = PLACEHOLDER_IMAGE
                }
              }}
            />
            <div className="cart-item-info">
              <h3 className="cart-item-title">{item.offer.title}</h3>
              <p className="cart-item-price">
                {Math.round(item.offer.discount_price).toLocaleString()} so'm
              </p>
              <button className="cart-item-comment" type="button" onClick={handleCommentShortcut}>
                Izoh qoldirish
              </button>
              {item.offer.store_name && (
                <p className="cart-item-store">Do'kon: {item.offer.store_name}</p>
              )}
              {item.offer.stock && item.quantity >= item.offer.stock && (
                <p className="cart-item-stock-warning">Maksimum: {item.offer.stock} {getUnitLabel(item.offer.unit)}</p>
              )}
            </div>
            <div className="cart-item-controls">
              <QuantityControl
                value={item.quantity}
                size="md"
                onDecrement={() => handleQuantityChange(item.offer.id, -1)}
                onIncrement={() => handleQuantityChange(item.offer.id, 1)}
                disableIncrement={item.quantity >= stockLimit}
              />
              {isMaxReached && (
                <span className="cart-item-limit">Maksimum: {stockLimit} {getUnitLabel(item.offer.unit)}</span>
              )}
              <p className="cart-item-total">
                {Math.round(item.offer.discount_price * item.quantity).toLocaleString()} so'm
              </p>
            </div>
          </div>
        )})}
      </div>

      <div className="cart-sticky-checkout">
        <div className="checkout-total">
          <span className="checkout-total-label">Jami</span>
          <span className="checkout-total-value">{Math.round(total).toLocaleString()} so'm</span>
        </div>
        <button className="checkout-primary-btn" onClick={handleCheckout}>
          Keyingi
        </button>
      </div>

      <BottomNav currentPage="cart" cartCount={itemsCount} />

      {/* Checkout Modal */}
      {showCheckout && (
        <div className="modal-overlay checkout-overlay" onClick={closeCheckout}>
          <div className="modal checkout-modal" onClick={e => e.stopPropagation()}>
            <div className="sheet-handle" aria-hidden="true"></div>
            <div className="modal-header">
              <div className="modal-header-main">
                <button
                  className="app-back-btn"
                  onClick={closeCheckout}
                  type="button"
                  aria-label="Orqaga"
                >
                  <ArrowLeft size={18} strokeWidth={2} aria-hidden="true" />
                </button>
                <h2>
                  {checkoutStep === 'details' && (orderType === 'delivery' ? 'Yetkazib berish' : 'Olib ketish')}
                  {checkoutStep === 'payment' && 'To\'lov'}
                </h2>
                <div className="modal-spacer" aria-hidden="true"></div>
              </div>
            </div>

            <div className="modal-body">
              {/* Step 1: Order Details */}
              {checkoutStep === 'details' && (
                <>
                  {/* Order Type Selection */}
                  <div className="order-type-section">
                    <p className="section-label">Yetkazish turi</p>
                    <div className="order-type-options">
                      <button
                        className={`order-type-btn ${orderType === 'pickup' ? 'active' : ''}`}
                        onClick={() => setOrderType('pickup')}
                      >
                        <span className="order-type-icon">✓</span>
                        <span className="order-type-text">Olib ketish</span>
                        <span className="order-type-desc">Bepul</span>
                      </button>

                      <button
                        className={`order-type-btn ${orderType === 'delivery' ? 'active' : ''} ${!storeDeliveryEnabled || !canDelivery || !hasPrepayProviders ? 'disabled' : ''}`}
                        onClick={() => storeDeliveryEnabled && canDelivery && hasPrepayProviders && setOrderType('delivery')}
                        disabled={!storeDeliveryEnabled || !canDelivery || !hasPrepayProviders}
                      >
                        <span className="order-type-icon">✓</span>
                        <span className="order-type-text">Yetkazib berish</span>
                        <span className="order-type-desc">
                          {!storeDeliveryEnabled
                            ? 'Mavjud emas'
                            : !canDelivery
                              ? `Min: ${Math.round(minOrderAmount).toLocaleString()} so'm`
                              : `${Math.round(deliveryFee).toLocaleString()} so'm`
                          }
                        </span>
                      </button>
                    </div>

                    {!canDelivery && storeDeliveryEnabled && (
                      <p className="delivery-hint">
                        Yetkazib berish uchun minimum {Math.round(minOrderAmount).toLocaleString()} so'm buyurtma qiling
                      </p>
                    )}
                    {storeDeliveryEnabled && canDelivery && !hasPrepayProviders && (
                      <p className="delivery-hint">
                        Yetkazib berish uchun to'lov usullari mavjud emas
                      </p>
                    )}
                  </div>

                  <label className="form-label">
                    Telefon raqam *
                    <input
                      type="tel"
                      className="form-input"
                      placeholder="+998 90 123 45 67"
                      value={canonicalPhone || phone}
                      onChange={e => setPhone(e.target.value)}
                      readOnly={!!canonicalPhone}
                      disabled={!!canonicalPhone}
                    />
                    {!canonicalPhone && !phone.trim() && (
                      <div className="form-hint">
                        Telefon raqamini kiriting yoki botda tasdiqlang.
                      </div>
                    )}
                  </label>

                  {orderType === 'delivery' && (
                    <label className="form-label">
                      Yetkazib berish manzili *
                      <textarea
                        className="form-textarea"
                        placeholder="Shahar, ko'cha, uy raqami, mo'ljal..."
                        value={address}
                        onChange={e => setAddress(e.target.value)}
                        onKeyDown={blurOnEnter}
                      />
                    </label>
                  )}

                  <label className="form-label">
                    Izoh (kuryerga)
                    <textarea
                      className="form-textarea"
                      placeholder="Qo'shimcha ma'lumot..."
                      value={comment}
                      onChange={e => setComment(e.target.value)}
                      onKeyDown={blurOnEnter}
                      ref={commentInputRef}
                    />
                  </label>

                  <button
                    type="button"
                    className="checkout-row checkout-row-button"
                    onClick={() => setShowPaymentSheet(true)}
                  >
                    <div className="checkout-row-left">
                      <span className="checkout-row-title">To'lov</span>
                      <span className="checkout-row-subtitle">{paymentMethodLabels[selectedPaymentMethod]}</span>
                    </div>
                    <ChevronRight size={18} />
                  </button>

                  <div className="order-summary">
                    <div className="summary-line">
                      <span>Mahsulotlar:</span>
                      <span>{Math.round(subtotal).toLocaleString()} so'm</span>
                    </div>
                    {orderType === 'delivery' && (
                      <div className="summary-line">
                        <span>Yetkazib berish:</span>
                        <span>{Math.round(deliveryFee).toLocaleString()} so'm</span>
                      </div>
                    )}
                    <div className="summary-line total">
                      <span><strong>Jami:</strong></span>
                      <span><strong>{Math.round(total).toLocaleString()} so'm</strong></span>
                    </div>
                  </div>
                </>
              )}

              {/* Step 2: Payment (for delivery) */}
              {checkoutStep === 'payment' && (
                <div className="payment-step">
                  {/* Card Transfer UI */}
                  {selectedPaymentMethod === 'card' && paymentCard && (
                    <>
                      <div className="payment-info">
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

                      <div className="upload-section">
                        <p className="upload-label">O'tkazma chekini yuklang:</p>

                        {paymentProofPreview ? (
                          <div className="proof-preview">
                            <img src={paymentProofPreview} alt="Chek" />
                            <button
                              className="remove-proof"
                              onClick={() => {
                                setPaymentProof(null)
                                setPaymentProofPreview(null)
                              }}
                            >
                              O'chirish
                            </button>
                          </div>
                        ) : (
                          <div className="upload-area">
                            <input
                              type="file"
                              id="payment-proof-input"
                              accept="image/*"
                              onChange={handleFileSelect}
                              style={{ display: 'none' }}
                            />
                            <label htmlFor="payment-proof-input" className="upload-btn">
                              Rasm tanlash
                            </label>
                          </div>
                        )}
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>

            <div className="modal-footer">
              {checkoutStep === 'details' && (
                <>
                  <div className="checkout-footer-total">
                    <span>Jami</span>
                    <strong>{Math.round(total).toLocaleString()} so'm</strong>
                  </div>
                  <button
                    className="checkout-footer-btn"
                    onClick={proceedToPayment}
                    disabled={orderLoading || !getResolvedPhone() || (orderType === 'delivery' && !address.trim())}
                  >
                    {orderLoading ? '...' : selectedPaymentMethod === 'card' ? 'To\'lovga o\'tish' : 'Buyurtma berish'}
                  </button>
                </>
              )}

              {checkoutStep === 'payment' && (
                <>
                  <button
                    className="cancel-btn"
                    onClick={() => setCheckoutStep('details')}
                    disabled={orderLoading}
                  >
                    {'<- Orqaga'}
                  </button>
                  <button
                    className="confirm-btn"
                    onClick={placeOrder}
                    disabled={orderLoading || !paymentProof}
                  >
                    {orderLoading ? 'Yuborilmoqda...' : 'Buyurtma berish'}
                  </button>
                </>
              )}

              {checkoutStep === 'payment_upload' && (
                <>
                  <input
                    type="file"
                    id="payment-proof-upload-input"
                    accept="image/*,image/jpeg,image/jpg,image/png"
                    onChange={handleFileSelect}
                    style={{ display: 'none' }}
                  />

                <p className="upload-instruction">
                    Buyurtma yaratildi! Endi to'lov chekini yuklang.
                </p>

                  {paymentProofPreview && (
                    <div className="proof-preview" style={{ margin: '10px 0' }}>
                      <img src={paymentProofPreview} alt="Chek" style={{ maxWidth: '200px', borderRadius: '8px' }} />
                    </div>
                  )}

                  {!paymentProof ? (
                    <button
                      className="confirm-btn"
                      onClick={() => {
                        const input = document.getElementById('payment-proof-upload-input')
                        if (input) {
                          input.click()
                        }
                      }}
                      disabled={orderLoading}
                    >
                      Chekni yuklash
                    </button>
                  ) : (
                    <button
                      className="confirm-btn"
                      onClick={async () => {
                        setOrderLoading(true)
                        try {
                          await api.uploadPaymentProof(orderResult.orderId, paymentProof)
                          clearCart()
                          setShowCheckout(false)
                          setCheckoutStep('details')
                          setPaymentProof(null)
                          setPaymentProofPreview(null)
                          setOrderResult({
                            ...orderResult,
                            awaitingPayment: false,
                            message: 'Chek yuklandi! Admin tekshiradi.'
                          })
                        } catch (error) {
                          alert('Xatolik: ' + error.message)
                        } finally {
                          setOrderLoading(false)
                        }
                      }}
                      disabled={orderLoading}
                    >
                      {orderLoading ? 'Yuklanmoqda...' : 'Yuborish'}
                    </button>
                  )}
                </>
              )}
            </div>
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

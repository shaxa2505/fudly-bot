import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/client'
import { useCart } from '../context/CartContext'
import BottomNav from '../components/BottomNav'
import './CartPage.css'

function CartPage({ user }) {
  const navigate = useNavigate()
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

  const [orderLoading, setOrderLoading] = useState(false)

  // Checkout form
  const [showCheckout, setShowCheckout] = useState(false)
  const [phone, setPhone] = useState(() => localStorage.getItem('fudly_phone') || '')
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
  const fileInputRef = useRef(null)

  // Success/Error modals
  const [orderResult, setOrderResult] = useState(null)

  // Check if stores in cart support delivery
  useEffect(() => {
    const checkDeliveryAvailability = async () => {
      // Get unique store IDs from cart
      const storeIds = [...new Set(cartItems.map(item => item.offer?.store_id).filter(Boolean))]

      if (storeIds.length === 0) return

      try {
        // Check first store for simplicity
        const stores = await api.getStores({})
        const cartStore = stores.find(s => storeIds.includes(s.id))

        if (cartStore) {
          setStoreDeliveryEnabled(cartStore.delivery_enabled || false)
          setDeliveryFee(cartStore.delivery_price || 15000)
          setMinOrderAmount(cartStore.min_order_amount || 30000)
        }
      } catch (e) {
        console.warn('Could not fetch store info:', e)
        // Default values
        setStoreDeliveryEnabled(true)
        setDeliveryFee(15000)
        setMinOrderAmount(30000)
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
    setCheckoutStep('details')
    setShowCheckout(true)
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

  // Proceed to payment step (for delivery)
  const proceedToPayment = async () => {
    if (!phone.trim()) {
      alert('Telefon raqamingizni kiriting')
      return
    }
    if (orderType === 'delivery' && !address.trim()) {
      alert('Yetkazib berish manzilini kiriting')
      return
    }

    // If pickup - place order directly
    if (orderType === 'pickup') {
      await placeOrder()
      return
    }

    // If delivery - fetch payment card and show payment step
    setOrderLoading(true)
    try {
      const storeId = cartItems[0]?.offer?.store_id || 0
      const cardData = await api.getPaymentCard(storeId)
      setPaymentCard(cardData)
      setCheckoutStep('payment')
    } catch (error) {
      console.error('Error fetching payment card:', error)
      alert('To\'lov rekvizitlarini olishda xatolik')
    } finally {
      setOrderLoading(false)
    }
  }

  // Place order (for pickup or after payment upload)
  const placeOrder = async () => {
    if (isEmpty) return

    setOrderLoading(true)

    try {
      const userId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id || user?.id || 1

      const orderData = {
        items: cartItems.map(item => ({
          offer_id: item.offer.id,
          quantity: item.quantity,
        })),
        user_id: userId,
        delivery_address: orderType === 'delivery' ? address.trim() : null,
        phone: phone.trim(),
        comment: `${orderType === 'pickup' ? '🏪 O\'zi olib ketadi' : '🚚 Yetkazib berish'}\n${comment.trim()}`.trim(),
        order_type: orderType,
        delivery_fee: orderType === 'delivery' ? deliveryFee : 0,
      }

      localStorage.setItem('fudly_phone', phone.trim())

      const result = await api.createOrder(orderData)

      // Check if order was successful
      if (!result.success && !result.bookings?.length) {
        throw new Error(result.message || result.error || 'Order failed')
      }

      // Get order ID from response
      const orderId = result.order_id || result.bookings?.[0]?.booking_id

      // If delivery and we have payment proof - upload it
      if (orderType === 'delivery' && paymentProof && orderId) {
        try {
          await api.uploadPaymentProof(orderId, paymentProof)
        } catch (e) {
          console.warn('Could not upload payment proof:', e)
        }
      }

      clearCart()
      setShowCheckout(false)
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

  // Empty cart
  if (isEmpty) {
    return (
      <div className="cart-page">
        <header className="cart-header">
          <h1>🛒 Savat</h1>
        </header>

        <div className="empty-cart">
          <div className="empty-icon">🛒</div>
          <h2>Savatingiz bo'sh</h2>
          <p>Mahsulotlar qo'shish uchun bosh sahifaga o'ting</p>
          <button className="primary-btn" onClick={() => navigate('/')}>
            🏠 Bosh sahifa
          </button>
        </div>

        <BottomNav currentPage="cart" cartCount={0} />
      </div>
    )
  }

  return (
    <div className="cart-page">
      <header className="cart-header">
        <h1>🛒 Savat</h1>
        <button className="clear-cart-btn" onClick={clearCart}>
          🗑️ Tozalash
        </button>
      </header>

      <div className="cart-items">
        {cartItems.map(item => (
          <div key={item.offer.id} className="cart-item">
            <img
              src={item.offer.photo || 'https://placehold.co/80x80/F5F5F5/CCCCCC?text=📷'}
              alt={item.offer.title}
              className="cart-item-img"
              onError={(e) => { e.target.src = 'https://placehold.co/80x80/F5F5F5/CCCCCC?text=📷' }}
            />
            <div className="cart-item-info">
              <h3 className="cart-item-title">{item.offer.title}</h3>
              <p className="cart-item-price">
                {Math.round(item.offer.discount_price).toLocaleString()} so'm
              </p>
              {item.offer.store_name && (
                <p className="cart-item-store">🏪 {item.offer.store_name}</p>
              )}
            </div>
            <div className="cart-item-controls">
              <div className="qty-controls">
                <button
                  className="qty-btn"
                  onClick={() => handleQuantityChange(item.offer.id, -1)}
                >
                  −
                </button>
                <span className="qty-value">{item.quantity}</span>
                <button
                  className="qty-btn plus"
                  onClick={() => handleQuantityChange(item.offer.id, 1)}
                >
                  +
                </button>
              </div>
              <p className="cart-item-total">
                {Math.round(item.offer.discount_price * item.quantity).toLocaleString()} so'm
              </p>
              <button
                className="remove-btn"
                onClick={() => removeItem(item.offer.id)}
              >
                ✕
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className="cart-summary">
        <div className="summary-row">
          <span>Mahsulotlar ({itemsCount} ta)</span>
          <span>{Math.round(subtotal).toLocaleString()} so'm</span>
        </div>
        {orderType === 'delivery' && (
          <div className="summary-row delivery-fee">
            <span>🚚 Yetkazib berish</span>
            <span>{Math.round(deliveryFee).toLocaleString()} so'm</span>
          </div>
        )}
        <div className="summary-row total">
          <span>Jami</span>
          <span>{Math.round(total).toLocaleString()} so'm</span>
        </div>
      </div>

      <button className="checkout-btn" onClick={handleCheckout}>
        Buyurtma berish →
      </button>

      <BottomNav currentPage="cart" cartCount={itemsCount} />

      {/* Checkout Modal */}
      {showCheckout && (
        <div className="modal-overlay" onClick={() => !orderLoading && setShowCheckout(false)}>
          <div className="modal checkout-modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>
                {checkoutStep === 'details' && 'Buyurtmani tasdiqlash'}
                {checkoutStep === 'payment' && '💳 To\'lov'}
              </h2>
              <button
                className="modal-close"
                onClick={() => !orderLoading && setShowCheckout(false)}
              >✕</button>
            </div>

            <div className="modal-body">
              {/* Step 1: Order Details */}
              {checkoutStep === 'details' && (
                <>
                  {/* Order Type Selection */}
                  <div className="order-type-section">
                    <p className="section-label">Buyurtma turi:</p>
                    <div className="order-type-options">
                      <button
                        className={`order-type-btn ${orderType === 'pickup' ? 'active' : ''}`}
                        onClick={() => setOrderType('pickup')}
                      >
                        <span className="order-type-icon">🏪</span>
                        <span className="order-type-text">O'zi olib ketadi</span>
                        <span className="order-type-desc">Bepul</span>
                      </button>

                      <button
                        className={`order-type-btn ${orderType === 'delivery' ? 'active' : ''} ${!storeDeliveryEnabled || !canDelivery ? 'disabled' : ''}`}
                        onClick={() => storeDeliveryEnabled && canDelivery && setOrderType('delivery')}
                        disabled={!storeDeliveryEnabled || !canDelivery}
                      >
                        <span className="order-type-icon">🚚</span>
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
                        💡 Yetkazib berish uchun minimum {Math.round(minOrderAmount).toLocaleString()} so'm buyurtma qiling
                      </p>
                    )}
                  </div>

                  <label className="form-label">
                    📱 Telefon raqam *
                    <input
                      type="tel"
                      className="form-input"
                      placeholder="+998 90 123 45 67"
                      value={phone}
                      onChange={e => setPhone(e.target.value)}
                    />
                  </label>

                  {orderType === 'delivery' && (
                    <label className="form-label">
                      📍 Yetkazib berish manzili *
                      <textarea
                        className="form-textarea"
                        placeholder="Shahar, ko'cha, uy raqami, mo'ljal..."
                        value={address}
                        onChange={e => setAddress(e.target.value)}
                      />
                    </label>
                  )}

                  <label className="form-label">
                    💬 Izoh
                    <textarea
                      className="form-textarea"
                      placeholder="Qo'shimcha ma'lumot..."
                      value={comment}
                      onChange={e => setComment(e.target.value)}
                    />
                  </label>

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
              {checkoutStep === 'payment' && paymentCard && (
                <div className="payment-step">
                  <div className="payment-info">
                    <p className="payment-instruction">
                      💳 Quyidagi kartaga {Math.round(total).toLocaleString()} so'm o'tkazing:
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
                          {paymentCard.card_number} 📋
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
                        📋 {paymentCard.payment_instructions}
                      </p>
                    )}

                    <div className="payment-amount">
                      <span>To'lov summasi:</span>
                      <strong>{Math.round(total).toLocaleString()} so'm</strong>
                    </div>
                  </div>

                  <div className="upload-section">
                    <p className="upload-label">📸 O'tkazma chekini yuklang:</p>

                    <input
                      type="file"
                      ref={fileInputRef}
                      accept="image/*"
                      capture="environment"
                      onChange={handleFileSelect}
                      style={{ display: 'none' }}
                    />

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
                          ✕ O'chirish
                        </button>
                      </div>
                    ) : (
                      <button
                        className="upload-btn"
                        onClick={() => fileInputRef.current?.click()}
                      >
                        📷 Rasm tanlash
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>

            <div className="modal-footer">
              {checkoutStep === 'details' && (
                <>
                  <button
                    className="cancel-btn"
                    onClick={() => setShowCheckout(false)}
                    disabled={orderLoading}
                  >
                    Bekor qilish
                  </button>
                  <button
                    className="confirm-btn"
                    onClick={proceedToPayment}
                    disabled={orderLoading || !phone.trim() || (orderType === 'delivery' && !address.trim())}
                  >
                    {orderLoading ? '⏳ ...' : orderType === 'delivery' ? '💳 To\'lovga o\'tish' : '✅ Tasdiqlash'}
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
                    ← Orqaga
                  </button>
                  <button
                    className="confirm-btn"
                    onClick={placeOrder}
                    disabled={orderLoading || !paymentProof}
                  >
                    {orderLoading ? '⏳ Yuborilmoqda...' : '✅ Buyurtma berish'}
                  </button>
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
                <div className="result-icon success">✅</div>
                <h2>Buyurtma qabul qilindi!</h2>
                {orderResult.bookingCode && (
                  <p className="booking-code-display">
                    🎫 Kod: <strong>{orderResult.bookingCode}</strong>
                  </p>
                )}
                <p className="order-type-result">
                  {orderResult.orderType === 'pickup'
                    ? '🏪 O\'zi olib ketish'
                    : '🚚 Yetkazib berish'
                  }
                </p>
                <p className="order-total-result">
                  💰 Jami: {Math.round(orderResult.total).toLocaleString()} so'm
                </p>
                <p className="order-note">Tez orada siz bilan bog'lanamiz</p>
                <button className="primary-btn" onClick={() => {
                  setOrderResult(null)
                  navigate('/')
                }}>
                  🏠 Bosh sahifaga
                </button>
              </>
            ) : (
              <>
                <div className="result-icon error">❌</div>
                <h2>Xatolik yuz berdi</h2>
                <p>{orderResult.error || 'Iltimos, qaytadan urinib ko\'ring'}</p>
                <button className="primary-btn" onClick={() => setOrderResult(null)}>
                  Yopish
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default CartPage

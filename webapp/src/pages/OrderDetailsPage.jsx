import { useEffect, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import apiClient from '../api/client'
import { resolveOrderItemImageUrl } from '../utils/imageUtils'
import { calcItemsTotal, calcQuantity, calcDeliveryFee, calcTotalPrice } from '../utils/orderMath'
import { deriveDisplayStatus, displayStatusText, normalizeOrderStatus, paymentStatusText, resolveOrderType } from '../utils/orderStatus'
import './OrderDetailsPage.css'

export default function OrderDetailsPage() {
  const { orderId } = useParams()
  const navigate = useNavigate()
  const [order, setOrder] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const enrichmentAttemptedRef = useRef(false)

  useEffect(() => {
    loadOrderDetails({ allowEnrich: true })
    // Auto-refresh every 30 seconds
    const interval = setInterval(() => loadOrderDetails({ allowEnrich: false }), 30000)
    return () => clearInterval(interval)
  }, [orderId])

  const loadOrderDetails = async ({ allowEnrich } = {}) => {
    try {
      setLoading(true)
      const numericOrderId = Number(orderId)
      if (!Number.isFinite(numericOrderId)) {
        setError('Buyurtma topilmadi')
        return
      }

      const statusPayload = await apiClient.getOrderStatus(numericOrderId)
      if (!statusPayload) {
        setError('Buyurtma topilmadi')
        return
      }

      const statusValue = statusPayload.status || statusPayload.order_status || 'pending'
      const baseStatus = normalizeOrderStatus(statusValue)
      const displayStatus = deriveDisplayStatus({
        ...statusPayload,
        order_status: statusValue,
        status: statusValue,
      })

      let foundOrder = {
        ...statusPayload,
        order_id: statusPayload.booking_id || statusPayload.order_id || numericOrderId,
        status: displayStatus,
        fulfillment_status: baseStatus,
        order_status: baseStatus,
        offer_title: statusPayload.offer_title || 'Buyurtma',
        offer_photo: statusPayload.offer_photo,
        store_name: statusPayload.store_name,
        store_address: statusPayload.store_address,
        store_phone: statusPayload.store_phone,
        quantity: statusPayload.quantity || 1,
        items: Array.isArray(statusPayload.items) ? statusPayload.items : [],
        booking_code: statusPayload.booking_code || statusPayload.pickup_code || '',
        delivery_fee: statusPayload.delivery_cost ?? statusPayload.delivery_fee,
      }

      if (allowEnrich && !enrichmentAttemptedRef.current && foundOrder.items.length === 0) {
        enrichmentAttemptedRef.current = true
        try {
          const response = await apiClient.getOrders({ force: true })
          const all = [...(response.orders || []), ...(response.bookings || [])]
          const raw = all.find(o => (o.order_id || o.booking_id) === numericOrderId)
          if (raw) {
            foundOrder = {
              ...raw,
              ...foundOrder,
              items: Array.isArray(raw.items) && raw.items.length > 0 ? raw.items : foundOrder.items,
              offer_title: foundOrder.offer_title || raw.items?.[0]?.offer_title || raw.offer_title || 'Buyurtma',
              offer_photo: foundOrder.offer_photo ||
                resolveOrderItemImageUrl(raw.items?.[0]) ||
                resolveOrderItemImageUrl(raw),
              store_name: foundOrder.store_name || raw.store_name || raw.items?.[0]?.store_name,
              store_address: foundOrder.store_address || raw.store_address,
              store_phone: foundOrder.store_phone || raw.store_phone,
              payment_method: foundOrder.payment_method || raw.payment_method,
              payment_status: foundOrder.payment_status || raw.payment_status,
              order_type: foundOrder.order_type || raw.order_type,
              total_price: foundOrder.total_price ?? raw.total_price,
              quantity: foundOrder.quantity || raw.quantity ||
                raw.items?.reduce((sum, item) => sum + (item.quantity || 0), 0) || 1,
              booking_code: foundOrder.booking_code || raw.booking_code || raw.pickup_code || '',
            }
          }
        } catch (err) {
          console.warn('Failed to enrich order details:', err)
        }
      }

      setOrder(foundOrder)
      setError(null)
    } catch (err) {
      console.error('Failed to load order details:', err)
      setError('Buyurtma ma\'lumotlarini yuklab bo\'lmadi')
    } finally {
      setLoading(false)
    }
  }

  const formatMoney = (value) => Math.round(Number(value || 0)).toLocaleString('ru-RU')

  const getStatusInfo = (status, orderType) => {
    const statusMap = {
      pending: { color: '#F97316', bg: '#FFF4EB' },
      preparing: { color: '#10B981', bg: '#ECFDF5' },
      ready: { color: '#8B5CF6', bg: '#FAF5FF' },
      delivering: { color: '#3B82F6', bg: '#EFF6FF' },
      completed: { color: '#10B981', bg: '#ECFDF5' },
      cancelled: { color: '#EF4444', bg: '#FEF2F2' },
      rejected: { color: '#EF4444', bg: '#FEF2F2' },
      awaiting_payment: { color: '#F59E0B', bg: '#FFFBEB' },
      awaiting_proof: { color: '#F59E0B', bg: '#FFFBEB' },
      proof_submitted: { color: '#3B82F6', bg: '#EFF6FF' },
      payment_rejected: { color: '#EF4444', bg: '#FEF2F2' },
    }
    const palette = statusMap[status] || { color: '#6B7280', bg: '#F3F4F6' }
    return { ...palette, text: displayStatusText(status, 'uz', orderType) }
  }

  const getPaymentStatusLabel = (status) => {
    return paymentStatusText(status, 'uz')
  }

  const formatDate = (dateString) => {
    if (!dateString) return '-'
    const date = new Date(dateString)
    return date.toLocaleString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  const handlePayOnline = async () => {
    if (order?.payment_method !== 'click') {
      return
    }

    try {
      const storeId = order.store_id || null
      const available = await apiClient.getPaymentProviders(storeId)
      if (!available.includes('click')) {
        if (window.Telegram?.WebApp) {
          window.Telegram.WebApp.showAlert('Bu to\'lov usuli hozircha mavjud emas.')
        }
        return
      }

      const returnUrl = window.location.origin + `/order/${orderId}/details`
      const paymentData = await apiClient.createPaymentLink(
        order.order_id,
        'click',
        returnUrl,
        storeId,
        order.total_price || null
      )

      if (paymentData?.payment_url) {
        if (window.Telegram?.WebApp) {
          window.Telegram.WebApp.openLink(paymentData.payment_url)
        } else {
          window.location.href = paymentData.payment_url
        }
      }
    } catch (err) {
      console.error('Failed to open payment link:', err)
    }
  }

  if (loading) {
    return (
      <div className="order-details-page">
        <div className="details-loading">
          <div className="details-spinner"></div>
          <p>Yuklanmoqda...</p>
        </div>
      </div>
    )
  }

  if (error || !order) {
    return (
      <div className="order-details-page">
        <div className="details-header">
          <div className="topbar-card details-header-inner">
            <button className="details-back" onClick={() => navigate(-1)} aria-label="Ortga">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M15 18l-6-6 6-6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
            <div className="details-header-main">
              <span className="details-label">Buyurtma</span>
              <h1 className="details-title">#{orderId}</h1>
            </div>
          </div>
        </div>
        <div className="details-error">
          <div className="details-error-icon">!</div>
          <p>{error || 'Xatolik yuz berdi'}</p>
        </div>
      </div>
    )
  }

  const fulfillmentStatus = order.fulfillment_status || normalizeOrderStatus(order.order_status || order.status)
  const orderType = resolveOrderType(order)
  const statusInfo = getStatusInfo(fulfillmentStatus || order.status, orderType)
  const isDelivery = orderType === 'delivery'
  const isCancelled = ['cancelled', 'rejected'].includes(fulfillmentStatus)
  const canPayOnline = order.payment_method === 'click'
  const paymentStatusLabel = getPaymentStatusLabel(order.payment_status || order.status)

  const rawTotalValue = order?.total_price
  const rawTotal = rawTotalValue == null ? null : Number(rawTotalValue || 0)
  const hasItemBreakdown = Array.isArray(order.items) && order.items.length > 0
  const rawItemsSubtotal = hasItemBreakdown
    ? calcItemsTotal(order.items, {
      getPrice: (item) => Number(item?.price || 0),
      getQuantity: (item) => Number(item?.quantity || 0),
    })
    : 0
  const deliveryFee = isDelivery
    ? calcDeliveryFee(rawTotal, rawItemsSubtotal, {
      deliveryFee: order?.delivery_fee,
      isDelivery,
    })
    : 0
  const itemsSubtotal = hasItemBreakdown
    ? rawItemsSubtotal
    : Math.max(0, (rawTotal || 0) - deliveryFee)
  const totalPrice = calcTotalPrice(rawItemsSubtotal, deliveryFee, { totalPrice: rawTotal })
  const totalUnits = hasItemBreakdown
    ? calcQuantity(order.items, item => Number(item?.quantity || 0))
    : (order.quantity || 1)

  const paymentMethodLabels = {
    cash: 'Naqd',
    card: 'Karta',
    click: 'Click',
    payme: 'Payme',
  }

  const paymentNotice = (() => {
    switch (order.status) {
      case 'awaiting_payment':
        return {
          title: "To'lovni yakunlang",
          text: "Buyurtma tasdiqlanishi uchun to'lovni yakunlash kerak.",
          tone: 'warning',
          icon: '!',
          showActions: canPayOnline,
        }
      case 'awaiting_proof':
        return {
          title: "To'lov holati kutilmoqda",
          text: "Bu buyurtma eski to'lov usuli bilan yaratilgan. Qo'llab-quvvatlashga yozing.",
          tone: 'warning',
          icon: '!',
          showActions: false,
        }
      case 'payment_rejected':
        return {
          title: "To'lov rad etildi",
          text: "To'lovni Click orqali qayta bajaring yoki qo'llab-quvvatlashga yozing.",
          tone: 'danger',
          icon: '!',
          showActions: false,
        }
      case 'proof_submitted':
        return {
          title: 'Chek tekshirilmoqda',
          text: 'Chekingiz qabul qilindi. Tasdiqlashni kuting.',
          tone: 'info',
          icon: 'i',
          showActions: false,
        }
      default:
        return null
    }
  })()

  const payButtonLabel = "Click bilan to'lash"
  const showPayButton = canPayOnline && order.status === 'awaiting_payment'
  const isPayPrimary = showPayButton

  const statusSteps = isDelivery
    ? [
        { key: 'pending', label: 'Yaratildi' },
        { key: 'preparing', label: 'Tayyorlanmoqda' },
        { key: 'ready', label: 'Tayyor' },
        { key: 'delivering', label: "Yo'lda" },
        { key: 'completed', label: 'Yakunlandi' },
      ]
    : [
        { key: 'pending', label: 'Yaratildi' },
        { key: 'preparing', label: 'Tayyorlanmoqda' },
        { key: 'ready', label: 'Tayyor' },
        { key: 'completed', label: 'Yakunlandi' },
      ]

  const activeStepIndex = Math.max(0, statusSteps.findIndex(step => step.key === fulfillmentStatus))
  const orderPhotoUrl = resolveOrderItemImageUrl(order)

  return (
    <div className="order-details-page">
      <div className="details-header">
        <div className="topbar-card details-header-inner">
          <button className="details-back" onClick={() => navigate(-1)} aria-label="Ortga">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M15 18l-6-6 6-6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
          <div className="details-header-main">
            <span className="details-label">Buyurtma</span>
            <div className="details-title-row">
              <h1 className="details-title">#{orderId}</h1>
            </div>
            <div className="details-meta">
              <span className="details-meta-item">{order.store_name || "Do'kon"}</span>
              <span className="details-dot"></span>
              <span className="details-meta-item">{formatDate(order.created_at)}</span>
            </div>
          </div>
          <div className="details-header-side">
            <span className="details-type-pill">{isDelivery ? 'Yetkazib berish' : 'Olib ketish'}</span>
            <span className="status-pill" style={{ backgroundColor: statusInfo.bg, color: statusInfo.color }}>
              {statusInfo.text}
            </span>
          </div>
        </div>
      </div>

      {isCancelled && (
        <div className="status-note">
          <div className="status-note-title">
            {fulfillmentStatus === 'rejected' ? 'Buyurtma rad etildi' : 'Buyurtma bekor qilindi'}
          </div>
          <p className="status-note-text">Agar savollaringiz bo'lsa, qo'llab-quvvatlashga yozing.</p>
        </div>
      )}

      {paymentNotice && (
        <div className={`action-card tone-${paymentNotice.tone}`}>
          <div className="action-header">
            <div className="action-icon">{paymentNotice.icon}</div>
            <div className="action-content">
              <h3>{paymentNotice.title}</h3>
              <p>{paymentNotice.text}</p>
            </div>
          </div>
          {paymentNotice.showActions && (
            <div className="action-buttons">
              {showPayButton && (
                <button
                  className={`action-btn ${isPayPrimary ? 'primary' : 'ghost'}`}
                  onClick={handlePayOnline}
                >
                  {payButtonLabel}
                </button>
              )}
            </div>
          )}
        </div>
      )}

      <div className="summary-card">
        <div className="summary-grid">
          <div className="summary-item">
            <span className="summary-label">Jami</span>
            <span className="summary-value total">{formatMoney(totalPrice)} so'm</span>
          </div>
          <div className="summary-item">
            <span className="summary-label">Mahsulotlar</span>
            <span className="summary-value">{totalUnits} dona</span>
          </div>
          <div className="summary-item">
            <span className="summary-label">Buyurtma turi</span>
            <span className="summary-value">{isDelivery ? 'Yetkazib berish' : 'Olib ketish'}</span>
          </div>
          <div className="summary-item">
            <span className="summary-label">To'lov usuli</span>
            <span className="summary-value">{paymentMethodLabels[order.payment_method] || 'Naqd'}</span>
          </div>
        </div>
        {paymentStatusLabel && (
          <div className="summary-chip">{paymentStatusLabel}</div>
        )}
      </div>

      {!isCancelled && (
        <div className="details-section">
          <h2 className="details-section-title">Buyurtma bosqichlari</h2>
          <div className="progress-card">
            {statusSteps.map((step, index) => {
              const isComplete = index <= activeStepIndex
              const isCurrent = index === activeStepIndex
              return (
                <div
                  key={step.key}
                  className={`progress-step ${isComplete ? 'is-complete' : ''} ${isCurrent ? 'is-current' : ''}`}
                >
                  <div className="progress-marker">
                    <span className="progress-dot"></span>
                    {index < statusSteps.length - 1 && <span className="progress-line"></span>}
                  </div>
                  <div className="progress-content">
                    <span className="progress-title">{step.label}</span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      <div className="details-section">
        <h2 className="details-section-title">Mahsulotlar</h2>
        <div className="items-list">
          {order.items && order.items.length > 0 ? (
            order.items.map((item, idx) => {
              const itemPhoto = resolveOrderItemImageUrl(item)
              const itemTitle = item.offer_title || item.title || 'Mahsulot'
              const itemTotal = Number(item.price || 0) * Number(item.quantity || 0)
              return (
                <div key={idx} className="item-card">
                  <div className="item-thumb">
                    {itemPhoto ? (
                      <img
                        src={itemPhoto}
                        alt={itemTitle}
                        className="item-image"
                        onError={(e) => {
                          e.target.style.display = 'none'
                        }}
                      />
                    ) : (
                      <div className="item-placeholder">{itemTitle.trim().charAt(0).toUpperCase()}</div>
                    )}
                  </div>
                  <div className="item-body">
                    <div className="item-row">
                      <h3 className="item-title">{itemTitle}</h3>
                      <span className="item-total">{formatMoney(itemTotal)} so'm</span>
                    </div>
                    <div className="item-sub">
                      <span>{item.quantity} x {formatMoney(item.price)} so'm</span>
                    </div>
                    {item.store_name && (
                      <div className="item-store">Do'kon: {item.store_name}</div>
                    )}
                  </div>
                </div>
              )
            })
          ) : (
            <div className="item-card">
              <div className="item-thumb">
                {orderPhotoUrl ? (
                  <img
                    src={orderPhotoUrl}
                    alt={order.offer_title}
                    className="item-image"
                    onError={(e) => {
                      e.target.style.display = 'none'
                    }}
                  />
                ) : (
                  <div className="item-placeholder">{(order.offer_title || 'B').trim().charAt(0).toUpperCase()}</div>
                )}
              </div>
              <div className="item-body">
                <div className="item-row">
                  <h3 className="item-title">{order.offer_title}</h3>
                  <span className="item-total">{formatMoney(totalPrice)} so'm</span>
                </div>
                <div className="item-sub">
                  <span>{order.quantity || 1} dona</span>
                </div>
                {order.store_name && (
                  <div className="item-store">Do'kon: {order.store_name}</div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {isDelivery && order.delivery_address && (
        <div className="details-section">
          <h2 className="details-section-title">Yetkazib berish</h2>
          <div className="info-card">
            <div className="info-row">
              <span className="info-label">Manzil</span>
              <span className="info-value">{order.delivery_address}</span>
            </div>
            {order.phone && (
              <div className="info-row">
                <span className="info-label">Telefon</span>
                <span className="info-value">{order.phone}</span>
              </div>
            )}
            {order.delivery_notes && (
              <div className="info-row">
                <span className="info-label">Izoh</span>
                <span className="info-value">{order.delivery_notes}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {!isDelivery && order.booking_code && (
        <div className="details-section">
          <h2 className="details-section-title">Olib ketish</h2>
          <div className="info-card">
            <div className="info-row">
              <span className="info-label">Kod</span>
              <span className="info-value booking-code">{order.booking_code}</span>
            </div>
            {order.pickup_time && (
              <div className="info-row">
                <span className="info-label">Vaqt</span>
                <span className="info-value">{formatDate(order.pickup_time)}</span>
              </div>
            )}
          </div>
        </div>
      )}

      <div className="details-section">
        <h2 className="details-section-title">To'lov tafsilotlari</h2>
        <div className="info-card">
          <div className="info-row">
            <span className="info-label">Mahsulotlar</span>
            <span className="info-value">{formatMoney(itemsSubtotal)} so'm</span>
          </div>
          {deliveryFee > 0 && (
            <div className="info-row">
              <span className="info-label">Yetkazib berish</span>
              <span className="info-value">{formatMoney(deliveryFee)} so'm</span>
            </div>
          )}
          <div className="info-row">
            <span className="info-label">To'lov usuli</span>
            <span className="info-value">{paymentMethodLabels[order.payment_method] || 'Naqd'}</span>
          </div>
          {paymentStatusLabel && (
            <div className="info-row">
              <span className="info-label">To'lov holati</span>
              <span className="info-value">{paymentStatusLabel}</span>
            </div>
          )}
          <div className="info-row total-row">
            <span className="info-label">Jami</span>
            <span className="info-value total-price">{formatMoney(totalPrice)} so'm</span>
          </div>
        </div>
      </div>

      <div className="details-section">
        <h2 className="details-section-title">Do'kon</h2>
        <div className="info-card">
          <div className="info-row">
            <span className="info-label">Nomi</span>
            <span className="info-value">{order.store_name || "Do'kon"}</span>
          </div>
          {order.store_address && (
            <div className="info-row">
              <span className="info-label">Manzil</span>
              <span className="info-value">{order.store_address}</span>
            </div>
          )}
          {order.store_phone && (
            <div className="info-row">
              <span className="info-label">Telefon</span>
              <span className="info-value">
                <a href={`tel:${order.store_phone}`}>{order.store_phone}</a>
              </span>
            </div>
          )}
        </div>
      </div>

      <div className="support-section">
        <p className="support-text">Savollar bormi?</p>
        <button
          className="support-btn"
          onClick={() => {
            if (window.Telegram?.WebApp) {
              window.Telegram.WebApp.openTelegramLink('https://t.me/fudly_support')
            }
          }}
        >
          Qo'llab-quvvatlash
        </button>
      </div>
    </div>
  )
}

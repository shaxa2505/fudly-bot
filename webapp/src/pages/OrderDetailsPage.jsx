import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import apiClient, { API_BASE_URL, getTelegramInitData } from '../api/client'
import { resolveOrderItemImageUrl } from '../utils/imageUtils'
import { calcItemsTotal, calcQuantity, calcDeliveryFee, calcTotalPrice } from '../utils/orderMath'
import { deriveDisplayStatus, displayStatusText, normalizeOrderStatus, normalizePaymentStatus, paymentStatusText, resolveOrderType } from '../utils/orderStatus'
import { readPendingPayment, clearPendingPayment } from '../utils/pendingPayment'
import { getUserId } from '../utils/auth'
import './OrderDetailsPage.css'

export default function OrderDetailsPage() {
  const { orderId } = useParams()
  const [order, setOrder] = useState(null)
  const [loading, setLoading] = useState(true)
  const [isSyncing, setIsSyncing] = useState(false)
  const [error, setError] = useState(null)
  const enrichmentAttemptedRef = useRef(false)
  const userId = getUserId()

  useEffect(() => {
    if (!order) return
    const pending = readPendingPayment()
    if (!pending?.orderId) return
    if (Number(pending.orderId) !== Number(order.order_id || order.booking_id || orderId)) return

    const baseStatus = normalizeOrderStatus(order.order_status || order.status)
    const paymentStatus = String(order.payment_status || '').toLowerCase()
    const doneStatuses = new Set(['completed', 'cancelled', 'rejected', 'delivering', 'ready', 'preparing'])

    if ((paymentStatus && paymentStatus !== 'awaiting_payment') || doneStatuses.has(baseStatus)) {
      clearPendingPayment()
    }
  }, [order, orderId])

  const loadOrderDetails = useCallback(async ({ allowEnrich = false, silent = false } = {}) => {
    try {
      if (!silent) {
        setLoading(true)
      } else {
        setIsSyncing(true)
      }
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
      if (!silent) {
        setLoading(false)
      }
      setIsSyncing(false)
    }
  }, [orderId])

  useEffect(() => {
    loadOrderDetails({ allowEnrich: true, silent: false })
    // Auto-refresh every 15 seconds (silent)
    const interval = setInterval(() => loadOrderDetails({ allowEnrich: false, silent: true }), 15000)
    return () => clearInterval(interval)
  }, [orderId, loadOrderDetails])

  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        loadOrderDetails({ allowEnrich: false, silent: true })
      }
    }
    window.addEventListener('focus', handleVisibility)
    document.addEventListener('visibilitychange', handleVisibility)
    return () => {
      window.removeEventListener('focus', handleVisibility)
      document.removeEventListener('visibilitychange', handleVisibility)
    }
  }, [loadOrderDetails])

  useEffect(() => {
    if (!userId) return

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
          if (!eventOrderId || Number(eventOrderId) === Number(orderId)) {
            loadOrderDetails({ allowEnrich: false, silent: true })
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
  }, [orderId, userId, loadOrderDetails])

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
        window.Telegram?.WebApp?.showAlert?.('Bu to\'lov usuli hozircha mavjud emas.')
        return
      }

      const returnUrl = window.location.origin + `/order/${orderId}`
      const paymentData = await apiClient.createPaymentLink(
        order.order_id,
        'click',
        returnUrl,
        storeId,
        Number.isFinite(payableTotal) ? payableTotal : null
      )

      if (paymentData?.payment_url) {
        if (window.Telegram?.WebApp?.openLink) {
          window.Telegram?.WebApp?.openLink?.(paymentData.payment_url)
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
            <div className="details-header-main">
              <div className="details-title-row">
                <h1 className="details-title">Buyurtma #{orderId}</h1>
              </div>
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
  const isDelivery = orderType === 'delivery'
  const displayFulfillmentStatus = fulfillmentStatus
  const statusInfo = getStatusInfo(displayFulfillmentStatus || order.status, orderType)
  const isCancelled = ['cancelled', 'rejected'].includes(fulfillmentStatus)
  const canPayOnline = order.payment_method === 'click'
  const paymentStatusLabel = getPaymentStatusLabel(order.payment_status || order.status)
  const showPaymentChip = paymentStatusLabel && paymentStatusLabel !== "To'lov talab qilinmaydi"

  const rawTotalValue = order?.total_price
  const rawTotal = rawTotalValue == null ? null : Number(rawTotalValue || 0)
  const explicitItemsTotal = order?.items_total
  const explicitTotalWithDelivery = order?.total_with_delivery
  const hasItemBreakdown = Array.isArray(order.items) && order.items.length > 0
  const rawItemsSubtotal = hasItemBreakdown
    ? calcItemsTotal(order.items, {
      getPrice: (item) => Number(item?.price || 0),
      getQuantity: (item) => Number(item?.quantity || 0),
    })
    : 0
  const itemsSubtotal = hasItemBreakdown
    ? rawItemsSubtotal
    : Number(explicitItemsTotal ?? (rawTotal ?? 0))
  const deliveryFee = isDelivery
    ? calcDeliveryFee(rawTotal, itemsSubtotal, {
      deliveryFee: order?.delivery_fee,
      isDelivery,
    })
    : 0
  const totalWithDelivery = Number(
    explicitTotalWithDelivery ?? calcTotalPrice(itemsSubtotal, deliveryFee)
  )
  const payableTotal = Number(
    explicitItemsTotal ?? (hasItemBreakdown ? rawItemsSubtotal : (rawTotal ?? 0))
  )
  const totalUnits = hasItemBreakdown
    ? calcQuantity(order.items, item => Number(item?.quantity || 0))
    : (order.quantity || 1)

  const paymentMethodLabels = {
    cash: 'Naqd',
    card: 'Karta',
    click: 'Click',
    payme: 'Payme',
  }

  const normalizedPaymentStatus = normalizePaymentStatus(order.payment_status, order.payment_method)

  const paymentNotice = (() => {
    switch (normalizedPaymentStatus) {
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
  const showPayButton = canPayOnline && normalizedPaymentStatus === 'awaiting_payment'
  const isPayPrimary = showPayButton

  const statusSteps = isDelivery
    ? [
        { key: 'pending', label: 'Yaratildi' },
        { key: 'preparing', label: 'Tasdiqlandi' },
        { key: 'delivering', label: "Yo'lda" },
        { key: 'completed', label: 'Yakunlandi' },
      ]
    : [
        { key: 'pending', label: 'Yaratildi' },
        { key: 'preparing', label: 'Tasdiqlandi' },
        { key: 'ready', label: 'Tayyor' },
        { key: 'completed', label: 'Berildi' },
      ]

  const activeStepIndex = Math.max(0, statusSteps.findIndex(step => step.key === displayFulfillmentStatus))
  const orderPhotoUrl = resolveOrderItemImageUrl(order)
  const showPickupReadyNote = !isDelivery && displayFulfillmentStatus === 'ready'
  const pickupReadyUntil = order?.ready_until
  const hasDeliveryInfo = Boolean(order.delivery_address || order.phone || order.delivery_notes)
  const hasStoreInfo = Boolean(order.store_name || order.store_address || order.store_phone)

  return (
    <div className="order-details-page">
      <div className="details-header">
        <div className="topbar-card details-header-inner">
          <div className="details-header-main">
            <div className="details-title-row">
              <h1 className="details-title">Buyurtma #{orderId}</h1>
              {isSyncing && (
                <span className="details-sync">
                  <span className="details-sync-dot"></span>
                  Yangilanmoqda
                </span>
              )}
            </div>
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

      <div className="hero-card">
        <div className="hero-top">
          <div className="hero-meta">
            <span className="hero-store">{order.store_name || "Do'kon"}</span>
            <span className="details-dot"></span>
            <span className="hero-date">{formatDate(order.created_at)}</span>
          </div>
          <div className="hero-status">
            <span className="details-type-pill">{isDelivery ? 'Yetkazib berish' : 'Olib ketish'}</span>
            <span className="status-pill" style={{ backgroundColor: statusInfo.bg, color: statusInfo.color }}>
              {statusInfo.text}
            </span>
          </div>
          {showPickupReadyNote && pickupReadyUntil && (
            <div className="hero-deadline">
              Olib ketishgacha: {pickupReadyUntil}
            </div>
          )}
        </div>
        <div className="hero-body">
          <div className="hero-total">
            <span className="hero-label">Jami</span>
            <span className="hero-value">{formatMoney(totalWithDelivery)} so'm</span>
          </div>
          {orderPhotoUrl && (
            <div className="hero-photo">
              <img
                src={orderPhotoUrl}
                alt={order.offer_title || 'Buyurtma'}
                loading="lazy"
                decoding="async"
                onError={(e) => {
                  e.currentTarget.style.display = 'none'
                }}
              />
            </div>
          )}
        </div>
        <div className="hero-grid">
          <div className="hero-item">
            <span className="hero-label">Mahsulotlar</span>
            <span className="hero-value">{totalUnits} dona</span>
          </div>
          <div className="hero-item">
            <span className="hero-label">To'lov usuli</span>
            <span className="hero-value">{paymentMethodLabels[order.payment_method] || 'Naqd'}</span>
          </div>
          <div className="hero-item">
            <span className="hero-label">Buyurtma turi</span>
            <span className="hero-value">{isDelivery ? 'Yetkazib berish' : 'Olib ketish'}</span>
          </div>
        </div>
        {showPaymentChip && (
          <div className="hero-chip">{paymentStatusLabel}</div>
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

      {showPickupReadyNote && (
        <div className="pickup-ready-note">
          <div className="pickup-ready-icon">i</div>
          <div className="pickup-ready-content">
            <h3>Buyurtma tayyor</h3>
            <p>
              {pickupReadyUntil
                ? `Olib ketishgacha: ${pickupReadyUntil}`
                : "2 soat ichida olib ketishingiz kerak, aks holda buyurtma bekor qilinadi."}
            </p>
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
                        loading="lazy"
                        decoding="async"
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
                    loading="lazy"
                    decoding="async"
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
                  <span className="item-total">{formatMoney(totalWithDelivery)} so'm</span>
                </div>
                <div className="item-sub">
                  <span>{order.quantity || 1} dona</span>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {isDelivery && (
        <div className="details-section">
          <h2 className="details-section-title">Yetkazib berish</h2>
          <div className="info-card">
            {hasDeliveryInfo && (
              <div className="info-group">
                <div className="info-group-title">Mijoz</div>
                {order.delivery_address && (
                  <div className="info-row">
                    <span className="info-label">Manzil</span>
                    <span className="info-value">{order.delivery_address}</span>
                  </div>
                )}
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
            )}
            {hasStoreInfo && (
              <div className="info-group">
                <div className="info-group-title">Do'kon</div>
                {order.store_name && (
                  <div className="info-row">
                    <span className="info-label">Nomi</span>
                    <span className="info-value">{order.store_name}</span>
                  </div>
                )}
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
            )}
          </div>
        </div>
      )}

      {!isDelivery && (
        <div className="details-section">
          <h2 className="details-section-title">Olib ketish</h2>
          <div className="info-card">
            {(order.booking_code || order.pickup_time || order.pickup_address) && (
              <div className="info-group">
                <div className="info-group-title">Buyurtma</div>
                {order.booking_code && (
                  <div className="info-row">
                    <span className="info-label">Kod</span>
                    <span className="info-value booking-code">{order.booking_code}</span>
                  </div>
                )}
                {order.pickup_time && (
                  <div className="info-row">
                    <span className="info-label">Vaqt</span>
                    <span className="info-value">{formatDate(order.pickup_time)}</span>
                  </div>
                )}
                {order.pickup_address && (
                  <div className="info-row">
                    <span className="info-label">Manzil</span>
                    <span className="info-value">{order.pickup_address}</span>
                  </div>
                )}
              </div>
            )}
            {hasStoreInfo && (
              <div className="info-group">
                <div className="info-group-title">Do'kon</div>
                {order.store_name && (
                  <div className="info-row">
                    <span className="info-label">Nomi</span>
                    <span className="info-value">{order.store_name}</span>
                  </div>
                )}
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
            )}
          </div>
        </div>
      )}

      <div className="details-section">
        <h2 className="details-section-title">To'lov tafsilotlari</h2>
        <div className="info-card">
          <div className="info-group">
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
            <div className="info-row total-row">
              <span className="info-label">Jami</span>
              <span className="info-value total-price">{formatMoney(totalWithDelivery)} so'm</span>
            </div>
          </div>
        </div>
        {isDelivery && (
          <div className="payment-note">
            Yetkazib berish to&apos;lovi buyurtma qabul qilinganda kuryerga alohida to&apos;lanadi.
          </div>
        )}
      </div>

      <div className="support-section">
        <p className="support-text">Savollar bormi?</p>
        <button
          className="support-btn"
          onClick={() => {
            window.Telegram?.WebApp?.openTelegramLink?.('https://t.me/fudly_support')
          }}
        >
          Qo'llab-quvvatlash
        </button>
      </div>
    </div>
  )
}

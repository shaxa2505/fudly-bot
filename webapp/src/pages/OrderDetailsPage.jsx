import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ChevronLeft, MoreHorizontal, Phone, QrCode } from 'lucide-react'
import apiClient, { API_BASE_URL, getTelegramInitData } from '../api/client'
import { resolveOrderItemImageUrl } from '../utils/imageUtils'
import { calcItemsTotal, calcQuantity, calcDeliveryFee, calcTotalPrice } from '../utils/orderMath'
import { deriveDisplayStatus, displayStatusText, normalizeOrderStatus, normalizePaymentStatus, paymentStatusText, resolveOrderType } from '../utils/orderStatus'
import { readPendingPayment, clearPendingPayment } from '../utils/pendingPayment'
import { getUserId } from '../utils/auth'
import './OrderDetailsPage.css'

export default function OrderDetailsPage() {
  const { orderId } = useParams()
  const navigate = useNavigate()
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
      setError("Buyurtma ma'lumotlarini yuklab bo'lmadi")
    } finally {
      if (!silent) {
        setLoading(false)
      }
      setIsSyncing(false)
    }
  }, [orderId])

  useEffect(() => {
    loadOrderDetails({ allowEnrich: true, silent: false })
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

  const formatMoney = (value) => Math.round(Number(value || 0)).toLocaleString('uz-UZ')

  const getStatusInfo = (status, orderType) => {
    const statusMap = {
      pending: { color: '#C2410C', bg: '#FEF3C7' },
      preparing: { color: '#1D4ED8', bg: '#DBEAFE' },
      ready: { color: '#15803D', bg: '#DCFCE7' },
      delivering: { color: '#0F766E', bg: '#CCFBF1' },
      completed: { color: '#15803D', bg: '#DCFCE7' },
      cancelled: { color: '#B91C1C', bg: '#FEE2E2' },
      rejected: { color: '#B91C1C', bg: '#FEE2E2' },
      awaiting_payment: { color: '#C2410C', bg: '#FEF3C7' },
      awaiting_proof: { color: '#C2410C', bg: '#FEF3C7' },
      proof_submitted: { color: '#1D4ED8', bg: '#DBEAFE' },
      payment_rejected: { color: '#B91C1C', bg: '#FEE2E2' },
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
    if (Number.isNaN(date.getTime())) return String(dateString)
    return date.toLocaleString('uz-UZ', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  const formatTimeOnly = (value) => {
    if (!value) return ''
    if (typeof value === 'string') {
      if (value.includes('T')) {
        const date = new Date(value)
        if (!Number.isNaN(date.getTime())) {
          return date.toLocaleTimeString('uz-UZ', { hour: '2-digit', minute: '2-digit' })
        }
      }
      const match = value.match(/(\d{1,2}:\d{2})/)
      if (match) return match[1]
      return value
    }
    return String(value)
  }

  const formatPhone = (raw) => {
    if (!raw) return ''
    const sanitized = String(raw).replace(/[^0-9+]/g, '')
    const digits = sanitized.replace(/\D/g, '')
    if (digits.startsWith('998') && digits.length === 12) {
      return `+998 ${digits.slice(3, 5)} ${digits.slice(5, 8)} ${digits.slice(8, 10)} ${digits.slice(10, 12)}`
    }
    if (sanitized.startsWith('+') && digits) {
      return `+${digits}`
    }
    return sanitized || String(raw)
  }

  const phoneLink = (raw) => {
    if (!raw) return ''
    return String(raw).replace(/[^0-9+]/g, '')
  }

  const handlePayOnline = async () => {
    if (order?.payment_method !== 'click') {
      return
    }

    try {
      const storeId = order.store_id || null
      const available = await apiClient.getPaymentProviders(storeId)
      if (!available.includes('click')) {
        window.Telegram?.WebApp?.showAlert?.("Bu to'lov usuli hozircha mavjud emas.")
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

  const handleGetDirections = () => {
    const address = order?.pickup_address || order?.store_address || order?.delivery_address
    if (!address) {
      window.Telegram?.WebApp?.showAlert?.('Manzil topilmadi')
      return
    }
    const url = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(address)}`
    if (window.Telegram?.WebApp?.openLink) {
      window.Telegram.WebApp.openLink(url)
    } else {
      window.open(url, '_blank', 'noopener,noreferrer')
    }
  }

  const handleOpenReceipt = () => {
    const receiptUrl = order?.receipt_url || order?.invoice_url
    if (receiptUrl) {
      if (window.Telegram?.WebApp?.openLink) {
        window.Telegram.WebApp.openLink(receiptUrl)
      } else {
        window.open(receiptUrl, '_blank', 'noopener,noreferrer')
      }
      return
    }
    window.Telegram?.WebApp?.showAlert?.('Chek tez orada tayyor bo\'ladi')
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
        { key: 'pending', label: 'Tasdiqlandi' },
        { key: 'delivering', label: "Yo'lda" },
        { key: 'completed', label: 'Yetkazildi' },
      ]
    : [
        { key: 'pending', label: 'Tasdiqlandi' },
        { key: 'preparing', label: 'Tayyorlanmoqda' },
        { key: 'ready', label: 'Tayyor' },
      ]

  const activeStepIndex = Math.max(0, statusSteps.findIndex(step => step.key === displayFulfillmentStatus))
  const heroTitle = (() => {
    switch (displayFulfillmentStatus) {
      case 'ready':
        return isDelivery ? 'Yetkazib berishga tayyor' : 'Olib ketishga tayyor'
      case 'preparing':
        return 'Buyurtma tayyorlanmoqda'
      case 'delivering':
        return 'Buyurtma yo\'lda'
      case 'completed':
        return 'Buyurtma yakunlandi'
      case 'cancelled':
      case 'rejected':
        return 'Buyurtma bekor qilindi'
      default:
        return 'Buyurtma qabul qilindi'
    }
  })()

  const readyUntil = order?.ready_until || order?.pickup_time
  const formattedReady = formatTimeOnly(readyUntil)
  const heroSubtitle = isDelivery
    ? (order?.delivery_address ? `Yetkazib berish manzili: ${order.delivery_address}` : 'Yetkazib berish jarayoni')
    : (formattedReady ? `Iltimos, buyurtmani ${formattedReady} gacha olib keting` : "Buyurtmani vaqtida olib keting")

  const orderPhotoUrl = resolveOrderItemImageUrl(order)
  const pickupCode = order?.booking_code || order?.pickup_code
  const showPickupPanel = !isDelivery && pickupCode
  const rescueDiscount = Number(order?.discount_amount ?? order?.discount ?? 0)
  const showDiscount = Number.isFinite(rescueDiscount) && rescueDiscount > 0
  const hasDeliveryInfo = Boolean(
    order.delivery_address ||
    order.phone ||
    order.delivery_notes ||
    order.pickup_address ||
    order.pickup_time
  )
  const hasStoreInfo = Boolean(order.store_name || order.store_address || order.store_phone)

  const headerId = order?.order_id || order?.booking_id || orderId

  return (
    <div className={`order-details-page ${showPickupPanel ? 'with-pickup-panel' : ''}`}>
      <header className="order-confirmation-header">
        <button
          type="button"
          className="order-confirmation-btn"
          onClick={() => navigate(-1)}
          aria-label="Orqaga"
        >
          <ChevronLeft size={18} strokeWidth={2.2} />
        </button>
        <div className="order-confirmation-center">
          <span className="order-confirmation-label">Buyurtma tasdiqlash</span>
          <span className="order-confirmation-id">ID #{headerId}</span>
        </div>
        <button
          type="button"
          className="order-confirmation-btn ghost"
          onClick={() => window.Telegram?.WebApp?.showAlert?.('Buyurtma ma\'lumotlari yangilanmoqda')}
          aria-label="Ko'proq"
        >
          <MoreHorizontal size={18} strokeWidth={2} />
        </button>
      </header>

      <main className="order-confirmation-content">
        {isSyncing && (
          <div className="order-sync">Yangilanmoqda...</div>
        )}

        {isCancelled && (
          <div className="order-alert danger">
            <strong>{fulfillmentStatus === 'rejected' ? 'Buyurtma rad etildi' : 'Buyurtma bekor qilindi'}</strong>
            <p>Agar savollaringiz bo'lsa, qo'llab-quvvatlashga yozing.</p>
          </div>
        )}

        {paymentNotice && (
          <div className={`order-alert ${paymentNotice.tone}`}>
            <div className="order-alert-icon">{paymentNotice.icon}</div>
            <div className="order-alert-content">
              <strong>{paymentNotice.title}</strong>
              <p>{paymentNotice.text}</p>
            </div>
            {paymentNotice.showActions && showPayButton && (
              <button
                className={`order-alert-btn ${isPayPrimary ? 'primary' : 'ghost'}`}
                onClick={handlePayOnline}
              >
                {payButtonLabel}
              </button>
            )}
          </div>
        )}

        <section className="order-hero">
          <h1>{heroTitle}</h1>
          <p>{heroSubtitle}</p>

          <div className="order-hero-progress">
            <div className="order-hero-line">
              <div
                className="order-hero-line-fill"
                style={{ width: `${statusSteps.length > 1 ? (activeStepIndex / (statusSteps.length - 1)) * 100 : 0}%` }}
              ></div>
            </div>
            <div className="order-hero-steps">
              {statusSteps.map((step, idx) => (
                <div key={step.key} className="order-hero-step">
                  <span className={`order-hero-dot ${idx <= activeStepIndex ? 'active' : ''}`}></span>
                  <span className={`order-hero-label ${idx === activeStepIndex ? 'current' : ''}`}>
                    {step.label}
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div className="order-hero-meta">
            <span className="order-hero-chip" style={{ background: statusInfo.bg, color: statusInfo.color }}>
              {statusInfo.text}
            </span>
            {showPaymentChip && (
              <span className="order-hero-chip outline">{paymentStatusLabel}</span>
            )}
          </div>
        </section>

        {hasStoreInfo && (
          <section className="order-merchant">
            <div className="order-merchant-header">
              <div>
                <h2>{order.store_name || "Do'kon"}</h2>
                <p>{order.store_address || 'Manzil ko\'rsatilmagan'}</p>
              </div>
              {order.store_phone && (
                <a className="order-merchant-call" href={`tel:${phoneLink(order.store_phone)}`}>
                  <Phone size={16} strokeWidth={2} />
                </a>
              )}
            </div>
            <div className="order-merchant-map">
              <div className="order-merchant-dot"></div>
              <span>Xarita</span>
            </div>
          </section>
        )}

        {hasDeliveryInfo && (
          <section className="order-info">
            <h3>{isDelivery ? 'Yetkazib berish' : 'Olib ketish'}</h3>
            <div className="order-info-card">
              {order.delivery_address && (
                <div className="order-info-row">
                  <span>Manzil</span>
                  <strong>{order.delivery_address}</strong>
                </div>
              )}
              {order.phone && (
                <div className="order-info-row">
                  <span>Telefon</span>
                  <strong>{formatPhone(order.phone)}</strong>
                </div>
              )}
              {order.delivery_notes && (
                <div className="order-info-row">
                  <span>Izoh</span>
                  <strong>{order.delivery_notes}</strong>
                </div>
              )}
              {order.pickup_address && (
                <div className="order-info-row">
                  <span>Manzil</span>
                  <strong>{order.pickup_address}</strong>
                </div>
              )}
              {order.pickup_time && (
                <div className="order-info-row">
                  <span>Vaqt</span>
                  <strong>{formatDate(order.pickup_time)}</strong>
                </div>
              )}
            </div>
          </section>
        )}

        <section className="order-selection">
          <div className="order-selection-head">
            <h3>Tanlovingiz</h3>
            <span>{totalUnits} ta</span>
          </div>
          <div className="order-selection-list">
            {order.items && order.items.length > 0 ? (
              order.items.map((item, idx) => {
                const itemPhoto = resolveOrderItemImageUrl(item)
                const itemTitle = item.offer_title || item.title || 'Mahsulot'
                const itemTotal = Number(item.price || 0) * Number(item.quantity || 0)
                return (
                  <div key={idx} className="order-selection-item">
                    <div className="order-selection-thumb">
                      {itemPhoto ? (
                        <img
                          src={itemPhoto}
                          alt={itemTitle}
                          loading="lazy"
                          decoding="async"
                          onError={(e) => {
                            e.target.style.display = 'none'
                          }}
                        />
                      ) : (
                        <span>{itemTitle.trim().charAt(0).toUpperCase()}</span>
                      )}
                    </div>
                    <div className="order-selection-body">
                      <div className="order-selection-row">
                        <p>{itemTitle}</p>
                        <strong>{formatMoney(itemTotal)} so'm</strong>
                      </div>
                      <span>{item.quantity} x {formatMoney(item.price)} so'm</span>
                    </div>
                  </div>
                )
              })
            ) : (
              <div className="order-selection-item">
                <div className="order-selection-thumb">
                  {orderPhotoUrl ? (
                    <img
                      src={orderPhotoUrl}
                      alt={order.offer_title}
                      loading="lazy"
                      decoding="async"
                      onError={(e) => {
                        e.target.style.display = 'none'
                      }}
                    />
                  ) : (
                    <span>{(order.offer_title || 'B').trim().charAt(0).toUpperCase()}</span>
                  )}
                </div>
                <div className="order-selection-body">
                  <div className="order-selection-row">
                    <p>{order.offer_title}</p>
                    <strong>{formatMoney(totalWithDelivery)} so'm</strong>
                  </div>
                  <span>{order.quantity || 1} dona</span>
                </div>
              </div>
            )}
          </div>
        </section>

        <section className="order-summary">
          <div className="order-summary-row">
            <span>Mahsulotlar</span>
            <strong>{formatMoney(itemsSubtotal)} so'm</strong>
          </div>
          {deliveryFee > 0 && (
            <div className="order-summary-row">
              <span>Yetkazib berish</span>
              <strong>{formatMoney(deliveryFee)} so'm</strong>
            </div>
          )}
          {showDiscount && (
            <div className="order-summary-row discount">
              <span>Tejash</span>
              <strong>-{formatMoney(rescueDiscount)} so'm</strong>
            </div>
          )}
          <div className="order-summary-total">
            <span>Jami</span>
            <strong>{formatMoney(totalWithDelivery)} so'm</strong>
          </div>
          <div className="order-summary-meta">
            <span>To'lov usuli</span>
            <strong>{paymentMethodLabels[order.payment_method] || 'Naqd'}</strong>
          </div>
          {isDelivery && (
            <div className="order-summary-note">
              Yetkazib berish to'lovi buyurtma qabul qilinganda kuryerga alohida to'lanadi.
            </div>
          )}
        </section>

        <div className="order-terms">
          <button
            type="button"
            onClick={() => window.Telegram?.WebApp?.openTelegramLink?.('https://t.me/fudly_support')}
          >
            Shartlar va qo'llab-quvvatlash
          </button>
        </div>
      </main>

      {showPickupPanel && (
        <div className="pickup-panel">
          <div className="pickup-code-card">
            <div>
              <span className="pickup-code-label">Olib ketish kodi</span>
              <span className="pickup-code-value">{pickupCode}</span>
            </div>
            <div className="pickup-code-icon">
              <QrCode size={22} strokeWidth={1.6} />
            </div>
          </div>
          <div className="pickup-actions">
            <button className="pickup-btn primary" onClick={handleGetDirections}>
              Yo'nalish
            </button>
            <button className="pickup-btn ghost" onClick={handleOpenReceipt}>
              Chek
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

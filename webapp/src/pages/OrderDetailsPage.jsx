import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ChevronLeft, MoreHorizontal, Phone, QrCode } from 'lucide-react'
import apiClient, { API_BASE_URL } from '../api/client'
import { resolveOrderItemImageUrl } from '../utils/imageUtils'
import { calcQuantity, calcDeliveryFee, calcTotalPrice } from '../utils/orderMath'
import {
  deriveDisplayStatus,
  displayStatusText,
  normalizeOrderStatus,
  normalizePaymentStatus,
  paymentStatusText,
  resolveOrderType,
  statusText,
} from '../utils/orderStatus'
import { readPendingPayment, clearPendingPayment } from '../utils/pendingPayment'
import { getUserId } from '../utils/auth'
import './OrderDetailsPage.css'

export default function OrderDetailsPage() {
  const { orderId } = useParams()
  const navigate = useNavigate()
  const [order, setOrder] = useState(null)
  const [timeline, setTimeline] = useState(null)
  const [timelineLoading, setTimelineLoading] = useState(false)
  const [loading, setLoading] = useState(true)
  const [isSyncing, setIsSyncing] = useState(false)
  const [error, setError] = useState(null)
  const [showQr, setShowQr] = useState(false)
  const [qrPayload, setQrPayload] = useState(null)
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

  useEffect(() => {
    setShowQr(false)
    setQrPayload(null)
  }, [orderId])

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
        qr_code: statusPayload.qr_code,
      }

      if (allowEnrich && !enrichmentAttemptedRef.current && foundOrder.items.length === 0) {
        enrichmentAttemptedRef.current = true
        try {
          const response = await apiClient.getOrders({
            force: true,
            limit: 100,
            offset: 0,
            include_meta: true,
          })
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

  const loadOrderTimeline = useCallback(async (silent = false) => {
    const numericOrderId = Number(orderId)
    if (!Number.isFinite(numericOrderId)) return

    if (!silent) {
      setTimelineLoading(true)
    }

    try {
      const timelineData = await apiClient.getOrderTimeline(numericOrderId)
      setTimeline(timelineData)
    } catch (err) {
      console.warn('Failed to load order timeline:', err)
      if (!silent) {
        setTimeline(null)
      }
    } finally {
      if (!silent) {
        setTimelineLoading(false)
      }
    }
  }, [orderId])

  useEffect(() => {
    loadOrderDetails({ allowEnrich: true, silent: false })
    loadOrderTimeline(false)
    const interval = setInterval(() => {
      loadOrderDetails({ allowEnrich: false, silent: true })
      loadOrderTimeline(true)
    }, 15000)
    return () => clearInterval(interval)
  }, [orderId, loadOrderDetails, loadOrderTimeline])

  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        loadOrderDetails({ allowEnrich: false, silent: true })
        loadOrderTimeline(true)
      }
    }
    window.addEventListener('focus', handleVisibility)
    document.addEventListener('visibilitychange', handleVisibility)
    return () => {
      window.removeEventListener('focus', handleVisibility)
      document.removeEventListener('visibilitychange', handleVisibility)
    }
  }, [loadOrderDetails, loadOrderTimeline])

  useEffect(() => {
    if (!userId) return

    const buildWsUrl = async () => {
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
      try {
        const token = await apiClient.getWsToken()
        if (token) {
          params.set('ws_token', token)
        }
      } catch (error) {
        console.warn('Could not fetch WS token:', error)
      }
      const query = params.toString()
      return `${wsEndpoint}${query ? `?${query}` : ''}`
    }

    let ws
    let cancelled = false

    const connect = async () => {
      const wsUrl = await buildWsUrl()
      if (!wsUrl || cancelled) return

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
              loadOrderTimeline(true)
            }
          }
        } catch (error) {
          console.warn('Failed to parse order update:', error)
        }
      }
    }

    connect()

    return () => {
      cancelled = true
      if (ws) {
        ws.close()
      }
    }
  }, [orderId, userId, loadOrderDetails, loadOrderTimeline])

  const toNumeric = (value) => {
    if (typeof value === 'string') {
      const cleaned = value.replace(/[^\d.-]/g, '')
      return Number(cleaned || 0)
    }
    return Number(value || 0)
  }

  const toMoneyInt = (value) => {
    const numeric = toNumeric(value)
    if (!Number.isFinite(numeric)) return 0
    return Math.round(numeric + Number.EPSILON)
  }

  const formatMoney = (value) => {
    return toMoneyInt(value).toLocaleString('uz-UZ')
  }

  const getStatusInfo = (status, orderType) => {
    const statusMap = {
      pending: { color: 'var(--color-warning)', bg: 'var(--color-warning-light)' },
      preparing: { color: 'var(--color-primary)', bg: 'var(--color-primary-light)' },
      ready: { color: 'var(--color-success)', bg: 'var(--color-success-light)' },
      delivering: { color: 'var(--color-primary)', bg: 'var(--color-primary-light)' },
      completed: { color: 'var(--color-success)', bg: 'var(--color-success-light)' },
      cancelled: { color: 'var(--color-error)', bg: 'var(--color-error-light)' },
      rejected: { color: 'var(--color-error)', bg: 'var(--color-error-light)' },
      awaiting_payment: { color: 'var(--color-warning)', bg: 'var(--color-warning-light)' },
      awaiting_proof: { color: 'var(--color-warning)', bg: 'var(--color-warning-light)' },
      proof_submitted: { color: 'var(--color-primary)', bg: 'var(--color-primary-light)' },
      payment_rejected: { color: 'var(--color-error)', bg: 'var(--color-error-light)' },
    }
    const palette = statusMap[status] || { color: 'var(--color-text-secondary)', bg: 'var(--color-bg-tertiary)' }
    return { ...palette, text: displayStatusText(status, 'uz', orderType) }
  }

  const getPaymentStatusLabel = (status) => {
    return paymentStatusText(status, 'uz')
  }

  const TIMELINE_TIMEZONE = 'Asia/Tashkent'
  const UZ_MONTHS_SHORT = ['yan', 'fev', 'mar', 'apr', 'may', 'iyn', 'iyl', 'avg', 'sen', 'okt', 'noy', 'dek']
  const hasTimezoneHint = (raw) => /[zZ]|[+-]\d{2}:?\d{2}$/.test(raw)

  const formatTimeOnly = (value) => {
    if (!value) return ''
    if (typeof value === 'string') {
      if (value.includes('T') || hasTimezoneHint(value)) {
        const date = new Date(value)
        if (!Number.isNaN(date.getTime())) {
          return new Intl.DateTimeFormat('uz-UZ', {
            timeZone: TIMELINE_TIMEZONE,
            hour: '2-digit',
            minute: '2-digit',
            hour12: false,
          }).format(date)
        }
      }
      const match = value.match(/(\d{1,2}:\d{2})/)
      if (match) return match[1]
      return value
    }
    return String(value)
  }

  const formatTimelineTime = (value) => {
    if (!value) return ''
    const raw = String(value).trim()
    const localMatch = raw.match(/(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/)
    if (localMatch && !hasTimezoneHint(raw)) {
      const day = localMatch[3]
      const monthIndex = Number(localMatch[2]) - 1
      const month = UZ_MONTHS_SHORT[monthIndex] || localMatch[2]
      const timeLabel = `${localMatch[4]}:${localMatch[5]}`
      return `${day}-${month}, ${timeLabel}`
    }
    const date = new Date(raw)
    if (Number.isNaN(date.getTime())) return raw
    return new Intl.DateTimeFormat('uz-UZ', {
      timeZone: TIMELINE_TIMEZONE,
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).format(date)
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

  const handleSupport = () => {
    const link = 'https://t.me/fudly_support'
    if (window.Telegram?.WebApp?.openTelegramLink) {
      window.Telegram?.WebApp?.openTelegramLink?.(link)
      return
    }
    window.open(link, '_blank', 'noopener,noreferrer')
  }

  const handleShowQr = async () => {
    const existingQr = order?.qr_code || qrPayload?.qr_code
    if (existingQr) {
      setShowQr(true)
      return
    }

    const numericOrderId = Number(orderId)
    if (!Number.isFinite(numericOrderId)) {
      window.Telegram?.WebApp?.showAlert?.('QR kod topilmadi')
      return
    }

    try {
      const data = await apiClient.getOrderQR(numericOrderId)
      if (data?.qr_code) {
        setQrPayload(data)
        setShowQr(true)
      } else {
        window.Telegram?.WebApp?.showAlert?.('QR kod topilmadi')
      }
    } catch (err) {
      console.warn('Failed to load QR:', err)
      window.Telegram?.WebApp?.showAlert?.('QR kod topilmadi')
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
        <header className="app-header">
          <div className="app-header-inner">
            <div className="app-header-spacer" aria-hidden="true" />
            <div className="app-header-title">
              <h1 className="app-header-title-text">Buyurtma #{orderId}</h1>
            </div>
            <div className="app-header-spacer" aria-hidden="true" />
          </div>
        </header>
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

  const explicitItemsTotal = toMoneyInt(order?.items_total ?? order?.itemsTotal ?? 0)
  const hasItemBreakdown = Array.isArray(order.items) && order.items.length > 0
  const rawItemsSubtotal = hasItemBreakdown
    ? order.items.reduce((sum, item) => {
        const lineTotal = toNumeric(item?.total_price ?? 0)
        if (Number.isFinite(lineTotal) && lineTotal > 0) {
          return sum + toMoneyInt(lineTotal)
        }
        const price = toNumeric(item?.price ?? item?.discount_price ?? 0)
        const qty = toNumeric(item?.quantity ?? 0)
        if (!Number.isFinite(price) || !Number.isFinite(qty)) return sum
        return sum + toMoneyInt(price * qty)
      }, 0)
    : 0
  const itemsSubtotal = rawItemsSubtotal > 0 ? rawItemsSubtotal : explicitItemsTotal
  const rawTotal = (() => {
    const candidates = isDelivery
      ? [order?.total_with_delivery, order?.total_price, order?.total_amount, order?.total, order?.items_total]
      : [order?.total_price, order?.total_amount, order?.total, order?.items_total, order?.total_with_delivery]
    for (const value of candidates) {
      const numeric = toNumeric(value)
      if (Number.isFinite(numeric) && numeric > 0) return numeric
    }
    return 0
  })()
  const rawTotalRounded = toMoneyInt(rawTotal)
  const deliveryFee = isDelivery
    ? toMoneyInt(calcDeliveryFee(rawTotal || null, itemsSubtotal, {
      deliveryFee: order?.delivery_fee,
      isDelivery,
    }))
    : 0
  const rescueDiscount = toMoneyInt(order?.discount_amount ?? order?.discount ?? 0)
  const showDiscount = Number.isFinite(rescueDiscount) && rescueDiscount > 0
  const derivedTotal = Math.max(0, itemsSubtotal + deliveryFee - (showDiscount ? rescueDiscount : 0))
  const totalDue = (() => {
    if (rawTotalRounded > 0 && derivedTotal > 0 && Math.abs(rawTotalRounded - derivedTotal) <= 1) {
      return derivedTotal
    }
    return rawTotalRounded > 0 ? rawTotalRounded : derivedTotal
  })()
  const payableTotal = Number(
    totalDue
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
        { key: 'preparing', label: 'Tayyorlanmoqda' },
        { key: 'ready', label: 'Tayyor' },
        { key: 'delivering', label: "Yo'lda" },
        { key: 'completed', label: 'Yetkazildi' },
      ]
    : [
        { key: 'pending', label: 'Tasdiqlandi' },
        { key: 'preparing', label: 'Tayyorlanmoqda' },
        { key: 'ready', label: 'Olib ketish' },
        { key: 'completed', label: 'Berildi' },
      ]

  const activeStepIndex = Math.max(0, statusSteps.findIndex(step => step.key === displayFulfillmentStatus))
  const heroTitle = (() => {
    switch (displayFulfillmentStatus) {
      case 'ready':
        return isDelivery ? 'Yetkazib berishga tayyor' : 'Olib ketishga tayyor'
      case 'preparing':
        return 'Buyurtma tayyorlanmoqda'
      case 'delivering':
        return "Buyurtma yo'lda"
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
    : (formattedReady ? `Iltimos, buyurtmani ${formattedReady} gacha olib keting` : 'Buyurtmani vaqtida olib keting')

  const orderPhotoUrl = resolveOrderItemImageUrl(order)
  const pickupCode = order?.booking_code || order?.pickup_code
  const showPickupPanel = !isDelivery && pickupCode
  const hasDeliveryInfo = Boolean(
    order.delivery_address ||
    order.phone ||
    order.delivery_notes ||
    order.pickup_address ||
    order.pickup_time
  )
  const hasStoreInfo = Boolean(order.store_name || order.store_address || order.store_phone)

  const timelineItems = Array.isArray(timeline?.timeline) ? timeline.timeline : []
  const showTimeline = timelineLoading || timelineItems.length > 0
  const orderTypeLabel = isDelivery ? 'Yetkazib berish' : 'Olib ketish'

  const qrImage = order?.qr_code || qrPayload?.qr_code
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
          onClick={() => window.Telegram?.WebApp?.showAlert?.("Buyurtma ma'lumotlari yangilanmoqda")}
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
            <span className="order-hero-chip outline">{orderTypeLabel}</span>
            {showPaymentChip && (
              <span className="order-hero-chip outline">{paymentStatusLabel}</span>
            )}
          </div>
        </section>
        {showTimeline && (
          <section className="order-timeline">
            <div className="order-timeline-header">
              <div>
                <h3>Buyurtma holati</h3>
                {formattedReady && (
                  <span className="order-timeline-estimate">
                    {isDelivery
                      ? `Taxminiy vaqt: ${formattedReady}`
                      : `Tayyor vaqt: ${formattedReady}`}
                  </span>
                )}
              </div>
              {timelineLoading && <span className="order-timeline-loading">Yangilanmoqda...</span>}
            </div>
            <div className="order-timeline-list">
              {timelineLoading && timelineItems.length === 0 ? (
                <div className="order-timeline-empty">Ma'lumotlar yangilanmoqda...</div>
              ) : (
                timelineItems.map((item, index) => {
                  const eventStatus = item.status || item.order_status || item.type || ''
                  const rawLabel = statusText(eventStatus, 'uz', orderType)
                  const displayStatus = /[А-Яа-яЁё]/.test(rawLabel) ? 'Buyurtma yangilandi' : rawLabel
                  const timestamp =
                    item.created_at ||
                    item.time ||
                    item.timestamp ||
                    item.date
                  const timeLabel = formatTimelineTime(timestamp)
                  const rawMessage = item.message || item.note || item.description || ''
                  const message = /[А-Яа-яЁё]/.test(rawMessage) ? '' : rawMessage

                  return (
                    <div className="order-timeline-item" key={`${eventStatus}-${timestamp}-${index}`}>
                      <span className="order-timeline-marker"></span>
                      <div className="order-timeline-row">
                        <div className="order-timeline-status">{displayStatus}</div>
                        <div className="order-timeline-time">{timeLabel}</div>
                      </div>
                      {message && (
                        <div className="order-timeline-message">{message}</div>
                      )}
                    </div>
                  )
                })
              )}
            </div>
          </section>
        )}

        {hasStoreInfo && (
          <section className="order-merchant">
            <div className="order-merchant-header">
              <div>
                <h2>{order.store_name || "Do'kon"}</h2>
                <p>{order.store_address || "Manzil ko'rsatilmagan"}</p>
                {order.store_phone && (
                  <span className="order-merchant-phone">{formatPhone(order.store_phone)}</span>
                )}
              </div>
              {order.store_phone && (
                <a
                  className="order-merchant-call"
                  href={`tel:${phoneLink(order.store_phone)}`}
                  aria-label="Qo'ng'iroq qilish"
                >
                  <Phone size={18} strokeWidth={2} />
                </a>
              )}
            </div>
            <div className="order-merchant-map">
              <span>Manzil xaritasi</span>
              <span className="order-merchant-dot"></span>
            </div>
          </section>
        )}

        {hasDeliveryInfo && (
          <section className="order-info">
            <h3>{isDelivery ? 'Yetkazib berish' : 'Olib ketish'}</h3>
            <div className="order-info-card">
              {isDelivery ? (
                <>
                  <div className="order-info-row">
                    <span>Manzil</span>
                    <strong>{order.delivery_address || '-'}</strong>
                  </div>
                  {order.phone && (
                    <div className="order-info-row">
                      <span>Aloqa</span>
                      <strong>{formatPhone(order.phone)}</strong>
                    </div>
                  )}
                  {order.delivery_notes && (
                    <div className="order-info-row">
                      <span>Izoh</span>
                      <strong>{order.delivery_notes}</strong>
                    </div>
                  )}
                </>
              ) : (
                <>
                  <div className="order-info-row">
                    <span>Olib ketish manzili</span>
                    <strong>{order.pickup_address || order.store_address || '-'}</strong>
                  </div>
                  {order.pickup_time && (
                    <div className="order-info-row">
                      <span>Olib ketish vaqti</span>
                      <strong>{formatTimeOnly(order.pickup_time)}</strong>
                    </div>
                  )}
                </>
              )}
            </div>
          </section>
        )}

        <section className="order-selection">
          <div className="order-selection-head">
            <h3>Tanlanganlar</h3>
            <span>{totalUnits} ta</span>
          </div>
          <div className="order-selection-list">
            {hasItemBreakdown ? (
              order.items.map((item, index) => {
                const itemQty = Number(item?.quantity || 1)
                const itemTitle = item?.offer_title || item?.title || item?.name || 'Mahsulot'
                const itemPrice = Number(item?.price ?? item?.discount_price ?? 0)
                const itemTotal = Number(item?.total_price ?? (itemPrice * itemQty))
                const itemImage = resolveOrderItemImageUrl(item) || orderPhotoUrl

                return (
                  <div className="order-selection-item" key={`${itemTitle}-${index}`}>
                    <div className="order-selection-thumb">
                      {itemImage ? (
                        <img src={itemImage} alt={itemTitle} />
                      ) : (
                        <span>{itemTitle.slice(0, 1)}</span>
                      )}
                    </div>
                    <div className="order-selection-body">
                      <div className="order-selection-row">
                        <p>{itemTitle}</p>
                        <strong>{formatMoney(itemTotal)} UZS</strong>
                      </div>
                      <span>{itemQty} ta</span>
                    </div>
                  </div>
                )
              })
            ) : (
              <div className="order-selection-item">
                <div className="order-selection-thumb">
                  {orderPhotoUrl ? (
                    <img src={orderPhotoUrl} alt={order.offer_title || 'Buyurtma'} />
                  ) : (
                    <span>{(order.offer_title || 'B').slice(0, 1)}</span>
                  )}
                </div>
                <div className="order-selection-body">
                  <div className="order-selection-row">
                    <p>{order.offer_title || 'Buyurtma'}</p>
                    <strong>{formatMoney(totalDue)} UZS</strong>
                  </div>
                  <span>{totalUnits} ta</span>
                </div>
              </div>
            )}
          </div>
        </section>

        <section className="order-summary">
          <div className="order-summary-row">
            <span>Mahsulotlar</span>
            <strong>{formatMoney(itemsSubtotal)} UZS</strong>
          </div>
          {isDelivery && (
            <div className="order-summary-row">
              <span>Yetkazib berish</span>
              <strong>{formatMoney(deliveryFee)} UZS</strong>
            </div>
          )}
          {showDiscount && (
            <div className="order-summary-row discount">
              <span>Chegirma</span>
              <strong>-{formatMoney(rescueDiscount)} UZS</strong>
            </div>
          )}
          <div className="order-summary-total">
            <span>Jami to'lov</span>
            <strong>{formatMoney(totalDue)} UZS</strong>
          </div>
          <div className="order-summary-meta">
            <span>To'lov usuli</span>
            <strong>{paymentMethodLabels[order.payment_method] || '---'}</strong>
          </div>
          {order.delivery_notes && (
            <div className="order-summary-note">
              Izoh: {order.delivery_notes}
            </div>
          )}
        </section>

        <div className="order-terms">
          <button type="button" onClick={handleSupport}>
            Qoidalar va qo'llab-quvvatlash
          </button>
        </div>
      </main>

      {showPickupPanel && (
        <div className="pickup-panel">
          <div className="pickup-code-card">
            <div>
              <span className="pickup-code-label">Olib ketish kodi</span>
              <strong className="pickup-code-value">{pickupCode}</strong>
            </div>
            <button
              type="button"
              className="pickup-code-icon"
              onClick={handleShowQr}
              aria-label="QR kod"
            >
              <QrCode size={20} strokeWidth={2} />
            </button>
          </div>
          <div className="pickup-actions">
            <button type="button" className="pickup-btn primary" onClick={handleGetDirections}>
              Yo'nalish
            </button>
            <button type="button" className="pickup-btn ghost" onClick={handleOpenReceipt}>
              Chek
            </button>
          </div>
        </div>
      )}

      {showQr && (
        <div className="qr-modal" onClick={() => setShowQr(false)}>
          <div className="qr-modal-card" onClick={(event) => event.stopPropagation()}>
            <button
              type="button"
              className="qr-modal-close"
              onClick={() => setShowQr(false)}
              aria-label="Yopish"
            >
              X
            </button>
            <h3>Olib ketish kodi</h3>
            <p>Buyurtmani olish uchun kassada ko'rsating.</p>
            {qrImage ? (
              <img className="qr-modal-code" src={qrImage} alt="QR" />
            ) : (
              <div className="qr-modal-code placeholder">QR kod mavjud emas</div>
            )}
            {pickupCode && <div className="qr-modal-text">{pickupCode}</div>}
          </div>
        </div>
      )}
    </div>
  )
}


import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, ChevronLeft, Info, MessageCircle } from 'lucide-react'
import api from '../api/client'
import { useCart } from '../context/CartContext'
import { useToast } from '../context/ToastContext'
import BottomNav from '../components/BottomNav'
import PullToRefresh from '../components/PullToRefresh'
import { usePullToRefresh } from '../hooks/usePullToRefresh'
import { resolveImageUrl } from '../utils/imageUtils'
import { calcQuantity, calcDeliveryFee, calcTotalPrice } from '../utils/orderMath'
import { deriveDisplayStatus as deriveStatus, displayStatusText, normalizeOrderStatus, resolveOrderType } from '../utils/orderStatus'
import './YanaPage.css'
import './OrdersPage.css'

const ACTIVE_STATUSES = new Set([
  'pending',
  'confirmed',
  'preparing',
  'ready',
  'delivering',
  'awaiting_payment',
  'awaiting_proof',
  'proof_submitted',
  'payment_rejected',
])

const COMPLETED_STATUSES = new Set(['completed', 'cancelled', 'rejected'])

const CANCELABLE_STATUSES = new Set(['pending'])

const TAB_ACTIVE = 'active'
const TAB_HISTORY = 'history'

function OrdersPage() {
  const navigate = useNavigate()
  const { cartCount } = useCart()
  const { toast } = useToast()
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [cancelingOrderId, setCancelingOrderId] = useState(null)
  const [activeTab, setActiveTab] = useState(TAB_ACTIVE)

  const normalizeOrder = (order) => {
    const displayStatus = deriveStatus(order)
    const normalizedStatus = normalizeOrderStatus(order?.order_status || order?.status || 'pending')
    return {
      ...order,
      status: displayStatus,
      order_status: normalizedStatus || 'pending',
    }
  }

  const loadOrders = async (force = false) => {
    if (!force) setLoading(true)
    try {
      const response = await api.getOrders({ force })
      const allOrders = [
        ...(response.orders || []),
        ...(response.bookings || []),
      ].map(normalizeOrder)

      setOrders(allOrders)
    } catch (error) {
      console.error('Error loading orders:', error)
      setOrders([])
      toast.error("Buyurtmalarni yuklab bo'lmadi")
    } finally {
      if (!force) setLoading(false)
    }
  }

  useEffect(() => {
    loadOrders()
  }, [])

  useEffect(() => {
    const interval = setInterval(() => {
      if (orders.some(o => ACTIVE_STATUSES.has(o.status))) {
        loadOrders(true)
      }
    }, 10000)

    return () => clearInterval(interval)
  }, [orders])

  const toNumeric = (value) => {
    if (typeof value === 'string') {
      const cleaned = value.replace(/[^\d.-]/g, '')
      return Number(cleaned || 0)
    }
    return Number(value || 0)
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

  const getOrderQuantity = (order) => {
    const items = Array.isArray(order.items) ? order.items : []
    const explicitQty = Number(order.quantity || 0)
    if (explicitQty) return explicitQty
    const itemsQty = calcQuantity(items, item => Number(item?.quantity || 0))
    return itemsQty || 1
  }

  const getOrderSummary = (order) => {
    const items = Array.isArray(order.items) ? order.items : []
    const orderId = order.booking_id || order.order_id || order.id
    const status = order.status || order.order_status
    const createdAt = order.created_at || order.createdAt
    const orderStatus = normalizeOrderStatus(order.order_status || order.status)
    const quantity = getOrderQuantity(order)
    const explicitItemsTotal = toNumeric(order.items_total ?? order.itemsTotal ?? 0)
    const itemsTotal = Number.isFinite(explicitItemsTotal) && explicitItemsTotal > 0
      ? explicitItemsTotal
      : items.reduce((sum, item) => {
          const price = toNumeric(item?.price ?? item?.discount_price ?? 0)
          const qty = toNumeric(item?.quantity ?? 0)
          if (!Number.isFinite(price) || !Number.isFinite(qty)) return sum
          return sum + Math.round(price * qty)
        }, 0)
    const isDelivery = order?.order_type === 'delivery' || order?.delivery_address
    const rawTotal = (() => {
      const candidates = isDelivery
        ? [order.total_with_delivery, order.total_price, order.total_amount, order.total, order.items_total]
        : [order.total_price, order.total_amount, order.total, order.items_total, order.total_with_delivery]
      for (const value of candidates) {
        const numeric = toNumeric(value)
        if (Number.isFinite(numeric) && numeric > 0) return numeric
      }
      return 0
    })()
    const deliveryFee = calcDeliveryFee(rawTotal || null, itemsTotal, {
      deliveryFee: order?.delivery_fee,
      isDelivery,
    })
    const baseTotal = itemsTotal || (rawTotal ? Math.max(0, rawTotal - deliveryFee) : 0)
    const totalPrice = rawTotal > 0 ? rawTotal : calcTotalPrice(itemsTotal, deliveryFee)
    const unitPrice = quantity
      ? Math.round((baseTotal || 0) / quantity)
      : (items[0]?.price ?? items[0]?.discount_price ?? 0)
    const offerTitle = order.offer_title || order.title || items[0]?.title || items[0]?.offer_title || 'Buyurtma'
    const storeName = order.store_name || items[0]?.store_name || "Do'kon"
    const bookingCode = order.booking_code || order.pickup_code
    const photoUrl = resolveImageUrl(
      order.offer_photo,
      order.offer_photo_url,
      order.offer_photo_id,
      order.photo,
      order.photo_id,
      items[0]?.offer_photo_url,
      items[0]?.photo_url,
      items[0]?.image_url,
      items[0]?.photo,
      items[0]?.photo_id,
      items[0]?.offer_photo,
      items[0]?.offer_photo_id
    )

    return {
      orderId,
      status,
      orderStatus,
      createdAt,
      quantity,
      totalPrice,
      unitPrice,
      offerTitle,
      storeName,
      bookingCode,
      photoUrl,
      isDelivery,
    }
  }

  const formatOrderDate = (dateStr) => {
    if (!dateStr) return ''
    const raw = String(dateStr)
    const date = new Date(raw)
    if (!Number.isNaN(date.getTime())) {
      const months = ['yan', 'fev', 'mar', 'apr', 'may', 'iyn', 'iyl', 'avg', 'sen', 'okt', 'noy', 'dek']
      const day = String(date.getDate()).padStart(2, '0')
      return `${day} ${months[date.getMonth()]}`
    }

    const monthMap = {
      'янв': 'yan',
      'фев': 'fev',
      'мар': 'mar',
      'апр': 'apr',
      'май': 'may',
      'июн': 'iyn',
      'июл': 'iyl',
      'авг': 'avg',
      'сен': 'sen',
      'сент': 'sen',
      'окт': 'okt',
      'ноя': 'noy',
      'дек': 'dek',
    }
    const match = raw.toLowerCase().match(/(\d{1,2})\s*[-.\s]*\s*([а-яё]+)/i)
    if (match) {
      const day = match[1].padStart(2, '0')
      const key = match[2].slice(0, 4)
      const mapped = monthMap[key]
      if (mapped) {
        return `${day} ${mapped}`
      }
    }
    return raw
  }

  const formatSum = (value) => {
    const numeric = toNumeric(value)
    if (!Number.isFinite(numeric)) return '0'
    const rounded = Math.round(numeric + Number.EPSILON)
    return rounded.toLocaleString('uz-UZ')
  }

  const getProgressSteps = (orderType) => {
    if (orderType === 'delivery') {
      return [
        {
          label: 'Tasdiqlandi',
          statuses: ['pending', 'confirmed', 'awaiting_payment', 'awaiting_proof', 'proof_submitted', 'payment_rejected'],
        },
        { label: 'Tayyorlanmoqda', statuses: ['preparing'] },
        { label: 'Tayyor', statuses: ['ready'] },
        { label: "Yo'lda", statuses: ['delivering'] },
        { label: 'Yetkazildi', statuses: ['completed'] },
      ]
    }

    return [
      {
        label: 'Tasdiqlandi',
        statuses: ['pending', 'confirmed', 'awaiting_payment', 'awaiting_proof', 'proof_submitted', 'payment_rejected'],
      },
      { label: 'Tayyorlanmoqda', statuses: ['preparing'] },
      { label: 'Olib ketish', statuses: ['ready'] },
      { label: 'Berildi', statuses: ['completed'] },
    ]
  }

  const getProgressIndex = (status, steps) => {
    const normalized = normalizeOrderStatus(status)
    const index = steps.findIndex(step => step.statuses.includes(normalized))
    if (index === -1) return 0
    return Math.max(0, index)
  }

  const activeOrders = useMemo(() => (
    orders.filter((order) => {
      const status = normalizeOrderStatus(order?.status || order?.order_status)
      return !COMPLETED_STATUSES.has(status)
    })
  ), [orders])

  const completedOrders = useMemo(() => (
    orders.filter((order) => {
      const status = normalizeOrderStatus(order?.status || order?.order_status)
      return COMPLETED_STATUSES.has(status)
    })
  ), [orders])

  const handleRefresh = async () => {
    await loadOrders(true)
  }

  const { containerRef, isRefreshing, pullDistance, progress } = usePullToRefresh(handleRefresh)

  return (
    <div ref={containerRef} className="yana-page orders-page">
      <PullToRefresh
        isRefreshing={isRefreshing}
        pullDistance={pullDistance}
        progress={progress}
      />

      <header className="orders-topbar">
        <div className="orders-topbar-inner">
          <button
            type="button"
            className="orders-topbar-btn"
            onClick={() => navigate(-1)}
            aria-label="Orqaga"
          >
            <ChevronLeft size={18} strokeWidth={2.2} />
          </button>
          <div className="orders-topbar-center">
            <h1 className="orders-topbar-title">Buyurtmalar</h1>
          </div>
          <button
            type="button"
            className="orders-topbar-btn ghost"
            onClick={() => toast.info('Buyurtmalar bo\'limi yangilanmoqda')}
            aria-label="Ma'lumot"
          >
            <Info size={18} strokeWidth={2} />
          </button>
        </div>
        <div className="orders-tabs">
          <button
            type="button"
            className={`orders-tab ${activeTab === TAB_ACTIVE ? 'active' : ''}`}
            onClick={() => setActiveTab(TAB_ACTIVE)}
          >
            Faol ({activeOrders.length})
          </button>
          <button
            type="button"
            className={`orders-tab ${activeTab === TAB_HISTORY ? 'active' : ''}`}
            onClick={() => setActiveTab(TAB_HISTORY)}
          >
            Tarix
          </button>
        </div>
      </header>

      <main className="orders-content">
        {activeTab === TAB_ACTIVE ? (
          <>
            <section className="orders-section">
              <div className="orders-section-header">
                <h2 className="orders-section-title">Joriy buyurtma</h2>
              </div>
              {loading ? (
                <div className="orders-loading">
                  <div className="orders-spinner"></div>
                  <p>Yuklanmoqda...</p>
                </div>
              ) : activeOrders.length === 0 ? (
                <div className="orders-empty">
                  <div className="orders-empty-icon">*</div>
                  <h3>Faol buyurtmalar yo'q</h3>
                  <p>Yangi buyurtmalar shu yerda ko'rinadi.</p>
                  <button className="orders-empty-btn" onClick={() => navigate('/')}>Xarid qilish</button>
                </div>
              ) : (
                <div className="orders-active-list">
                  {activeOrders.map((order, idx) => {
                    const summary = getOrderSummary(order)
                    const orderType = resolveOrderType(order)
                    const statusInfo = getStatusInfo(summary.status, orderType)
                    const canCancel = CANCELABLE_STATUSES.has(summary.orderStatus)
                    const steps = getProgressSteps(orderType)
                    const progressIndex = getProgressIndex(summary.orderStatus || summary.status, steps)
                    const progressWidth = steps.length > 1
                      ? Math.round((progressIndex / (steps.length - 1)) * 100)
                      : 0

                    return (
                      <div
                        key={summary.orderId || idx}
                        className="order-card"
                        style={{ animationDelay: `${idx * 0.04}s` }}
                      >
                        <div className="order-card-header">
                          <div className={`order-card-thumb ${summary.photoUrl ? 'has-image' : ''}`}>
                            {summary.photoUrl ? (
                              <img
                                src={summary.photoUrl}
                                alt={summary.offerTitle}
                                loading="lazy"
                                decoding="async"
                                onError={(event) => {
                                  event.currentTarget.style.display = 'none'
                                  event.currentTarget.parentElement.classList.remove('has-image')
                                }}
                              />
                            ) : (
                              <span>{summary.offerTitle.trim().charAt(0).toUpperCase()}</span>
                            )}
                          </div>
                          <div className="order-card-main">
                            <div className="order-card-title-row">
                              <h3 className="order-card-title">{summary.storeName}</h3>
                              <span
                                className="order-card-status"
                                style={{ color: statusInfo.color, borderColor: statusInfo.color }}
                              >
                                {statusInfo.text}
                              </span>
                            </div>
                            <div className="order-card-meta">
                              ID: #{summary.orderId} &bull; {summary.quantity} ta
                            </div>
                            <div className="order-card-sub">
                              {formatOrderDate(summary.createdAt)}
                            </div>
                          </div>
                        </div>

                        <div className="order-card-progress">
                          <div className="order-card-progress-track">
                            <div className="order-card-progress-line"></div>
                            <div
                              className="order-card-progress-fill"
                              style={{ width: `${progressWidth}%` }}
                            ></div>
                            <div className="order-card-progress-dots">
                              {steps.map((step, stepIdx) => (
                                <span
                                  key={`${summary.orderId}-step-${stepIdx}`}
                                  className={`order-card-progress-dot ${stepIdx <= progressIndex ? 'active' : ''}`}
                                ></span>
                              ))}
                            </div>
                          </div>
                          <div className="order-card-progress-labels">
                            {steps.map((step, stepIdx) => (
                              <span
                                key={`${summary.orderId}-label-${stepIdx}`}
                                className={stepIdx <= progressIndex ? 'active' : ''}
                              >
                                {step.label}
                              </span>
                            ))}
                          </div>
                        </div>

                        <div className="order-card-actions">
                          <button
                            type="button"
                            className="order-card-primary"
                            onClick={() => summary.orderId && navigate(`/order/${summary.orderId}`)}
                          >
                            Tafsilotlar
                          </button>
                          <button
                            type="button"
                            className="order-card-icon"
                            onClick={() => {
                              const link = 'https://t.me/fudly_support'
                              if (window.Telegram?.WebApp?.openTelegramLink) {
                                window.Telegram.WebApp.openTelegramLink(link)
                              } else {
                                window.open(link, '_blank', 'noopener,noreferrer')
                              }
                            }}
                            aria-label="Qo'llab-quvvatlash"
                          >
                            <MessageCircle size={18} strokeWidth={2} />
                          </button>
                        </div>

                        <div className="order-card-footer">
                          <span className="order-card-price">{formatSum(summary.totalPrice)} so'm</span>
                          <button
                            type="button"
                            className="order-card-more"
                            onClick={() => summary.orderId && navigate(`/order/${summary.orderId}`)}
                          >
                            Batafsil
                            <ArrowRight size={14} strokeWidth={2.2} />
                          </button>
                        </div>

                        {canCancel && (
                          <button
                            type="button"
                            className="order-card-cancel"
                            disabled={cancelingOrderId === summary.orderId}
                            onClick={async () => {
                              const orderId = summary.orderId
                              setCancelingOrderId(orderId)

                              setOrders(prev => prev.map(o =>
                                (o.id || o.booking_id || o.order_id) === orderId
                                  ? { ...o, status: 'cancelled', order_status: 'cancelled' }
                                  : o
                              ))

                              try {
                                await api.cancelOrder(orderId)
                                toast.success('Buyurtma bekor qilindi')
                                setTimeout(() => loadOrders(true), 500)
                              } catch (error) {
                                console.error('Cancel order failed:', error)
                                loadOrders(true)
                                const errorMsg =
                                  error?.response?.data?.detail ||
                                  error?.response?.data?.message ||
                                  error?.message
                                toast.error(errorMsg || 'Bekor qilishda xatolik')
                              } finally {
                                setCancelingOrderId(null)
                              }
                            }}
                          >
                            {cancelingOrderId === summary.orderId ? 'Bekor qilinmoqda...' : 'Bekor qilish'}
                          </button>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </section>

            <section className="orders-section">
              <div className="orders-section-header">
                <h2 className="orders-section-title">Oldingi xaridlar</h2>
              </div>
              {loading ? (
                <div className="orders-loading">
                  <div className="orders-spinner"></div>
                  <p>Yuklanmoqda...</p>
                </div>
              ) : completedOrders.length === 0 ? (
                <div className="orders-empty compact">
                  <h3>Buyurtmalar tarixi bo'sh</h3>
                  <p>Birinchi buyurtmangizni bering!</p>
                </div>
              ) : (
                <div className="orders-history-list">
                  {completedOrders.map((order, idx) => {
                    const summary = getOrderSummary(order)
                    const statusInfo = getStatusInfo(summary.status, resolveOrderType(order))
                    return (
                      <button
                        key={summary.orderId || `history-${idx}`}
                        type="button"
                        className="order-history-card"
                        onClick={() => summary.orderId && navigate(`/order/${summary.orderId}`)}
                      >
                        <div className={`order-history-thumb ${summary.photoUrl ? 'has-image' : ''}`}>
                          {summary.photoUrl ? (
                            <img
                              src={summary.photoUrl}
                              alt={summary.offerTitle}
                              loading="lazy"
                              decoding="async"
                              onError={(event) => {
                                event.currentTarget.style.display = 'none'
                                event.currentTarget.parentElement.classList.remove('has-image')
                              }}
                            />
                          ) : (
                            <span>{summary.offerTitle.trim().charAt(0).toUpperCase()}</span>
                          )}
                        </div>
                        <div className="order-history-main">
                          <div className="order-history-row">
                            <h4>{summary.storeName}</h4>
                            <span className="order-history-price">{formatSum(summary.totalPrice)} so'm</span>
                          </div>
                          <div className="order-history-meta">
                            <span>{formatOrderDate(summary.createdAt)}</span>
                            <span className="order-history-dot"></span>
                            <span className="order-history-status">{statusInfo.text}</span>
                          </div>
                        </div>
                        <span className="order-history-action">
                          Qayta
                          <ArrowRight size={12} strokeWidth={2.2} />
                        </span>
                      </button>
                    )
                  })}
                </div>
              )}
            </section>

            <section className="orders-cta">
              <button
                type="button"
                className="orders-cta-btn"
                onClick={() => navigate('/')}
              >
                <div>
                  <span className="orders-cta-title">Barqaror tanlov</span>
                  <span className="orders-cta-text">Tumaningizdagi qolgan takliflarni ko'ring.</span>
                </div>
                <ArrowRight size={18} strokeWidth={2.2} />
              </button>
            </section>
          </>
        ) : (
          <section className="orders-section">
            <div className="orders-section-header">
              <h2 className="orders-section-title">Buyurtmalar tarixi</h2>
            </div>
            {loading ? (
              <div className="orders-loading">
                <div className="orders-spinner"></div>
                <p>Yuklanmoqda...</p>
              </div>
            ) : completedOrders.length === 0 ? (
              <div className="orders-empty">
                <div className="orders-empty-icon">*</div>
                <h3>Buyurtmalar tarixi bo'sh</h3>
                <p>Yangi buyurtmalar shu yerda ko'rinadi.</p>
                <button className="orders-empty-btn" onClick={() => navigate('/')}>Xarid qilish</button>
              </div>
            ) : (
              <div className="orders-history-list">
                {completedOrders.map((order, idx) => {
                  const summary = getOrderSummary(order)
                  const statusInfo = getStatusInfo(summary.status, resolveOrderType(order))
                  return (
                    <button
                      key={summary.orderId || `history-${idx}`}
                      type="button"
                      className="order-history-card"
                      onClick={() => summary.orderId && navigate(`/order/${summary.orderId}`)}
                    >
                      <div className={`order-history-thumb ${summary.photoUrl ? 'has-image' : ''}`}>
                        {summary.photoUrl ? (
                          <img
                            src={summary.photoUrl}
                            alt={summary.offerTitle}
                            loading="lazy"
                            decoding="async"
                            onError={(event) => {
                              event.currentTarget.style.display = 'none'
                              event.currentTarget.parentElement.classList.remove('has-image')
                            }}
                          />
                        ) : (
                          <span>{summary.offerTitle.trim().charAt(0).toUpperCase()}</span>
                        )}
                      </div>
                      <div className="order-history-main">
                        <div className="order-history-row">
                          <h4>{summary.storeName}</h4>
                          <span className="order-history-price">{formatSum(summary.totalPrice)} so'm</span>
                        </div>
                        <div className="order-history-meta">
                          <span>{formatOrderDate(summary.createdAt)}</span>
                          <span className="order-history-dot"></span>
                          <span className="order-history-status">{statusInfo.text}</span>
                        </div>
                      </div>
                      <span className="order-history-action">
                        Qayta
                        <ArrowRight size={12} strokeWidth={2.2} />
                      </span>
                    </button>
                  )
                })}
              </div>
            )}
          </section>
        )}
      </main>

      <BottomNav currentPage="orders" cartCount={cartCount} />
    </div>
  )
}

export default OrdersPage


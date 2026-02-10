import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import api from '../api/client'
import { useCart } from '../context/CartContext'
import { useToast } from '../context/ToastContext'
import BottomNav from '../components/BottomNav'
import PullToRefresh from '../components/PullToRefresh'
import { usePullToRefresh } from '../hooks/usePullToRefresh'
import { getUserLanguage } from '../utils/auth'
import { resolveImageUrl } from '../utils/imageUtils'
import { calcItemsTotal, calcQuantity, calcDeliveryFee, calcTotalPrice } from '../utils/orderMath'
import { deriveDisplayStatus as deriveStatus, displayStatusText, normalizeOrderStatus, resolveOrderType } from '../utils/orderStatus'
import './YanaPage.css'

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

function OrdersPage() {
  const navigate = useNavigate()
  const { cartCount } = useCart()
  const { toast } = useToast()
  const lang = getUserLanguage()

  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [cancelingOrderId, setCancelingOrderId] = useState(null)

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

  const getStatusInfo = (status, orderType) => {
    const statusMap = {
      pending: { color: '#FF9500', bg: '#FFF4E5' },
      preparing: { color: '#FF9500', bg: '#FFF4E5' },
      ready: { color: '#007AFF', bg: '#E5F2FF' },
      delivering: { color: '#007AFF', bg: '#E5F2FF' },
      completed: { color: '#53B175', bg: '#E8F5E9' },
      cancelled: { color: '#FF3B30', bg: '#FFEBEE' },
      rejected: { color: '#FF3B30', bg: '#FFEBEE' },
      awaiting_payment: { color: '#FF9500', bg: '#FFF4E5' },
      awaiting_proof: { color: '#FF9500', bg: '#FFF4E5' },
      proof_submitted: { color: '#007AFF', bg: '#E5F2FF' },
      payment_rejected: { color: '#FF3B30', bg: '#FFEBEE' },
    }
    const palette = statusMap[status] || { color: '#999', bg: '#F5F5F5' }
    return { ...palette, text: displayStatusText(status, lang, orderType) }
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
    const rawTotal = Number(order.total_with_delivery ?? order.total_price ?? order.total_amount ?? order.total ?? 0)
    const itemsTotal = calcItemsTotal(items, {
      getPrice: (item) => Number(item?.price ?? item?.discount_price ?? 0),
      getQuantity: (item) => Number(item?.quantity ?? 0),
    })
    const isDelivery = order?.order_type === 'delivery' || order?.delivery_address
    const deliveryFee = calcDeliveryFee(rawTotal, itemsTotal, {
      deliveryFee: order?.delivery_fee,
      isDelivery,
    })
    const baseTotal = itemsTotal || (rawTotal ? Math.max(0, rawTotal - deliveryFee) : 0)
    const totalPrice = calcTotalPrice(itemsTotal, deliveryFee, { totalPrice: rawTotal || null })
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
    }
  }

  const formatOrderDateTime = (dateStr) => {
    if (!dateStr) return ''
    try {
      const date = new Date(dateStr)
      if (Number.isNaN(date.getTime())) return String(dateStr)
      const now = new Date()
      const diffDays = Math.floor((now - date) / (1000 * 60 * 60 * 24))
      const time = date.toLocaleTimeString('uz-UZ', { hour: '2-digit', minute: '2-digit' })

      if (diffDays === 0) return `Bugun, ${time}`
      if (diffDays === 1) return `Kecha, ${time}`
      if (diffDays < 7) return `${diffDays} kun oldin, ${time}`

      const dateLabel = date.toLocaleDateString('uz-UZ', {
        day: 'numeric',
        month: 'short'
      })
      return `${dateLabel} - ${time}`
    } catch {
      return String(dateStr)
    }
  }

  const formatSum = (value) => {
    const numeric = Number(value || 0)
    if (!Number.isFinite(numeric)) return '0'
    return Math.round(numeric).toLocaleString('uz-UZ')
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

      <header className="profile-topbar">
        <div className="profile-topbar-inner">
          <div className="profile-topbar-center">
            <h1 className="profile-title">Buyurtmalar</h1>
          </div>
        </div>
      </header>

      <section className="profile-section active-orders-section">
        <div className="profile-section-header">
          <h3 className="profile-section-title">Faol buyurtmalar</h3>
          <span className="profile-section-badge">{activeOrders.length} ta</span>
        </div>
        {loading ? (
          <div className="profile-section-loading">
            <div className="profile-spinner"></div>
            <p>Yuklanmoqda...</p>
          </div>
        ) : activeOrders.length === 0 ? (
          <div className="profile-empty-state">
            <div className="profile-empty-icon">IMG</div>
            <h3>Faol buyurtmalar yo'q</h3>
            <p>Yangi buyurtmalar shu yerda ko'rinadi.</p>
            <button className="profile-cta-btn" onClick={() => navigate('/')}>Xarid qilish</button>
          </div>
        ) : (
          <div className="active-orders-scroll">
            {activeOrders.map((order, idx) => {
              const summary = getOrderSummary(order)
              const statusInfo = getStatusInfo(summary.status, resolveOrderType(order))
              const canCancel = CANCELABLE_STATUSES.has(summary.orderStatus)
              return (
                <div
                  key={summary.orderId || idx}
                  className="active-order-card"
                  onClick={() => summary.orderId && navigate(`/order/${summary.orderId}`)}
                  style={{ animationDelay: `${idx * 0.05}s` }}
                >
                  <div className={`active-order-image ${summary.photoUrl ? 'has-image' : ''}`}>
                    <span className="order-image-placeholder">IMG</span>
                    {summary.photoUrl && (
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
                    )}
                    <div className="active-order-overlay"></div>
                    <span className="active-order-quantity">{summary.quantity} dona</span>
                  </div>
                  <div className="active-order-body">
                    <div className="active-order-title-row">
                      <h4 className="active-order-title">{summary.storeName}</h4>
                      <span
                        className="active-order-status"
                        style={{ color: statusInfo.color, background: statusInfo.bg }}
                      >
                        {statusInfo.text}
                      </span>
                    </div>
                    <p className="active-order-subtitle">{formatOrderDateTime(summary.createdAt)}</p>
                    <div className="active-order-footer">
                      <span className="active-order-price">{formatSum(summary.totalPrice)} so'm</span>
                      <button
                        type="button"
                        className="active-order-arrow"
                        onClick={(event) => {
                          event.stopPropagation()
                          if (summary.orderId) {
                            navigate(`/order/${summary.orderId}`)
                          }
                        }}
                        aria-label="Buyurtma tafsilotlari"
                      >
                        <ArrowRight size={16} strokeWidth={2.4} />
                      </button>
                    </div>
                    {canCancel && (
                      <button
                        type="button"
                        className="active-order-cancel"
                        disabled={cancelingOrderId === summary.orderId}
                        onClick={async (event) => {
                          event.stopPropagation()
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
                </div>
              )
            })}
          </div>
        )}
      </section>

      <section className="profile-section order-history-section">
        <div className="profile-section-header">
          <h3 className="profile-section-title">Buyurtmalar tarixi</h3>
        </div>
        {loading ? (
          <div className="profile-section-loading">
            <div className="profile-spinner"></div>
            <p>Yuklanmoqda...</p>
          </div>
        ) : completedOrders.length === 0 ? (
          <div className="profile-empty-state">
            <div className="profile-empty-icon">IMG</div>
            <h3>Buyurtmalar yo'q</h3>
            <p>Birinchi buyurtmangizni bering!</p>
            <button className="profile-cta-btn" onClick={() => navigate('/')}>Xarid qilish</button>
          </div>
        ) : (
          <div className="order-history-list">
            {completedOrders.map((order, idx) => {
              const summary = getOrderSummary(order)
              return (
                <button
                  key={summary.orderId || `history-${idx}`}
                  type="button"
                  className="order-history-item"
                  onClick={() => summary.orderId && navigate(`/order/${summary.orderId}`)}
                >
                  <div className="order-history-left">
                    <div className={`order-history-thumb ${summary.photoUrl ? 'has-image' : ''}`}>
                      <span>IMG</span>
                      {summary.photoUrl && (
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
                      )}
                    </div>
                    <div className="order-history-info">
                      <p className="order-history-title">{summary.storeName}</p>
                      <p className="order-history-date">{formatOrderDateTime(summary.createdAt)}</p>
                    </div>
                  </div>
                  <div className="order-history-right">
                    <span className="order-history-price">{formatSum(summary.totalPrice)} so'm</span>
                    <span className="order-history-action">
                      Qayta
                      <ArrowRight size={12} strokeWidth={2.2} />
                    </span>
                  </div>
                </button>
              )
            })}
          </div>
        )}
      </section>

      <BottomNav currentPage="orders" cartCount={cartCount} />
    </div>
  )
}

export default OrdersPage

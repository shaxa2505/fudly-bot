import { useState, useEffect, useRef, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowRight,
  Bell,
  ChevronRight,
  CreditCard,
  Globe,
  Leaf,
  LifeBuoy,
  LogOut,
  MapPin,
} from 'lucide-react'
import api, { API_BASE_URL, getTelegramInitData } from '../api/client'
import { useCart } from '../context/CartContext'
import { useToast } from '../context/ToastContext'
import BottomNav from '../components/BottomNav'
import PullToRefresh from '../components/PullToRefresh'
import { usePullToRefresh } from '../hooks/usePullToRefresh'
import { getUserId, getUserLanguage, getCurrentUser } from '../utils/auth'
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

function YanaPage({ user }) {
  const navigate = useNavigate()
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [cancelingOrderId, setCancelingOrderId] = useState(null)
  const { toast } = useToast()
  const lang = getUserLanguage()

  const cachedUser = getCurrentUser()
  const telegramUser = window.Telegram?.WebApp?.initDataUnsafe?.user
  const resolvedPhone = (
    user?.phone ||
    cachedUser?.phone ||
    telegramUser?.phone_number ||
    localStorage.getItem('fudly_phone') ||
    ''
  )
  const resolvedCity = (() => {
    if (user?.city) return user.city
    if (cachedUser?.city) return cachedUser.city
    try {
      const stored = JSON.parse(localStorage.getItem('fudly_location') || '{}')
      return stored?.city || ''
    } catch {
      return ''
    }
  })()
  const [notifications, setNotifications] = useState(true)
  const [notificationsOpen, setNotificationsOpen] = useState(false)
  const [notificationsList, setNotificationsList] = useState([])
  const [notificationsLoading, setNotificationsLoading] = useState(true)
  const notificationsRef = useRef([])
  const [showClearCartModal, setShowClearCartModal] = useState(false)
  const profileName = (
    user?.full_name ||
    user?.name ||
    [user?.first_name, user?.last_name].filter(Boolean).join(' ') ||
    [telegramUser?.first_name, telegramUser?.last_name].filter(Boolean).join(' ') ||
    telegramUser?.username ||
    'Foydalanuvchi'
  ).trim()
  const profileHandle = user?.username || telegramUser?.username || ''
  const avatarUrl = resolveImageUrl(
    user?.photo_url,
    user?.photo,
    user?.avatar,
    telegramUser?.photo_url
  )
  const profileInitial = profileName ? profileName.slice(0, 1).toUpperCase() : 'F'

  const { cartCount, clearCart } = useCart()
  const userId = getUserId()
  const notificationsStorageKey = userId ? `fudly_notifications_${userId}` : 'fudly_notifications'

  const getWsUrl = () => {
    const base = API_BASE_URL.replace(/^http/, 'ws').replace(/\/api\/v1$/, '')
    const params = new URLSearchParams()
    if (userId) {
      params.set('user_id', userId)
    }
    const initData = getTelegramInitData()
    if (initData) {
      params.set('init_data', initData)
    }
    const query = params.toString()
    return `${base}/ws/notifications${query ? `?${query}` : ''}`
  }

  const loadNotificationSettings = async () => {
    if (!userId) return
    try {
      const data = await api.getNotificationSettings()
      setNotifications(Boolean(data.enabled))
    } catch (error) {
      console.warn('Failed to load notification settings:', error)
    }
  }

  const loadNotificationsCache = () => {
    if (!userId) {
      setNotificationsLoading(false)
      return
    }
    try {
      const raw = localStorage.getItem(notificationsStorageKey)
      const parsed = raw ? JSON.parse(raw) : []
      const next = Array.isArray(parsed) ? parsed : []
      setNotificationsList(next)
      notificationsRef.current = next
    } catch (error) {
      console.warn('Failed to load notifications cache:', error)
      setNotificationsList([])
    } finally {
      setNotificationsLoading(false)
    }
  }

  const persistNotifications = (items) => {
    if (!userId) return
    const trimmed = items.slice(0, 50)
    localStorage.setItem(notificationsStorageKey, JSON.stringify(trimmed))
  }

  const handleToggleNotifications = async () => {
    if (!userId) return
    const nextValue = !notifications
    try {
      const data = await api.setNotificationEnabled(nextValue)
      setNotifications(Boolean(data.enabled))
      toast.success(data.enabled ? 'Bildirishnomalar yoqildi' : "Bildirishnomalar o'chirildi")
    } catch (error) {
      console.error('Failed to update notifications:', error)
      toast.error("Bildirishnomalarni yangilab bo'lmadi")
    }
  }

  const handleClearNotifications = () => {
    setNotificationsList([])
    notificationsRef.current = []
    if (userId) {
      localStorage.removeItem(notificationsStorageKey)
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

  useEffect(() => {
    loadNotificationSettings()
    loadNotificationsCache()
  }, [])

  useEffect(() => {
    if (!userId || !notifications) return

    let ws
    try {
      ws = new WebSocket(getWsUrl())
    } catch (error) {
      console.warn('WebSocket init failed:', error)
      return
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'order_status_changed' || data.type === 'order_created') {
          loadOrders(true)
          return
        }

        if (data.type !== 'notification' || !data.payload) return

        const newItem = {
          id: `${Date.now()}_${Math.random().toString(16).slice(2)}`,
          title: data.payload.title || 'Bildirishnoma',
          message: data.payload.message || '',
          type: data.payload.type || 'system',
          created_at: data.payload.created_at || new Date().toISOString(),
          data: data.payload.data || {},
        }

        setNotificationsList((prev) => {
          const next = [newItem, ...prev]
          notificationsRef.current = next
          persistNotifications(next)
          return next
        })

        if (data.payload.data?.order_id || data.payload.data?.booking_id) {
          loadOrders(true)
        }
      } catch (error) {
        console.warn('Failed to parse notification:', error)
      }
    }

    return () => {
      if (ws) {
        ws.close()
      }
    }
  }, [userId, notifications])

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

  const handleRefresh = async () => {
    await loadOrders(true)
    await loadNotificationSettings()
    loadNotificationsCache()
  }

  const { containerRef, isRefreshing, pullDistance, progress } = usePullToRefresh(handleRefresh)

  const handleChangePhone = () => {
    const botUsername =
      window.Telegram?.WebApp?.initDataUnsafe?.bot?.username ||
      import.meta.env.VITE_BOT_USERNAME ||
      'fudlyuzbot'
    const link = `https://t.me/${botUsername}`
    if (window.Telegram?.WebApp?.openTelegramLink) {
      window.Telegram.WebApp.openTelegramLink(link)
      return
    }
    window.open(link, '_blank', 'noopener,noreferrer')
  }

  const handleEditProfile = () => {
    handleChangePhone()
  }

  const handleClearCart = () => {
    setShowClearCartModal(true)
  }

  const handleConfirmClearCart = () => {
    clearCart()
    setShowClearCartModal(false)
    window.Telegram?.WebApp?.showAlert?.('Savat tozalandi')
  }

  const handleDismissClearCart = () => {
    setShowClearCartModal(false)
  }

  const handleLogout = () => {
    if (window.Telegram?.WebApp?.close) {
      window.Telegram.WebApp.close()
      return
    }
    toast.info('Chiqish uchun Telegram oynasini yoping')
  }

  const handleSupport = () => {
    const link = 'https://t.me/fudly_support'
    if (window.Telegram?.WebApp?.openTelegramLink) {
      window.Telegram.WebApp.openTelegramLink(link)
      return
    }
    window.open(link, '_blank', 'noopener,noreferrer')
  }

  const getStatusInfo = (status, orderType) => {
    const statusMap = {
      pending: { text: 'Kutilmoqda', color: '#FF9500', bg: '#FFF4E5' },
      preparing: { text: 'Tayyorlanmoqda', color: '#FF9500', bg: '#FFF4E5' },
      ready: { text: 'Tayyor', color: '#007AFF', bg: '#E5F2FF' },
      delivering: { text: "Yo'lda", color: '#007AFF', bg: '#E5F2FF' },
      completed: { text: 'Yakunlandi', color: '#53B175', bg: '#E8F5E9' },
      cancelled: { text: 'Bekor', color: '#FF3B30', bg: '#FFEBEE' },
      rejected: { text: 'Rad etildi', color: '#FF3B30', bg: '#FFEBEE' },
      awaiting_payment: { text: "To'lov kutilmoqda", color: '#FF9500', bg: '#FFF4E5' },
      awaiting_proof: { text: "Chek kutilmoqda", color: '#FF9500', bg: '#FFF4E5' },
      proof_submitted: { text: 'Tekshirilmoqda', color: '#007AFF', bg: '#E5F2FF' },
      payment_rejected: { text: "To'lov rad etildi", color: '#FF3B30', bg: '#FFEBEE' },
    }
    const palette = statusMap[status] || { text: status, color: '#999', bg: '#F5F5F5' }
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
    const rawTotal = Number(order.total_price ?? order.total_amount ?? order.total ?? 0)
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
    const offerTitle =
      order.offer_title ||
      order.title ||
      items[0]?.title ||
      items[0]?.offer_title ||
      'Buyurtma'
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

  const formatDate = (dateStr) => {
    if (!dateStr) return ''
    try {
      const date = new Date(dateStr)
      const now = new Date()
      const diffDays = Math.floor((now - date) / (1000 * 60 * 60 * 24))

      if (diffDays === 0) return 'Bugun'
      if (diffDays === 1) return 'Kecha'
      if (diffDays < 7) return `${diffDays} kun oldin`

      return date.toLocaleDateString('uz-UZ', {
        day: 'numeric',
        month: 'short'
      })
    } catch {
      return dateStr
    }
  }

  const formatOrderDateTime = (dateStr) => {
    if (!dateStr) return ''
    try {
      const date = new Date(dateStr)
      if (Number.isNaN(date.getTime())) return dateStr
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
      return dateStr
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

  const savedMetric = useMemo(() => {
    const totalWeight = completedOrders.reduce((sum, order) => (
      sum + Number(order.saved_weight_kg || order.saved_weight || order.saved_kg || 0)
    ), 0)
    const totalQuantity = completedOrders.reduce((sum, order) => (
      sum + getOrderQuantity(order)
    ), 0)
    if (totalWeight > 0) {
      const formatted = Number.isInteger(totalWeight)
        ? totalWeight.toFixed(0)
        : totalWeight.toFixed(1)
      return { value: formatted, unit: 'kg' }
    }
    return { value: totalQuantity, unit: 'ta' }
  }, [completedOrders])

  const languageLabel = lang === 'ru'
    ? 'Русский'
    : (lang === 'en' ? 'English' : "O'zbekcha")

  const settingsItems = [
    {
      id: 'payments',
      label: "To'lov usullari",
      icon: CreditCard,
      tone: 'blue',
      onClick: () => toast.info("To'lov usullari tez orada")
    },
    {
      id: 'addresses',
      label: 'Manzillarim',
      icon: MapPin,
      tone: 'orange',
      onClick: () => toast.info("Manzillar ro'yxati tez orada")
    },
    {
      id: 'language',
      label: 'Ilova tili',
      icon: Globe,
      tone: 'purple',
      value: languageLabel,
      onClick: () => toast.info('Til sozlamalari tez orada')
    },
    {
      id: 'support',
      label: "Qo'llab-quvvatlash",
      icon: LifeBuoy,
      tone: 'green',
      onClick: handleSupport
    },
  ]

  return (
    <div ref={containerRef} className="yana-page">
      <PullToRefresh
        isRefreshing={isRefreshing}
        pullDistance={pullDistance}
        progress={progress}
      />

      <header className="profile-topbar">
        <div className="profile-topbar-inner">
          <h1 className="profile-title">Profilim</h1>
          <button
            type="button"
            className="profile-topbar-action"
            onClick={handleEditProfile}
          >
            Tahrirlash
          </button>
        </div>
      </header>

      <section className="profile-header" aria-label="Profil">
        <div className="profile-avatar-wrap">
          <div className={`profile-avatar ${avatarUrl ? 'has-photo' : ''}`}>
            {avatarUrl ? (
              <img src={avatarUrl} alt={profileName} />
            ) : (
              <span className="profile-initial">{profileInitial}</span>
            )}
          </div>
          {resolvedPhone && (
            <div className="profile-verify" title="Tasdiqlangan">
              <Leaf size={14} strokeWidth={2.2} />
            </div>
          )}
        </div>
        <h2 className="profile-name">{profileName}</h2>
        {profileHandle && <div className="profile-handle">@{profileHandle}</div>}
        <div className="profile-stat-pill">
          <span className="profile-stat-icon"><Leaf size={16} /></span>
          <span>
            <strong>{savedMetric.value}{savedMetric.unit}</strong> ovqat qutqarildi
          </span>
        </div>
        {(resolvedPhone || resolvedCity) && (
          <div className="profile-meta-row">
            {resolvedPhone && <span className="profile-meta-chip">{resolvedPhone}</span>}
            {resolvedCity && <span className="profile-meta-chip muted">{resolvedCity}</span>}
          </div>
        )}
      </section>

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

      <section className="profile-section notifications-section">
        <button
          type="button"
          className="notifications-accordion"
          onClick={() => setNotificationsOpen((prev) => !prev)}
          aria-expanded={notificationsOpen}
        >
          <div className="notifications-accordion-left">
            <div className="settings-icon tone-blue">
              <Bell size={18} strokeWidth={2} />
            </div>
            <div className="notifications-accordion-text">
              <span className="notifications-accordion-title">Bildirishnomalar</span>
              <span className="notifications-accordion-subtitle">
                {notifications ? 'Yoqilgan' : "O'chirilgan"}
              </span>
            </div>
          </div>
          <ChevronRight
            size={18}
            className={`notifications-accordion-chevron ${notificationsOpen ? 'open' : ''}`}
          />
        </button>

        {notificationsOpen && (
          <div className="notifications-body">
            <div className="notifications-card">
              <div className="notifications-toggle-row">
                <span className="notifications-label">Yangiliklar va statuslar</span>
                <button
                  className={`toggle ${notifications ? 'on' : ''}`}
                  onClick={handleToggleNotifications}
                >
                  <span className="toggle-knob"></span>
                </button>
              </div>
            </div>

            <div className="notifications-header">
              <h4 className="notifications-title">So'nggi bildirishnomalar</h4>
              <button className="clear-notifications-btn" onClick={handleClearNotifications}>
                Tozalash
              </button>
            </div>

            {notificationsLoading ? (
              <div className="profile-section-loading">
                <div className="profile-spinner"></div>
                <p>Yuklanmoqda...</p>
              </div>
            ) : notificationsList.length === 0 ? (
              <div className="profile-empty-state">
                <div className="profile-empty-icon">!</div>
                <h3>Bildirishnomalar yo'q</h3>
                <p>Yangi xabarlar shu yerda paydo bo'ladi.</p>
              </div>
            ) : (
              <div className="notifications-list">
                {notificationsList.map((item) => (
                  <div
                    key={item.id}
                    className={`notification-card notification-${item.type || 'system'}`}
                  >
                    <div className="notification-header">
                      <span className="notification-title">{item.title}</span>
                      <span className="notification-date">{formatDate(item.created_at)}</span>
                    </div>
                    <p className="notification-message">{item.message}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </section>

      <section className="profile-section settings-section">
        <h3 className="profile-section-label">Sozlamalar</h3>
        <div className="settings-list">
          {settingsItems.map((item) => {
            const Icon = item.icon
            return (
              <button
                key={item.id}
                type="button"
                className="settings-item"
                onClick={item.onClick}
              >
                <div className="settings-item-left">
                  <div className={`settings-icon tone-${item.tone}`}>
                    <Icon size={18} strokeWidth={2} />
                  </div>
                  <span className="settings-text">{item.label}</span>
                </div>
                <div className="settings-item-right">
                  {item.value && <span className="settings-value">{item.value}</span>}
                  <ChevronRight size={18} className="settings-chevron" />
                </div>
              </button>
            )
          })}
        </div>
      </section>

      <section className="profile-section danger-zone">
        <h3 className="danger-title">Xavfli amallar</h3>
        <p className="danger-note">
          Savatdagi barcha mahsulotlar o'chiriladi. Bu amalni qaytarib bo'lmaydi.
        </p>
        <button className="danger-btn" onClick={handleClearCart}>
          Savatni tozalash
        </button>
      </section>

      <div className="profile-logout">
        <button type="button" className="logout-btn" onClick={handleLogout}>
          <LogOut size={18} strokeWidth={2.2} />
          Chiqish
        </button>
        <p className="profile-version">Versiya 2.4.0</p>
      </div>

      {showClearCartModal && (
        <div className="confirm-modal-overlay" onClick={handleDismissClearCart}>
          <div
            className="confirm-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="clear-cart-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="confirm-modal-header">
              <h3 id="clear-cart-title">Savatni tozalash</h3>
            </div>
            <p className="confirm-modal-text">
              Savatdagi barcha mahsulotlar o'chiriladi. Davom etasizmi?
            </p>
            <div className="confirm-modal-actions">
              <button
                type="button"
                className="confirm-modal-btn secondary"
                onClick={handleDismissClearCart}
              >
                Bekor qilish
              </button>
              <button
                type="button"
                className="confirm-modal-btn danger"
                onClick={handleConfirmClearCart}
              >
                Tozalash
              </button>
            </div>
          </div>
        </div>
      )}

      <BottomNav currentPage="profile" cartCount={cartCount} />
    </div>
  )
}

export default YanaPage



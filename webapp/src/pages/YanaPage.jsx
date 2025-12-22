import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import api, { API_BASE_URL } from '../api/client'
import { useCart } from '../context/CartContext'
import { useToast } from '../context/ToastContext'
import BottomNav from '../components/BottomNav'
import { getUserId, getUserLanguage, getCurrentUser } from '../utils/auth'
import './YanaPage.css'

function YanaPage() {
  const navigate = useNavigate()
  const [activeSection, setActiveSection] = useState('orders') // orders, notifications, settings, about
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [orderFilter, setOrderFilter] = useState('all') // all, active, completed
  const { toast } = useToast()
  const lang = getUserLanguage()

  // Settings state - load from user profile first, then localStorage
  const [phone] = useState(() => {
    const user = getCurrentUser()
    if (user?.phone) return user.phone
    // Try Telegram WebApp contact
    const tgPhone = window.Telegram?.WebApp?.initDataUnsafe?.user?.phone_number
    if (tgPhone) return tgPhone
    return localStorage.getItem('fudly_phone') || ''
  })
  const [location] = useState(() => {
    try {
      const user = getCurrentUser()
      if (user?.city) return { city: user.city }
      return JSON.parse(localStorage.getItem('fudly_location') || '{}')
    } catch { return {} }
  })
  const [notifications, setNotifications] = useState(true)
  const [notificationsList, setNotificationsList] = useState([])
  const [notificationsLoading, setNotificationsLoading] = useState(true)
  const notificationsRef = useRef([])

  // Get cart count from context
  const { cartCount, clearCart } = useCart()
  const userId = getUserId()
  const notificationsStorageKey = userId ? `fudly_notifications_${userId}` : 'fudly_notifications'

  const getWsUrl = () => {
    const base = API_BASE_URL.replace(/^http/, 'ws').replace(/\/api\/v1$/, '')
    return `${base}/ws/notifications?user_id=${userId}`
  }

  const loadNotificationSettings = async () => {
    if (!userId) return
    try {
      const data = await api.getNotificationSettings(userId)
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
      const data = await api.setNotificationEnabled(userId, nextValue)
      setNotifications(Boolean(data.enabled))
      toast.success(data.enabled ? "Bildirishnomalar yoqildi" : "Bildirishnomalar o'chirildi")
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
  }, [orderFilter])

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
          loadOrders()
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
          loadOrders()
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

  const loadOrders = async () => {
    setLoading(true)
    try {
      const userId = getUserId()
      if (!userId) {
        setLoading(false)
        return
      }

      // Unified orders list from webapp API (orders + bookings)
      const response = await api.getOrders()
      const bookings = [
        ...(response.orders || []),
        ...(response.bookings || []),
      ]

      // Filter based on selection
      let filtered = bookings
      if (orderFilter === 'active') {
        // Active = pending, confirmed, ready (waiting for completion)
        filtered = bookings.filter(o => {
          const status = o.status || o.order_status
          return (
            status === 'pending' ||
            status === 'confirmed' ||
            status === 'ready' ||
            status === 'preparing' ||
            status === 'delivering' ||
            !status // treat undefined as pending
          )
        })
      } else if (orderFilter === 'completed') {
        filtered = bookings.filter(o => {
          const status = o.status || o.order_status
          return status === 'completed' || status === 'cancelled'
        })
      }

      setOrders(filtered)
    } catch (error) {
      console.error('Error loading orders:', error)
      setOrders([])
    } finally {
      setLoading(false)
    }
  }

  const handleChangePhone = () => {
    const botUsername = window.Telegram?.WebApp?.initDataUnsafe?.bot?.username || 'fudlybot'
    const link = `https://t.me/${botUsername}`
    if (window.Telegram?.WebApp?.openTelegramLink) {
      window.Telegram.WebApp.openTelegramLink(link)
      return
    }
    window.open(link, '_blank', 'noopener,noreferrer')
  }

  const getStatusInfo = (status) => {
    const statusMap = {
      pending: { text: 'Kutilmoqda', color: '#FF9500', bg: '#FFF4E5' },
      confirmed: { text: 'Tasdiqlandi', color: '#34C759', bg: '#E8F8ED' },
      preparing: { text: 'Tayyorlanmoqda', color: '#FF9500', bg: '#FFF4E5' },
      ready: { text: 'Tayyor', color: '#007AFF', bg: '#E5F2FF' },
      completed: { text: 'Yakunlandi', color: '#53B175', bg: '#E8F5E9' },
      cancelled: { text: 'Bekor', color: '#FF3B30', bg: '#FFEBEE' },
    }
    return statusMap[status] || { text: status, color: '#999', bg: '#F5F5F5' }
  }

  const getOrderSummary = (order) => {
    const items = Array.isArray(order.items) ? order.items : []
    const orderId = order.booking_id || order.order_id || order.id
    const status = order.status || order.order_status
    const createdAt = order.created_at || order.createdAt
    const quantity = order.quantity || items.reduce((sum, item) => sum + Number(item.quantity || 0), 0) || 1
    const rawTotal = Number(order.total_price ?? order.total_amount ?? order.total ?? 0)
    const itemsTotal = items.reduce((sum, item) => {
      const price = Number(item.price ?? item.discount_price ?? 0)
      const qty = Number(item.quantity ?? 0)
      return sum + price * qty
    }, 0)
    const totalPrice = rawTotal || itemsTotal
    const unitPrice = quantity
      ? Math.round((totalPrice || 0) / quantity)
      : (items[0]?.price ?? items[0]?.discount_price ?? 0)
    const offerTitle =
      order.offer_title ||
      order.title ||
      items[0]?.title ||
      items[0]?.offer_title ||
      'Buyurtma'
    const offerPhoto =
      order.offer_photo ||
      order.offer_photo_id ||
      items[0]?.photo ||
      items[0]?.offer_photo
    const storeName = order.store_name || items[0]?.store_name || "Do'kon"
    const bookingCode = order.booking_code || order.pickup_code
    const photoUrl = api.getPhotoUrl(offerPhoto) || offerPhoto

    return {
      orderId,
      status,
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

  const menuItems = [
    { id: 'orders', icon: 'O', label: 'Buyurtmalarim' },
    { id: 'notifications', icon: 'B', label: 'Bildirishnomalar' },
    { id: 'settings', icon: 'S', label: 'Sozlamalar' },
    { id: 'about', icon: 'I', label: "Ilova haqida" },
  ]

  return (
    <div className="yana-page">
      {/* Topbar */}
      <header className="yana-topbar">
        <h1 className="yana-title">Yana</h1>
      </header>

      {/* Subheader */}
      <div className="yana-subheader">
        <div className="yana-menu">
          {menuItems.map(item => (
            <button
              key={item.id}
              className={`yana-menu-item ${activeSection === item.id ? 'active' : ''}`}
              onClick={() => setActiveSection(item.id)}
            >
              <span className="menu-icon">{item.icon}</span>
              <span className="menu-label">{item.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Orders Section */}
      {activeSection === 'orders' && (
        <div className="yana-section orders-section">
          {/* Order Filters */}
          <div className="order-filters">
            {[
              { id: 'all', label: 'Barchasi' },
              { id: 'active', label: 'Faol' },
              { id: 'completed', label: 'Yakunlangan' },
            ].map(filter => (
              <button
                key={filter.id}
                className={`filter-chip ${orderFilter === filter.id ? 'active' : ''}`}
                onClick={() => setOrderFilter(filter.id)}
              >
                {filter.label}
              </button>
            ))}
          </div>

          {/* Orders List */}
          {loading ? (
            <div className="loading-state">
              <div className="spinner"></div>
              <p>Yuklanmoqda...</p>
            </div>
          ) : orders.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">IMG</div>
              <h3>Buyurtmalar yo'q</h3>
              <p>Birinchi buyurtmangizni bering!</p>
              <button className="cta-btn" onClick={() => navigate('/')}>
                 Xarid qilish
              </button>
            </div>
          ) : (
            <div className="orders-list">
              {orders.map((order, idx) => {
                const summary = getOrderSummary(order)
                const statusInfo = getStatusInfo(summary.status)
                const canCancel = ['pending', 'confirmed', 'preparing'].includes(summary.status)
                return (
                  <div
                    key={summary.orderId || idx}
                    className="order-card"
                    onClick={() => summary.orderId && navigate(`/order/${summary.orderId}`)}
                    style={{ animationDelay: `${idx * 0.05}s` }}
                  >
                    <div className="order-header">
                      <span className="order-id">#{summary.orderId}</span>
                      <span className="order-date">{formatDate(summary.createdAt)}</span>
                    </div>

                    <div className="order-content">
                      <div className="order-image-wrapper">
                        {summary.photoUrl ? (
                          <img
                            src={summary.photoUrl}
                            alt={summary.offerTitle}
                            className="order-image"
                            onError={(e) => {
                              e.target.style.display = 'none'
                              e.target.parentElement.classList.add('no-image')
                            }}
                          />
                        ) : (
                          <div className="order-placeholder">IMG</div>
                        )}
                      </div>
                      <div className="order-info">
                        <h3 className="order-title">{summary.offerTitle}</h3>
                        <p className="order-store">Do'kon: {summary.storeName}</p>
                        <div className="order-meta">
          <span>
            {summary.quantity} x {Math.round(summary.unitPrice || 0).toLocaleString()} so'm
          </span>
          <span className="order-total">
            {Math.round(summary.totalPrice || 0).toLocaleString()} so'm
          </span>
                        </div>
                      </div>
                    </div>

                    <div className="order-footer">
                      <span
                        className="order-status"
                        style={{
                          color: statusInfo.color,
                          background: statusInfo.bg
                        }}
                      >
                        {statusInfo.text}
                      </span>
                      {summary.bookingCode && (
                        <span className="booking-code">Kod: {summary.bookingCode}</span>
                      )}
                    </div>

                    {canCancel && (
                      <div className="order-actions">
                        <button
                          className="order-cancel-btn"
                          onClick={async (e) => {
                            e.stopPropagation()
                            try {
                              await api.cancelOrder(summary.orderId)
                              toast.success("Buyurtma bekor qilindi")
                              loadOrders()
                            } catch (error) {
                              console.error('Cancel order failed:', error)
                              toast.error('Bekor qilishda xatolik')
                            }
                          }}
                        >
                          Bekor qilish
                        </button>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* Notifications Section */}
      {activeSection === 'notifications' && (
        <div className="yana-section notifications-section">
          <div className="settings-group">
            <h3 className="group-title">Bildirishnomalar</h3>
            <div className="setting-item toggle-item">
              <span className="setting-label">Yangiliklar va statuslar</span>
              <button
                className={`toggle ${notifications ? 'on' : ''}`}
                onClick={handleToggleNotifications}
              >
                <span className="toggle-knob"></span>
              </button>
            </div>
          </div>

          <div className="notifications-header">
            <h3 className="group-title">So'nggi bildirishnomalar</h3>
            <button className="clear-notifications-btn" onClick={handleClearNotifications}>
              Tozalash
            </button>
          </div>

          {notificationsLoading ? (
            <div className="loading-state">
              <div className="spinner"></div>
              <p>Yuklanmoqda...</p>
            </div>
          ) : notificationsList.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">!</div>
              <h3>Bildirishnomalar yo'q</h3>
              <p>Yangi xabarlar shu yerda paydo bo'ladi.</p>
            </div>
          ) : (
            <div className="notifications-list">
              {notificationsList.map((item) => (
                <div key={item.id} className="notification-card">
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

      {/* Settings Section */}
      {activeSection === 'settings' && (
        <div className="yana-section settings-section">
          <div className="settings-group">
            <h3 className="group-title"> Shaxsiy ma'lumotlar</h3>

            <label className="setting-item">
              <span className="setting-label"> Telefon raqam</span>
              <input
                type="tel"
                className="setting-input"
                placeholder="+998 90 123 45 67"
                value={phone}
                readOnly
                disabled
              />
              <div className="setting-note">
                Telefon raqam bot orqali o'zgartiriladi.
              </div>
              <button type="button" className="change-btn" onClick={handleChangePhone}>
                Telegram orqali o'zgartirish
              </button>
            </label>

            <label className="setting-item">
              <span className="setting-label"> Shahar</span>
              <input
                type="text"
                className="setting-input"
                value={location.city || ''}
                readOnly
                disabled
                placeholder="Joylashuvni aniqlang"
              />
            </label>
          </div>

          <div className="settings-group">
            <h3 className="group-title"> Bildirishnomalar</h3>

            <div className="setting-item toggle-item">
              <span className="setting-label">Yangi takliflar</span>
              <button
                className={`toggle ${notifications ? 'on' : ''}`}
                onClick={handleToggleNotifications}
              >
                <span className="toggle-knob"></span>
              </button>
            </div>
          </div>

          <div className="settings-group">
            <h3 className="group-title"> Ma'lumotlarni tozalash</h3>

            <button
              className="danger-btn"
              onClick={() => {
                if (confirm('Savatni tozalashni xohlaysizmi?')) {
                  clearCart()
                  window.Telegram?.WebApp?.showAlert?.('Savat tozalandi')
                }
              }}
            >
               Savatni tozalash
            </button>
          </div>
        </div>
      )}

      {/* About Section */}
      {activeSection === 'about' && (
        <div className="yana-section about-section">
          <div className="about-logo">
            <span className="logo-icon">F</span>
            <h2>Fudly</h2>
            <p className="version">v2.0.0</p>
          </div>

          <div className="about-description">
            <p>
              Fudly - oziq-ovqat mahsulotlarini chegirmali narxlarda sotib olish uchun ilova.
            </p>
            <p>
              Muddati o'tayotgan yoki ortiqcha mahsulotlarni arzon narxda oling va isrofgarchilikni kamaytiring! 
            </p>
          </div>

          <div className="about-features">
            <div className="feature-item">
              <span className="feature-icon"></span>
              <div>
                <h4>70% gacha chegirma</h4>
                <p>Eng yaxshi takliflar</p>
              </div>
            </div>
            <div className="feature-item">
              <span className="feature-icon"></span>
              <div>
                <h4>Do'konlar tarmog'i</h4>
                <p>Yaqin atrofdagi do'konlar</p>
              </div>
            </div>
            <div className="feature-item">
              <span className="feature-icon">3</span>
              <div>
                <h4>Yetkazib berish</h4>
                <p>Tez va qulay</p>
              </div>
            </div>
          </div>

          <div className="about-links">
            <a href="https://t.me/fudly_support" className="link-item">
               Qo'llab-quvvatlash
            </a>
            <a href="https://t.me/fudly_channel" className="link-item">
               Telegram kanal
            </a>
          </div>

          <p className="copyright">(c) 2024 Fudly. Barcha huquqlar himoyalangan.</p>
        </div>
      )}

      <BottomNav currentPage="profile" cartCount={cartCount} />
    </div>
  )
}

export default YanaPage

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Package, Settings, Info } from 'lucide-react'
import api from '../api/client'
import { useCart } from '../context/CartContext'
import BottomNav from '../components/BottomNav'
import { getUserId, getUserLanguage, getCurrentUser } from '../utils/auth'
import './YanaPage.css'

function YanaPage() {
  const navigate = useNavigate()
  const [activeSection, setActiveSection] = useState('orders') // orders, settings, about
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [orderFilter, setOrderFilter] = useState('all') // all, active, completed
  const lang = getUserLanguage()

  // Settings state - load from user profile first, then localStorage
  const [phone, setPhone] = useState(() => {
    const user = getCurrentUser()
    if (user?.phone) return user.phone
    // Try Telegram WebApp contact
    const tgPhone = window.Telegram?.WebApp?.initDataUnsafe?.user?.phone_number
    if (tgPhone) return tgPhone
    return localStorage.getItem('fudly_phone') || ''
  })
  const [location, setLocation] = useState(() => {
    try {
      const user = getCurrentUser()
      if (user?.city) return { city: user.city }
      return JSON.parse(localStorage.getItem('fudly_location') || '{}')
    } catch { return {} }
  })
  const [notifications, setNotifications] = useState(true)

  // Get cart count from context
  const { cartCount, clearCart } = useCart()

  useEffect(() => {
    loadOrders()

    // Auto-refresh orders every 30 seconds when on orders section
    let interval
    if (activeSection === 'orders') {
      interval = setInterval(() => {
        loadOrders()
      }, 30000) // 30 seconds
    }

    return () => {
      if (interval) clearInterval(interval)
    }
  }, [orderFilter, activeSection])

  const loadOrders = async () => {
    setLoading(true)
    try {
      const userId = getUserId()
      if (!userId) {
        setLoading(false)
        return
      }

      // Fetch both bookings (old system) and delivery orders (new system)
      const [bookings, deliveryOrders] = await Promise.all([
        api.getUserBookings(userId),
        api.getDeliveryOrders(userId)
      ])

      // Normalize delivery orders to match booking format
      const normalizedDelivery = deliveryOrders.map(order => ({
        booking_id: order.id || order.order_id,
        order_id: order.id || order.order_id,
        order_type: 'delivery',
        status: order.status,
        created_at: order.created_at,
        delivery_address: order.delivery_address,
        phone: order.phone,
        payment_method: order.payment_method,
        total_price: order.total_price,
        items: order.items || [],
        // Use first item for display
        offer_title: order.items?.[0]?.title || 'Delivery buyurtma',
        store_name: order.items?.[0]?.store_name || 'Do\'kon',
        offer_photo: order.items?.[0]?.photo_url,
        quantity: order.items?.reduce((sum, item) => sum + item.quantity, 0) || 1
      }))

      // Merge both lists
      const allOrders = [...normalizedDelivery, ...bookings]
        .sort((a, b) => {
          const dateA = new Date(a.created_at || 0)
          const dateB = new Date(b.created_at || 0)
          return dateB - dateA // newest first
        })

      // Filter based on selection
      let filtered = allOrders
      if (orderFilter === 'active') {
        // Active = pending, confirmed, ready, awaiting_admin_confirmation, awaiting_payment
        filtered = allOrders.filter(o =>
          o.status === 'pending' ||
          o.status === 'confirmed' ||
          o.status === 'ready' ||
          o.status === 'awaiting_admin_confirmation' ||
          o.status === 'awaiting_payment' ||
          !o.status // treat undefined as pending
        )
      } else if (orderFilter === 'completed') {
        filtered = allOrders.filter(o =>
          o.status === 'completed' ||
          o.status === 'cancelled' ||
          o.status === 'rejected'
        )
      }

      setOrders(filtered)
    } catch (error) {
      console.error('Error loading orders:', error)
      setOrders([])
    } finally {
      setLoading(false)
    }
  }

  const saveSettings = () => {
    localStorage.setItem('fudly_phone', phone)
    window.Telegram?.WebApp?.showAlert?.('Sozlamalar saqlandi!')
  }

  const getStatusInfo = (status) => {
    const statusMap = {
      pending: { text: '⏳ Kutilmoqda', color: '#FF9500', bg: '#FFF4E5' },
      awaiting_payment: { text: '💳 To\'lov kutilmoqda', color: '#FF9500', bg: '#FFF4E5' },
      awaiting_admin_confirmation: { text: '🔍 Tekshirilmoqda', color: '#FF9500', bg: '#FFF4E5' },
      confirmed: { text: '✅ Tasdiqlandi', color: '#34C759', bg: '#E8F8ED' },
      ready: { text: '📦 Tayyor', color: '#007AFF', bg: '#E5F2FF' },
      completed: { text: '🎉 Yakunlandi', color: '#53B175', bg: '#E8F5E9' },
      cancelled: { text: '❌ Bekor qilindi', color: '#FF3B30', bg: '#FFEBEE' },
      rejected: { text: '❌ Rad etildi', color: '#FF3B30', bg: '#FFEBEE' },
    }
    return statusMap[status] || { text: status, color: '#999', bg: '#F5F5F5' }
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
    { id: 'orders', icon: Package, label: 'Buyurtmalarim' },
    { id: 'settings', icon: Settings, label: 'Sozlamalar' },
    { id: 'about', icon: Info, label: "Ilova haqida" },
  ]

  return (
    <div className="yana-page">
      {/* Header with menu */}
      <header className="yana-header">
        <h1 className="yana-title">Yana</h1>
        <div className="yana-menu">
          {menuItems.map(item => {
            const IconComponent = item.icon
            return (
              <button
                key={item.id}
                className={`yana-menu-item ${activeSection === item.id ? 'active' : ''}`}
                onClick={() => setActiveSection(item.id)}
              >
                <IconComponent size={20} strokeWidth={2} className="menu-icon" aria-hidden="true" />
                <span className="menu-label">{item.label}</span>
              </button>
            )
          })}
        </div>
      </header>

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
              <div className="empty-icon">📦</div>
              <h3>Buyurtmalar yo'q</h3>
              <p>Birinchi buyurtmangizni bering!</p>
              <button className="cta-btn" onClick={() => navigate('/')}>
                🛒 Xarid qilish
              </button>
            </div>
          ) : (
            <div className="orders-list">
              {orders.map((order, idx) => {
                const statusInfo = getStatusInfo(order.status)
                return (
                  <div
                    key={order.order_id || order.booking_id || idx}
                    className="order-card"
                    onClick={() => {
                      const orderId = order.order_id || order.booking_id
                      if (orderId) navigate(`/order/${orderId}`)
                    }}
                    style={{ animationDelay: `${idx * 0.05}s` }}
                  >
                    <div className="order-header">
                      <span className="order-id">#{order.order_id || order.booking_id}</span>
                      <span className="order-date">{formatDate(order.created_at)}</span>
                    </div>

                    <div className="order-content">
                      <div className="order-image-wrapper">
                        {order.offer_photo ? (
                          <img
                            src={order.offer_photo}
                            alt={order.offer_title}
                            className="order-image"
                            onError={(e) => {
                              e.target.style.display = 'none'
                              e.target.parentElement.classList.add('no-image')
                            }}
                          />
                        ) : (
                          <div className="order-placeholder">📦</div>
                        )}
                      </div>
                      <div className="order-info">
                        <h3 className="order-title">{order.offer_title || 'Buyurtma'}</h3>
                        <p className="order-store">🏪 {order.store_name || 'Do\'kon'}</p>
                        <div className="order-meta">
                          <span>
                            {order.quantity || 1} × {order.total_price && order.quantity
                              ? Math.round(order.total_price / order.quantity).toLocaleString()
                              : '—'} so'm
                          </span>
                          <span className="order-total">
                            {order.total_price
                              ? Math.round(order.total_price).toLocaleString()
                              : '—'} so'm
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
                      {order.booking_code && (
                        <span className="booking-code">🎫 {order.booking_code}</span>
                      )}
                    </div>

                    {/* Upload payment proof button for awaiting_payment orders */}
                    {order.status === 'awaiting_payment' && (
                      <button
                        className="upload-proof-btn"
                        onClick={(e) => {
                          e.stopPropagation()
                          const orderId = order.order_id || order.booking_id
                          if (orderId && window.Telegram?.WebApp) {
                            // Open bot in private messages with deep link
                            window.Telegram.WebApp.openTelegramLink(
                              `https://t.me/${window.Telegram.WebApp.initDataUnsafe?.bot?.username || 'fudlybot'}?start=upload_proof_${orderId}`
                            )
                          }
                        }}
                      >
                        📸 Chekni yuklash / Загрузить чек
                      </button>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* Settings Section */}
      {activeSection === 'settings' && (
        <div className="yana-section settings-section">
          <div className="settings-group">
            <h3 className="group-title">👤 Shaxsiy ma'lumotlar</h3>

            <label className="setting-item">
              <span className="setting-label">📱 Telefon raqam</span>
              <input
                type="tel"
                className="setting-input"
                placeholder="+998 90 123 45 67"
                value={phone}
                onChange={e => setPhone(e.target.value)}
              />
            </label>

            <label className="setting-item">
              <span className="setting-label">📍 Shahar</span>
              <input
                type="text"
                className="setting-input"
                value={location.city || ''}
                readOnly
                placeholder="Joylashuvni aniqlang"
              />
            </label>

            <button className="save-btn" onClick={saveSettings}>
              💾 Saqlash
            </button>
          </div>

          <div className="settings-group">
            <h3 className="group-title">🔔 Bildirishnomalar</h3>

            <div className="setting-item toggle-item">
              <span className="setting-label">Yangi takliflar</span>
              <button
                className={`toggle ${notifications ? 'on' : ''}`}
                onClick={() => setNotifications(!notifications)}
              >
                <span className="toggle-knob"></span>
              </button>
            </div>
          </div>

          <div className="settings-group">
            <h3 className="group-title">🗑️ Ma'lumotlarni tozalash</h3>

            <button
              className="danger-btn"
              onClick={() => {
                if (confirm('Savatni tozalashni xohlaysizmi?')) {
                  clearCart()
                  window.Telegram?.WebApp?.showAlert?.('Savat tozalandi')
                }
              }}
            >
              🛒 Savatni tozalash
            </button>
          </div>
        </div>
      )}

      {/* About Section */}
      {activeSection === 'about' && (
        <div className="yana-section about-section">
          <div className="about-logo">
            <span className="logo-icon">🍽️</span>
            <h2>Fudly</h2>
            <p className="version">v2.0.0</p>
          </div>

          <div className="about-description">
            <p>
              Fudly - oziq-ovqat mahsulotlarini chegirmali narxlarda sotib olish uchun ilova.
            </p>
            <p>
              Muddati o'tayotgan yoki ortiqcha mahsulotlarni arzon narxda oling va isrofgarchilikni kamaytiring! 🌱
            </p>
          </div>

          <div className="about-features">
            <div className="feature-item">
              <span className="feature-icon">💰</span>
              <div>
                <h4>70% gacha chegirma</h4>
                <p>Eng yaxshi takliflar</p>
              </div>
            </div>
            <div className="feature-item">
              <span className="feature-icon">🏪</span>
              <div>
                <h4>Do'konlar tarmog'i</h4>
                <p>Yaqin atrofdagi do'konlar</p>
              </div>
            </div>
            <div className="feature-item">
              <span className="feature-icon">🚚</span>
              <div>
                <h4>Yetkazib berish</h4>
                <p>Tez va qulay</p>
              </div>
            </div>
          </div>

          <div className="about-links">
            <a href="https://t.me/fudly_support" className="link-item">
              💬 Qo'llab-quvvatlash
            </a>
            <a href="https://t.me/fudly_channel" className="link-item">
              📣 Telegram kanal
            </a>
          </div>

          <p className="copyright">© 2024 Fudly. Barcha huquqlar himoyalangan.</p>
        </div>
      )}

      <BottomNav currentPage="profile" cartCount={cartCount} />
    </div>
  )
}

export default YanaPage

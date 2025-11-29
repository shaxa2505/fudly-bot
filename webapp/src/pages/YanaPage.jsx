import { useState, useEffect } from 'react'
import api from '../api/client'
import BottomNav from '../components/BottomNav'
import { getUserId, getUserLanguage } from '../utils/auth'
import './YanaPage.css'

function YanaPage({ onNavigate }) {
  const [activeSection, setActiveSection] = useState('orders') // orders, settings, about
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [orderFilter, setOrderFilter] = useState('all') // all, active, completed
  const lang = getUserLanguage()

  // Settings state
  const [phone, setPhone] = useState(() => localStorage.getItem('fudly_phone') || '')
  const [location, setLocation] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem('fudly_location') || '{}')
    } catch { return {} }
  })
  const [notifications, setNotifications] = useState(true)
  
  // Get cart for badge
  const cart = (() => {
    try {
      return JSON.parse(localStorage.getItem('fudly_cart_v2') || '{}')
    } catch { return {} }
  })()
  const cartCount = Object.values(cart).reduce((sum, item) => sum + (item?.quantity || 0), 0)

  useEffect(() => {
    loadOrders()
  }, [orderFilter])

  const loadOrders = async () => {
    setLoading(true)
    try {
      const userId = getUserId()
      if (!userId) {
        setLoading(false)
        return
      }

      // Try to get bookings/orders
      const bookings = await api.getUserBookings(userId)
      
      // Filter based on selection
      let filtered = bookings
      if (orderFilter === 'active') {
        filtered = bookings.filter(o => ['pending', 'confirmed', 'ready'].includes(o.status))
      } else if (orderFilter === 'completed') {
        filtered = bookings.filter(o => ['completed', 'cancelled'].includes(o.status))
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
      confirmed: { text: '✅ Tasdiqlandi', color: '#34C759', bg: '#E8F8ED' },
      ready: { text: '📦 Tayyor', color: '#007AFF', bg: '#E5F2FF' },
      completed: { text: '🎉 Yakunlandi', color: '#53B175', bg: '#E8F5E9' },
      cancelled: { text: '❌ Bekor', color: '#FF3B30', bg: '#FFEBEE' },
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
    { id: 'orders', icon: '📦', label: 'Buyurtmalarim' },
    { id: 'settings', icon: '⚙️', label: 'Sozlamalar' },
    { id: 'about', icon: 'ℹ️', label: "Ilova haqida" },
  ]

  return (
    <div className="yana-page">
      {/* Header with menu */}
      <header className="yana-header">
        <h1 className="yana-title">Yana</h1>
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
              <button className="cta-btn" onClick={() => onNavigate('home')}>
                🛒 Xarid qilish
              </button>
            </div>
          ) : (
            <div className="orders-list">
              {orders.map((order, idx) => {
                const statusInfo = getStatusInfo(order.status)
                return (
                  <div 
                    key={order.booking_id || idx} 
                    className="order-card"
                    onClick={() => onNavigate('order-tracking', { bookingId: order.booking_id })}
                    style={{ animationDelay: `${idx * 0.05}s` }}
                  >
                    <div className="order-header">
                      <span className="order-id">#{order.booking_id}</span>
                      <span className="order-date">{formatDate(order.created_at)}</span>
                    </div>
                    
                    <div className="order-content">
                      {order.offer_photo && (
                        <img
                          src={order.offer_photo}
                          alt={order.offer_title}
                          className="order-image"
                        />
                      )}
                      <div className="order-info">
                        <h3 className="order-title">{order.offer_title}</h3>
                        <p className="order-store">🏪 {order.store_name}</p>
                        <div className="order-meta">
                          <span>{order.quantity} × {Math.round(order.total_price / order.quantity).toLocaleString()} so'm</span>
                          <span className="order-total">{Math.round(order.total_price).toLocaleString()} so'm</span>
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
                  localStorage.removeItem('fudly_cart_v2')
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

      <BottomNav currentPage="profile" onNavigate={onNavigate} cartCount={cartCount} />
    </div>
  )
}

export default YanaPage

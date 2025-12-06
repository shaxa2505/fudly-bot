import { useState, useEffect } from 'react'
import api from '../api/client'
import BottomNav from '../components/BottomNav'
import { getCurrentUser, getUserId, getUserLanguage } from '../utils/auth'
import './ProfilePage.css'

function ProfilePage({ onNavigate }) {
  const [user, setUser] = useState(null)
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('active') // active, completed, all
  const lang = getUserLanguage()

  useEffect(() => {
    loadProfile()
  }, [])

  useEffect(() => {
    if (user) {
      loadOrders()
    }
  }, [activeTab, user])

  const loadProfile = async () => {
    try {
      const userId = getUserId()
      if (!userId) {
        setLoading(false)
        return
      }

      const profile = await api.getProfile(userId)
      setUser(profile)
    } catch (error) {
      console.error('Error loading profile:', error)
      window.Telegram?.WebApp?.showAlert?.('Profil yuklanmadi')
    } finally {
      setLoading(false)
    }
  }

  const loadOrders = async () => {
    try {
      const userId = getUserId()
      const statusFilter = activeTab === 'active' ? null : activeTab === 'completed' ? 'completed' : null
      
      const data = await api.getUserOrders(userId, statusFilter)
      
      // Filter based on tab
      let filtered = data.orders
      if (activeTab === 'active') {
        filtered = data.orders.filter(o => ['pending', 'confirmed'].includes(o.status))
      }
      
      setOrders(filtered)
    } catch (error) {
      console.error('Error loading orders:', error)
    }
  }

  const getStatusText = (status) => {
    const statusMap = {
      ru: {
        pending: '⏳ Ожидает',
        confirmed: '✅ Подтверждён',
        completed: '🎉 Завершён',
        cancelled: '❌ Отменён'
      },
      uz: {
        pending: '⏳ Kutilmoqda',
        confirmed: '✅ Tasdiqlangan',
        completed: '🎉 Yakunlangan',
        cancelled: '❌ Bekor qilingan'
      }
    }
    return statusMap[lang === 'uz' ? 'uz' : 'ru'][status] || status
  }

  const getStatusColor = (status) => {
    switch (status) {
      case 'confirmed': return '#28a745'
      case 'completed': return '#FF6B35'
      case 'cancelled': return '#dc3545'
      default: return '#999'
    }
  }

  const formatDate = (dateStr) => {
    if (!dateStr) return ''
    try {
      const date = new Date(dateStr)
      const day = date.getDate().toString().padStart(2, '0')
      const month = (date.getMonth() + 1).toString().padStart(2, '0')
      const year = date.getFullYear()
      const hours = date.getHours().toString().padStart(2, '0')
      const minutes = date.getMinutes().toString().padStart(2, '0')
      return `${day}.${month}.${year} ${hours}:${minutes}`
    } catch {
      return dateStr
    }
  }

  if (loading) {
    return (
      <div className="profile-page">
        <div className="loading">
          <div className="spinner"></div>
          <p>{lang === 'uz' ? 'Yuklanmoqda...' : 'Загрузка...'}</p>
        </div>
        <BottomNav currentPage="profile" onNavigate={onNavigate} />
      </div>
    )
  }

  if (!user) {
    return (
      <div className="profile-page">
        <div className="empty-state">
          <div className="empty-icon">👤</div>
          <h3>{lang === 'uz' ? 'Profil topilmadi' : 'Профиль не найден'}</h3>
          <p>{lang === 'uz' ? 'Botda ro\'yxatdan o\'ting' : 'Зарегистрируйтесь в боте'}</p>
        </div>
        <BottomNav currentPage="profile" onNavigate={onNavigate} />
      </div>
    )
  }

  return (
    <div className="profile-page">
      {/* Header */}
      <div className="profile-header">
        <div className="profile-avatar">
          {user.first_name?.charAt(0)?.toUpperCase() || '👤'}
        </div>
        <div className="profile-info">
          <h1 className="profile-name">{user.first_name} {user.last_name || ''}</h1>
          {user.username && <p className="profile-username">@{user.username}</p>}
          <div className="profile-meta">
            {user.phone && <span>📱 {user.phone}</span>}
            {user.city && <span>📍 {user.city}</span>}
          </div>
        </div>
      </div>

      {/* Orders Section */}
      <div className="orders-section">
        <h2 className="section-title">
          {lang === 'uz' ? 'Buyurtmalarim' : 'Мои заказы'}
        </h2>

        {/* Tabs */}
        <div className="orders-tabs">
          <button
            className={`tab ${activeTab === 'active' ? 'active' : ''}`}
            onClick={() => setActiveTab('active')}
          >
            {lang === 'uz' ? 'Aktiv' : 'Активные'}
          </button>
          <button
            className={`tab ${activeTab === 'completed' ? 'active' : ''}`}
            onClick={() => setActiveTab('completed')}
          >
            {lang === 'uz' ? 'Yakunlangan' : 'Завершённые'}
          </button>
          <button
            className={`tab ${activeTab === 'all' ? 'active' : ''}`}
            onClick={() => setActiveTab('all')}
          >
            {lang === 'uz' ? 'Barchasi' : 'Все'}
          </button>
        </div>

        {/* Orders List */}
        {orders.length === 0 ? (
          <div className="empty-orders">
            <div className="empty-icon">📦</div>
            <p>
              {lang === 'uz' 
                ? 'Buyurtmalar yo\'q' 
                : 'Нет заказов'}
            </p>
          </div>
        ) : (
          <div className="orders-list">
            {orders.map((order) => (
              <div 
                key={order.booking_id} 
                className="order-card"
                onClick={() => onNavigate('order-tracking', { bookingId: order.booking_id })}
                style={{ cursor: 'pointer' }}
              >
                <div className="order-content">
                  {order.offer_photo && (
                    <img
                      src={order.offer_photo}
                      alt={order.offer_title}
                      className="order-image"
                    />
                  )}
                  <div className="order-details">
                    <h3 className="order-title">{order.offer_title}</h3>
                    <p className="order-store">🏪 {order.store_name}</p>
                    {order.store_address && (
                      <p className="order-address">📍 {order.store_address}</p>
                    )}
                    <div className="order-meta">
                      <span className="order-quantity">
                        {order.quantity} × {Math.round(order.total_price / order.quantity).toLocaleString()} {lang === 'uz' ? 'so\'m' : 'сум'}
                      </span>
                      <span className="order-total">
                        {order.total_price.toLocaleString()} {lang === 'uz' ? 'so\'m' : 'сум'}
                      </span>
                    </div>
                    <div className="order-footer">
                      <span 
                        className="order-status"
                        style={{ color: getStatusColor(order.status) }}
                      >
                        {getStatusText(order.status)}
                      </span>
                      {order.booking_code && (
                        <span className="booking-code">
                          🎫 #{order.booking_code}
                        </span>
                      )}
                    </div>
                    {order.created_at && (
                      <p className="order-date">{formatDate(order.created_at)}</p>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <BottomNav currentPage="profile" onNavigate={onNavigate} />
    </div>
  )
}

export default ProfilePage

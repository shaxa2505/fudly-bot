import { useNavigate } from 'react-router-dom'
import { resolveImageUrl } from '../../utils/imageUtils'
import { Package, ShoppingCart, Home } from 'lucide-react'

const ORDER_FILTERS = [
  { id: 'all', label: 'Barchasi' },
  { id: 'active', label: 'Faol' },
  { id: 'completed', label: 'Yakunlangan' },
]

const getStatusInfo = (status) => {
  const statusMap = {
    pending: { text: '⏳ Kutilmoqda', color: '#FF9500', bg: '#FFF4E5' },
    preparing: { text: '👨‍🍳 Tayyorlanmoqda', color: '#34C759', bg: '#E8F8ED' },
    ready: { text: '📦 Tayyor', color: '#007AFF', bg: '#E5F2FF' },
    delivering: { text: '🚚 Yo\'lda', color: '#007AFF', bg: '#E5F2FF' },
    completed: { text: '🎉 Yakunlandi', color: '#53B175', bg: '#E8F5E9' },
    cancelled: { text: '❌ Bekor qilindi', color: '#FF3B30', bg: '#FFEBEE' },
    rejected: { text: '❌ Rad etildi', color: '#FF3B30', bg: '#FFEBEE' },

    awaiting_payment: { text: '💳 To\'lov kutilmoqda', color: '#FF9500', bg: '#FFF4E5' },
    awaiting_proof: { text: '📸 Chek kutilmoqda', color: '#FF9500', bg: '#FFF4E5' },
    proof_submitted: { text: '🔍 Tekshirilmoqda', color: '#FF9500', bg: '#FFF4E5' },
    payment_rejected: { text: '❌ To\'lov rad etildi', color: '#FF3B30', bg: '#FFEBEE' },
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

function OrdersSection({ orders, loading, orderFilter, onFilterChange }) {
  const navigate = useNavigate()

  const handleOrderClick = (orderId) => {
    if (orderId) {
      navigate(`/order/${orderId}`)
    }
  }

  const handleUploadProof = (orderId) => {
    if (!orderId || !window.Telegram?.WebApp) return
    const botUsername = window.Telegram.WebApp.initDataUnsafe?.bot?.username || 'fudlybot'
    window.Telegram.WebApp.openTelegramLink(
      `https://t.me/${botUsername}?start=upload_proof_${orderId}`
    )
  }

  return (
    <div className="yana-section orders-section">
      <div className="order-filters">
        {ORDER_FILTERS.map(filter => (
          <button
            key={filter.id}
            className={`filter-chip ${orderFilter === filter.id ? 'active' : ''}`}
            onClick={() => onFilterChange(filter.id)}
          >
            {filter.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Yuklanmoqda...</p>
        </div>
      ) : orders.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">
            <Package size={80} strokeWidth={1.5} color="#53B175" aria-hidden="true" />
          </div>
          <h3>Buyurtmalar yo'q</h3>
          <p className="empty-description">
            Hali hech qanday buyurtma bermadingiz.
            Birinchi buyurtmangizni berib, tez yetkazib olishdan bahramand bo'ling!
          </p>
          <button className="cta-btn" onClick={() => navigate('/')}>
            <ShoppingCart size={20} strokeWidth={2} aria-hidden="true" />
            <span>Xarid qilish</span>
          </button>
          <button className="secondary-btn" onClick={() => navigate('/stores')}>
            <Home size={20} strokeWidth={2} aria-hidden="true" />
            <span>Do'konlarni ko'rish</span>
          </button>
        </div>
      ) : (
        <div className="orders-list">
          {orders.map((order, idx) => {
            const statusInfo = getStatusInfo(order.status)
            const orderId = order.order_id || order.booking_id
            const photoUrl = resolveImageUrl(
              order.offer_photo,
              order.offer_photo_url,
              order.offer_photo_id,
              order.photo,
              order.photo_id
            )
            return (
              <div
                key={orderId || idx}
                className="order-card"
                onClick={() => handleOrderClick(orderId)}
                style={{ animationDelay: `${idx * 0.05}s` }}
              >
                <div className="order-header">
                  <span className="order-id">#{orderId}</span>
                  <span className="order-date">{formatDate(order.created_at)}</span>
                </div>

                <div className="order-content">
                  <div className="order-image-wrapper">
                    {photoUrl ? (
                      <img
                        src={photoUrl}
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
                    <p className="order-store">🏪 {order.store_name || "Do'kon"}</p>
                    <div className="order-meta">
                      <span>
                        {order.quantity || 1} × {order.total_price && order.quantity
                          ? Math.round(order.total_price / order.quantity).toLocaleString()
                          : '0'} so'm
                      </span>
                      <span className="order-total">
                        {order.total_price
                          ? Math.round(order.total_price).toLocaleString()
                          : '0'} so'm
                      </span>
                    </div>
                  </div>
                </div>

                <div className="order-footer">
                  <span
                    className="order-status"
                    style={{ color: statusInfo.color, background: statusInfo.bg }}
                  >
                    {statusInfo.text}
                  </span>
                  {order.booking_code && (
                    <span className="booking-code">🎫 {order.booking_code}</span>
                  )}
                </div>

                {['awaiting_proof', 'payment_rejected'].includes(order.status) && (
                  <button
                    className="upload-proof-btn"
                    onClick={(e) => {
                      e.stopPropagation()
                      handleUploadProof(orderId)
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
  )
}

export default OrdersSection

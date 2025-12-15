import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import apiClient from '../api/client'
import './OrderDetailsPage.css'

export default function OrderDetailsPage() {
  const { orderId } = useParams()
  const navigate = useNavigate()
  const [order, setOrder] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    loadOrderDetails()
    // Auto-refresh every 30 seconds
    const interval = setInterval(loadOrderDetails, 30000)
    return () => clearInterval(interval)
  }, [orderId])

  const loadOrderDetails = async () => {
    try {
      setLoading(true)
      // Try to get delivery order first
      const response = await apiClient.getUserBookings()
      
      // Find order by ID in both bookings and delivery orders
      let foundOrder = null
      
      if (response.bookings) {
        foundOrder = response.bookings.find(
          b => b.booking_id === parseInt(orderId) || b.order_id === parseInt(orderId)
        )
      }
      
      if (!foundOrder && response.delivery_orders) {
        foundOrder = response.delivery_orders.find(
          d => d.order_id === parseInt(orderId)
        )
        
        // Normalize delivery order format
        if (foundOrder) {
          foundOrder = {
            ...foundOrder,
            order_id: foundOrder.order_id,
            status: foundOrder.order_status || foundOrder.status,
            offer_title: foundOrder.items?.[0]?.offer_title || 'Заказ',
            offer_photo: foundOrder.items?.[0]?.photo,
            store_name: foundOrder.items?.[0]?.store_name,
            quantity: foundOrder.items?.reduce((sum, item) => sum + (item.quantity || 0), 0) || 1,
            items: foundOrder.items || []
          }
        }
      }
      
      if (!foundOrder) {
        setError('Заказ не найден / Buyurtma topilmadi')
        return
      }
      
      setOrder(foundOrder)
      setError(null)
    } catch (err) {
      console.error('Failed to load order details:', err)
      setError('Не удалось загрузить детали заказа / Buyurtma ma\'lumotlarini yuklab bo\'lmadi')
    } finally {
      setLoading(false)
    }
  }

  const getStatusInfo = (status) => {
    const statusMap = {
      pending: { text: '⏳ Kutilmoqda / Ожидание', color: '#FF6B35', bg: '#FFF4F0' },
      confirmed: { text: '✅ Tasdiqlandi / Подтверждён', color: '#10B981', bg: '#ECFDF5' },
      ready_for_pickup: { text: '📦 Tayyor / Готов к выдаче', color: '#8B5CF6', bg: '#FAF5FF' },
      completed: { text: '✅ Bajarildi / Выполнен', color: '#10B981', bg: '#ECFDF5' },
      cancelled: { text: '❌ Bekor qilindi / Отменён', color: '#EF4444', bg: '#FEF2F2' },
      rejected: { text: '❌ Rad etildi / Отклонён', color: '#EF4444', bg: '#FEF2F2' },
      awaiting_payment: { text: '💳 To\'lov kutilmoqda / Ожидание оплаты', color: '#F59E0B', bg: '#FFFBEB' },
      awaiting_admin_confirmation: { text: '⏳ Admin tekshiruvi / Проверка админом', color: '#3B82F6', bg: '#EFF6FF' },
    }
    return statusMap[status] || { text: status, color: '#6B7280', bg: '#F3F4F6' }
  }

  const formatDate = (dateString) => {
    if (!dateString) return '—'
    const date = new Date(dateString)
    return date.toLocaleString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  const handleUploadProof = () => {
    if (window.Telegram?.WebApp) {
      window.Telegram.WebApp.openTelegramLink(
        `https://t.me/${window.Telegram.WebApp.initDataUnsafe?.bot?.username || 'fudlybot'}?start=upload_proof_${orderId}`
      )
    }
  }

  if (loading) {
    return (
      <div className="order-details-page">
        <div className="loading-container">
          <div className="spinner"></div>
          <p>Yuklanmoqda...</p>
        </div>
      </div>
    )
  }

  if (error || !order) {
    return (
      <div className="order-details-page">
        <div className="error-container">
          <div className="error-icon">😕</div>
          <p>{error || 'Xatolik yuz berdi / Произошла ошибка'}</p>
          <button className="back-btn" onClick={() => navigate('/yana')}>
            ← Orqaga / Назад
          </button>
        </div>
      </div>
    )
  }

  const statusInfo = getStatusInfo(order.status)
  const isDelivery = order.order_type === 'delivery' || order.delivery_address
  const needsPayment = order.status === 'awaiting_payment'

  return (
    <div className="order-details-page">
      {/* Header */}
      <div className="details-header">
        <button className="back-button" onClick={() => navigate('/yana')}>
          ←
        </button>
        <h1 className="details-title">Buyurtma / Заказ #{orderId}</h1>
      </div>

      {/* Status Banner */}
      <div className="status-banner" style={{ background: statusInfo.bg }}>
        <span className="status-text" style={{ color: statusInfo.color }}>
          {statusInfo.text}
        </span>
        <span className="order-date">{formatDate(order.created_at)}</span>
      </div>

      {/* Upload Payment Proof Button */}
      {needsPayment && (
        <div className="payment-notice">
          <div className="notice-icon">💳</div>
          <div className="notice-content">
            <h3>To'lov talab qilinadi / Требуется оплата</h3>
            <p>To'lovni amalga oshiring va chekni yuklang</p>
            <p>Совершите оплату и загрузите чек</p>
          </div>
          <button className="upload-btn" onClick={handleUploadProof}>
            📸 Yuklash
          </button>
        </div>
      )}

      {/* Order Items */}
      <div className="details-section">
        <h2 className="section-title">📦 Mahsulotlar / Товары</h2>
        <div className="items-list">
          {order.items && order.items.length > 0 ? (
            order.items.map((item, idx) => (
              <div key={idx} className="item-card">
                {item.photo && (
                  <img
                    src={item.photo}
                    alt={item.offer_title}
                    className="item-image"
                    onError={(e) => {
                      e.target.style.display = 'none'
                    }}
                  />
                )}
                <div className="item-info">
                  <h3 className="item-title">{item.offer_title}</h3>
                  <p className="item-store">🏪 {item.store_name}</p>
                  <div className="item-meta">
                    <span className="item-quantity">{item.quantity} × {Math.round(item.price).toLocaleString()} so'm</span>
                    <span className="item-total">{Math.round(item.quantity * item.price).toLocaleString()} so'm</span>
                  </div>
                </div>
              </div>
            ))
          ) : (
            <div className="single-item-card">
              {order.offer_photo && (
                <img
                  src={order.offer_photo}
                  alt={order.offer_title}
                  className="item-image"
                  onError={(e) => {
                    e.target.style.display = 'none'
                  }}
                />
              )}
              <div className="item-info">
                <h3 className="item-title">{order.offer_title}</h3>
                <p className="item-store">🏪 {order.store_name}</p>
                <div className="item-meta">
                  <span className="item-quantity">{order.quantity || 1} dona</span>
                  <span className="item-total">{Math.round(order.total_price || 0).toLocaleString()} so'm</span>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Delivery Info */}
      {isDelivery && order.delivery_address && (
        <div className="details-section">
          <h2 className="section-title">🚚 Yetkazib berish / Доставка</h2>
          <div className="info-card">
            <div className="info-row">
              <span className="info-label">📍 Manzil / Адрес:</span>
              <span className="info-value">{order.delivery_address}</span>
            </div>
            {order.phone && (
              <div className="info-row">
                <span className="info-label">📱 Telefon:</span>
                <span className="info-value">{order.phone}</span>
              </div>
            )}
            {order.delivery_notes && (
              <div className="info-row">
                <span className="info-label">📝 Izoh / Примечание:</span>
                <span className="info-value">{order.delivery_notes}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Pickup Info */}
      {!isDelivery && order.booking_code && (
        <div className="details-section">
          <h2 className="section-title">🎫 Olib ketish / Самовывоз</h2>
          <div className="info-card">
            <div className="info-row">
              <span className="info-label">Kod / Код:</span>
              <span className="info-value booking-code">{order.booking_code}</span>
            </div>
            {order.pickup_time && (
              <div className="info-row">
                <span className="info-label">⏰ Vaqt:</span>
                <span className="info-value">{formatDate(order.pickup_time)}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Payment Info */}
      <div className="details-section">
        <h2 className="section-title">💰 To'lov / Оплата</h2>
        <div className="info-card">
          <div className="info-row">
            <span className="info-label">Usul / Способ:</span>
            <span className="info-value">
              {order.payment_method === 'card' ? '💳 Karta / Карта' : '💵 Naqd / Наличные'}
            </span>
          </div>
          <div className="info-row total-row">
            <span className="info-label">Jami / Итого:</span>
            <span className="info-value total-price">
              {Math.round(order.total_price || 0).toLocaleString()} so'm
            </span>
          </div>
        </div>
      </div>

      {/* Contact Support */}
      <div className="support-section">
        <p className="support-text">Savollar bormi? / Есть вопросы?</p>
        <button
          className="support-btn"
          onClick={() => {
            if (window.Telegram?.WebApp) {
              window.Telegram.WebApp.openTelegramLink('https://t.me/fudly_support')
            }
          }}
        >
          💬 Qo'llab-quvvatlash / Поддержка
        </button>
      </div>
    </div>
  )
}

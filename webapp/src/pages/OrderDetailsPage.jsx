import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
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
      const response = await apiClient.getOrders()

      const all = [...(response.orders || []), ...(response.bookings || [])]
      let foundOrder = null
      const raw = all.find(o => (o.order_id || o.booking_id) === parseInt(orderId))

      if (raw) {
        const ps = raw.payment_status
        const displayStatus =
          ps === 'awaiting_payment' ? 'awaiting_payment' :
          ps === 'awaiting_proof' ? 'awaiting_proof' :
          ps === 'proof_submitted' ? 'proof_submitted' :
          ps === 'rejected' ? 'payment_rejected' :
          (raw.order_status || raw.status || 'pending')

        foundOrder = {
          ...raw,
          order_id: raw.order_id || raw.booking_id,
          status: displayStatus,
          offer_title: raw.items?.[0]?.offer_title || raw.offer_title || 'Buyurtma',
          offer_photo: apiClient.getPhotoUrl(raw.items?.[0]?.photo) || raw.offer_photo,
          store_name: raw.store_name || raw.items?.[0]?.store_name,
          quantity: raw.quantity || raw.items?.reduce((sum, item) => sum + (item.quantity || 0), 0) || 1,
          items: raw.items || [],
          booking_code: raw.booking_code || raw.pickup_code || raw.booking_code,
        }
      }

      if (!foundOrder) {
        setError('Buyurtma topilmadi')
        return
      }

      setOrder(foundOrder)
      setError(null)
    } catch (err) {
      console.error('Failed to load order details:', err)
      setError('Buyurtma ma\'lumotlarini yuklab bo\'lmadi')
    } finally {
      setLoading(false)
    }
  }

  const getStatusInfo = (status) => {
    const statusMap = {
      pending: { text: 'Kutilmoqda', color: '#FF6B35', bg: '#FFF4F0' },
      preparing: { text: 'Tayyorlanmoqda', color: '#10B981', bg: '#ECFDF5' },
      ready: { text: 'Tayyor', color: '#8B5CF6', bg: '#FAF5FF' },
      delivering: { text: "Yo'lda", color: '#3B82F6', bg: '#EFF6FF' },
      completed: { text: 'Bajarildi', color: '#10B981', bg: '#ECFDF5' },
      cancelled: { text: 'Bekor qilindi', color: '#EF4444', bg: '#FEF2F2' },
      rejected: { text: 'Rad etildi', color: '#EF4444', bg: '#FEF2F2' },
      awaiting_payment: { text: 'To\'lov kutilmoqda', color: '#F59E0B', bg: '#FFFBEB' },
      awaiting_proof: { text: 'Chek kutilmoqda', color: '#F59E0B', bg: '#FFFBEB' },
      proof_submitted: { text: 'Tekshirilmoqda', color: '#3B82F6', bg: '#EFF6FF' },
      payment_rejected: { text: 'To\'lov rad etildi', color: '#EF4444', bg: '#FEF2F2' },
    }
    return statusMap[status] || { text: status, color: '#6B7280', bg: '#F3F4F6' }
  }

  const formatDate = (dateString) => {
    if (!dateString) return '-'
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

  const handlePayOnline = async () => {
    const provider = order?.payment_method
    if (!provider || !['click', 'payme'].includes(provider)) {
      return
    }

    try {
      const storeId = order.store_id || null
      const available = await apiClient.getPaymentProviders(storeId)
      if (!available.includes(provider)) {
        if (window.Telegram?.WebApp) {
          window.Telegram.WebApp.showAlert('Bu to\'lov usuli hozircha mavjud emas.')
        }
        return
      }

      const returnUrl = window.location.origin + `/order/${orderId}/details`
      const paymentData = await apiClient.createPaymentLink(
        order.order_id,
        provider,
        returnUrl,
        storeId,
        order.total_price || null
      )

      if (paymentData?.payment_url) {
        if (window.Telegram?.WebApp) {
          window.Telegram.WebApp.openLink(paymentData.payment_url)
        } else {
          window.location.href = paymentData.payment_url
        }
      }
    } catch (err) {
      console.error('Failed to open payment link:', err)
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
        <div className="details-header">
          <button className="app-back-btn" onClick={() => navigate('/profile')} aria-label="Orqaga">
            <ArrowLeft size={20} strokeWidth={2} />
          </button>
          <h1 className="details-title">Buyurtma</h1>
        </div>
        <div className="error-container">
          <div className="error-icon">!</div>
          <p>{error || 'Xatolik yuz berdi'}</p>
        </div>
      </div>
    )
  }

  const statusInfo = getStatusInfo(order.status)
  const isDelivery = order.order_type === 'delivery' || order.delivery_address
  const needsPayment = ['awaiting_payment', 'awaiting_proof', 'payment_rejected'].includes(order.status)
  const canPayOnline = order.payment_method && ['click', 'payme'].includes(order.payment_method)
  const paymentMethodLabels = {
    cash: 'Naqd',
    card: 'Karta',
    click: 'Click',
    payme: 'Payme',
  }

  return (
    <div className="order-details-page">
      {/* Header */}
      <div className="details-header">
        <button className="app-back-btn" onClick={() => navigate('/profile')} aria-label="Orqaga">
          <ArrowLeft size={20} strokeWidth={2} />
        </button>
        <h1 className="details-title">Buyurtma #{orderId}</h1>
      </div>

      {/* Status Banner */}
      <div className="status-banner" style={{ background: statusInfo.bg }}>
        <span className="status-text" style={{ color: statusInfo.color }}>
          {statusInfo.text}
        </span>
        <span className="order-date">{formatDate(order.created_at)}</span>
      </div>

      {needsPayment && (
        <div className="payment-banner">
          <h3>To'lov holati</h3>
          {order.status === 'awaiting_payment' && (
            <p>To'lovni yakunlang. Buyurtma to'liq tasdiqlanishi uchun to'lov kerak.</p>
          )}
          {order.status === 'awaiting_proof' && (
            <p>Chek yuborilishi kerak. To'lovni tasdiqlash uchun chek yuboring.</p>
          )}
          {order.status === 'payment_rejected' && (
            <p>To'lov rad etildi. Yangi chek yuboring yoki onlayn to'lov qiling.</p>
          )}

          <div className="payment-actions">
            {canPayOnline && (
              <button className="payment-btn primary" onClick={handlePayOnline}>
                {order.payment_method === 'click' ? 'Click bilan to\'lash' : 'Payme bilan to\'lash'}
              </button>
            )}
            {(order.status !== 'awaiting_payment' || !canPayOnline) && (
              <button className="payment-btn secondary" onClick={handleUploadProof}>
                Chekni yuborish
              </button>
            )}
          </div>
        </div>
      )}

      {/* Order Items */}
      <div className="details-section">
        <h2 className="section-title">Mahsulotlar</h2>
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
                  <p className="item-store">Do'kon: {item.store_name}</p>
                  <div className="item-meta">
                    <span className="item-quantity">{item.quantity} x {Math.round(item.price).toLocaleString()} so'm</span>
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
                <p className="item-store">Do'kon: {order.store_name}</p>
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
          <h2 className="section-title">Yetkazib berish</h2>
          <div className="info-card">
            <div className="info-row">
              <span className="info-label">Manzil:</span>
              <span className="info-value">{order.delivery_address}</span>
            </div>
            {order.phone && (
              <div className="info-row">
                <span className="info-label">Telefon:</span>
                <span className="info-value">{order.phone}</span>
              </div>
            )}
            {order.delivery_notes && (
              <div className="info-row">
                <span className="info-label">Izoh:</span>
                <span className="info-value">{order.delivery_notes}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Pickup Info */}
      {!isDelivery && order.booking_code && (
        <div className="details-section">
        <h2 className="section-title">Olib ketish</h2>
        <div className="info-card">
          <div className="info-row">
              <span className="info-label">Kod:</span>
            <span className="info-value booking-code">{order.booking_code}</span>
          </div>
          {order.pickup_time && (
            <div className="info-row">
                <span className="info-label">Vaqt:</span>
              <span className="info-value">{formatDate(order.pickup_time)}</span>
            </div>
          )}
        </div>
      </div>
      )}

      {/* Payment Info */}
      <div className="details-section">
        <h2 className="section-title">To'lov</h2>
        <div className="info-card">
          <div className="info-row">
            <span className="info-label">Usul:</span>
            <span className="info-value">
              {paymentMethodLabels[order.payment_method] || 'Naqd'}
            </span>
          </div>
          <div className="info-row total-row">
            <span className="info-label">Jami:</span>
            <span className="info-value total-price">
              {Math.round(order.total_price || 0).toLocaleString()} so'm
            </span>
          </div>
        </div>
      </div>

      {/* Contact Support */}
      <div className="support-section">
        <p className="support-text">Savollar bormi?</p>
        <button
          className="support-btn"
          onClick={() => {
            if (window.Telegram?.WebApp) {
              window.Telegram.WebApp.openTelegramLink('https://t.me/fudly_support')
            }
          }}
        >
          Qo'llab-quvvatlash
        </button>
      </div>
    </div>
  )
}

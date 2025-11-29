import React, { useEffect, useState } from 'react';
import api from '../api/client';
import { getCurrentUser } from '../utils/auth';
import BottomNav from '../components/BottomNav';
import './OrderTrackingPage.css';

const STATUS_STEPS = {
  'pending': { order: 1, label: { ru: 'Создан', uz: 'Yaratildi' } },
  'confirmed': { order: 2, label: { ru: 'Подтвержден', uz: 'Tasdiqlandi' } },
  'ready': { order: 3, label: { ru: 'Готов', uz: 'Tayyor' } },
  'completed': { order: 4, label: { ru: 'Завершен', uz: 'Yakunlandi' } },
  'cancelled': { order: -1, label: { ru: 'Отменен', uz: 'Bekor qilindi' } }
};

function OrderTrackingPage({ user, bookingId, onNavigate }) {
  const [cartCount, setCartCount] = useState(() => {
    const saved = localStorage.getItem('fudly_cart')
    const cart = saved ? JSON.parse(saved) : {}
    return Object.keys(cart).length
  });
  const [order, setOrder] = useState(null);
  const [timeline, setTimeline] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showQR, setShowQR] = useState(false);

  const lang = user?.language || 'ru';
  const t = (ru, uz) => (lang === 'uz' ? uz : ru);

  useEffect(() => {
    loadOrderData(true);
    // Refresh every 30 seconds for real-time updates
    const interval = setInterval(() => loadOrderData(false), 30000);
    return () => clearInterval(interval);
  }, [bookingId]);

  const loadOrderData = async (withSpinner = false) => {
    if (!bookingId) {
      setError(t('Некорректный идентификатор заказа', 'Buyurtma identifikatori noto\'g\'ri'));
      setLoading(false);
      return;
    }

    if (withSpinner) {
      setLoading(true);
    }

    try {
      const currentUser = getCurrentUser();
      if (!currentUser) {
        onNavigate('home');
        return;
      }

      // Load order status
      const statusData = await api.getOrderStatus(bookingId);
      setOrder(statusData);

      // Load timeline
      try {
        const timelineData = await api.getOrderTimeline(bookingId);
        setTimeline(timelineData);
      } catch (timelineError) {
        console.warn('Timeline load failed', timelineError);
        setTimeline(null);
      }
    } catch (err) {
      console.error('Error loading order:', err);
      setError(err.message);
    } finally {
      if (withSpinner) {
        setLoading(false);
      }
    }
  };

  const handleShowQR = () => {
    setShowQR(true);
  };

  const handleCloseQR = () => {
    setShowQR(false);
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'pending': return '#FFA500';
      case 'confirmed': return '#4CAF50';
      case 'ready': return '#2196F3';
      case 'completed': return '#9E9E9E';
      case 'cancelled': return '#F44336';
      default: return '#9E9E9E';
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'pending': return '⏳';
      case 'confirmed': return '✅';
      case 'ready': return '🎁';
      case 'completed': return '✓';
      case 'cancelled': return '❌';
      default: return '•';
    }
  };

  if (loading) {
    return (
      <div className="order-tracking-page">
        <div className="loading-container">
          <div className="spinner"></div>
          <p>{t('Загрузка заказа...', 'Buyurtma yuklanmoqda...')}</p>
        </div>
      </div>
    );
  }

  if (error || !order) {
    return (
      <div className="order-tracking-page">
        <div className="error-container">
          <p className="error-icon">⚠️</p>
          <p className="error-message">{error || t('Заказ не найден', 'Buyurtma topilmadi')}</p>
          <button onClick={() => onNavigate('profile')} className="back-btn">
            {t('Вернуться', 'Qaytish')}
          </button>
        </div>
      </div>
    );
  }

  const currentStatusOrder = STATUS_STEPS[order.status]?.order || 0;
  const isCancelled = order.status === 'cancelled';
  const canShowQR = ['confirmed', 'ready'].includes(order.status) && order.qr_code;

  return (
    <div className="order-tracking-page">
      <div className="tracking-header">
        <button onClick={() => onNavigate('profile')} className="back-button">
          ← {t('Назад', 'Orqaga')}
        </button>
        <h1>{t('Заказ', 'Buyurtma')} #{order.booking_code}</h1>
      </div>

      {/* Order Status Card */}
      <div className="order-status-card">
        <div className="status-badge" style={{ backgroundColor: getStatusColor(order.status) }}>
          {getStatusIcon(order.status)} {STATUS_STEPS[order.status]?.label[lang] || order.status}
        </div>

        {timeline?.estimated_ready_time && order.status === 'confirmed' && (
          <div className="estimated-time">
            ⏱️ {t('Будет готов', 'Tayyor bo\'ladi')}: {timeline.estimated_ready_time}
          </div>
        )}

        <div className="order-details">
          <h3>{order.offer_title}</h3>
          <p className="quantity">
            {t('Количество', 'Miqdor')}: {order.quantity} {t('шт', 'dona')}
          </p>
          <p className="price">
            {t('Сумма', 'Summa')}: {order.total_price.toLocaleString()} {t('сум', 'so\'m')}
          </p>
        </div>

        {order.offer_photo && (
          <img src={order.offer_photo} alt={order.offer_title} className="order-photo" />
        )}
      </div>

      {/* Timeline */}
      {timeline && !isCancelled && (
        <div className="timeline-container">
          <h2>{t('История заказа', 'Buyurtma tarixi')}</h2>
          <div className="timeline">
            {timeline.timeline.map((item, index) => {
              const isActive = STATUS_STEPS[item.status]?.order <= currentStatusOrder;
              const isCurrent = item.status === order.status;

              return (
                <div key={index} className={`timeline-item ${isActive ? 'active' : ''} ${isCurrent ? 'current' : ''}`}>
                  <div className="timeline-marker">
                    <div className="timeline-dot"></div>
                    {index < timeline.timeline.length - 1 && <div className="timeline-line"></div>}
                  </div>
                  <div className="timeline-content">
                    <h4>{STATUS_STEPS[item.status]?.label[lang] || item.status}</h4>
                    <p className="timeline-message">{item.message}</p>
                    <p className="timeline-time">{new Date(item.timestamp).toLocaleString('ru-RU')}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Store Info */}
      <div className="store-info-card">
        <h3>{t('Магазин', 'Do\'kon')}</h3>
        <p className="store-name">{order.store_name}</p>
        {order.store_address && (
          <p className="store-address">📍 {order.store_address}</p>
        )}
        {order.store_phone && (
          <p className="store-phone">
            <a href={`tel:${order.store_phone}`}>📞 {order.store_phone}</a>
          </p>
        )}
      </div>

      {/* Pickup/Delivery Info */}
      {(order.pickup_address || order.delivery_address) && (
        <div className="delivery-info-card">
          <h3>{order.delivery_address ? t('Доставка', 'Yetkazib berish') : t('Самовывоз', 'Olib ketish')}</h3>
          {order.delivery_address && (
            <>
              <p className="delivery-address">📍 {order.delivery_address}</p>
              {order.delivery_cost && (
                <p className="delivery-cost">
                  {t('Стоимость доставки', 'Yetkazib berish narxi')}: {order.delivery_cost.toLocaleString()} {t('сум', 'so\'m')}
                </p>
              )}
            </>
          )}
          {order.pickup_address && (
            <p className="pickup-address">📍 {order.pickup_address}</p>
          )}
          {order.pickup_time && (
            <p className="pickup-time">⏰ {order.pickup_time}</p>
          )}
        </div>
      )}

      {/* QR Code Button */}
      {canShowQR && (
        <button onClick={handleShowQR} className="qr-button">
          📱 {t('Показать QR код', 'QR kodni ko\'rsatish')}
        </button>
      )}

      {/* QR Code Modal */}
      {showQR && order.qr_code && (
        <div className="qr-modal" onClick={handleCloseQR}>
          <div className="qr-modal-content" onClick={(e) => e.stopPropagation()}>
            <button onClick={handleCloseQR} className="close-btn">✕</button>
            <h2>{t('QR код для выдачи', 'Olib ketish uchun QR kod')}</h2>
            <p className="qr-instruction">
              {t('Покажите этот код в магазине', 'Bu kodni do\'konda ko\'rsating')}
            </p>
            <img src={order.qr_code} alt="QR Code" className="qr-code-image" />
            <p className="booking-code">{order.booking_code}</p>
          </div>
        </div>
      )}

      <BottomNav currentPage="profile" onNavigate={onNavigate} cartCount={cartCount} />
    </div>
  );
}

export default OrderTrackingPage;

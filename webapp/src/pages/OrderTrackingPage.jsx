import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useLocation, useParams } from 'react-router-dom';
import api from '../api/client';
import { useCart } from '../context/CartContext';
import { getCurrentUser } from '../utils/auth';
import { resolveOrderItemImageUrl } from '../utils/imageUtils';
import { normalizeOrderStatus, paymentStatusText, resolveOrderType, statusText } from '../utils/orderStatus';
import BottomNav from '../components/BottomNav';
import PullToRefresh from '../components/PullToRefresh';
import { usePullToRefresh } from '../hooks/usePullToRefresh';
import './OrderTrackingPage.css';

const STATUS_ORDER = {
  pending: 1,
  preparing: 2,
  ready: 3,
  delivering: 4,
  completed: 5,
  cancelled: -1,
  rejected: -1,
};

function OrderTrackingPage({ user }) {
  const navigate = useNavigate();
  const location = useLocation();
  const params = useParams();
  const { cartCount } = useCart();

  // Get orderId from URL params or route state
  const bookingId = params.orderId || location.state?.bookingId;

  const [order, setOrder] = useState(null);
  const [timeline, setTimeline] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showQR, setShowQR] = useState(false);
  const [statusPulse, setStatusPulse] = useState(false);
  const prevStatusRef = useRef(null);

  const lang = user?.language || 'ru';
  const t = (ru, uz) => (lang === 'uz' ? uz : ru);

  const formatPhone = (raw) => {
    if (!raw) return '';
    const sanitized = String(raw).replace(/[^0-9+]/g, '');
    const digits = sanitized.replace(/\D/g, '');
    if (digits.startsWith('998') && digits.length === 12) {
      return `+998 ${digits.slice(3, 5)} ${digits.slice(5, 8)} ${digits.slice(8, 10)} ${digits.slice(10, 12)}`;
    }
    if (sanitized.startsWith('+') && digits) {
      return `+${digits}`;
    }
    return sanitized || String(raw);
  };

  const phoneLink = (raw) => {
    if (!raw) return '';
    return String(raw).replace(/[^0-9+]/g, '');
  };

  useEffect(() => {
    loadOrderData(true);
    // Refresh every 30 seconds for real-time updates
    const interval = setInterval(() => loadOrderData(false), 30000);
    return () => clearInterval(interval);
  }, [bookingId]);

  useEffect(() => {
    if (!order?.status) return;
    if (prevStatusRef.current && prevStatusRef.current !== order.status) {
      setStatusPulse(true);
      const timer = setTimeout(() => setStatusPulse(false), 420);
      prevStatusRef.current = order.status;
      return () => clearTimeout(timer);
    }
    prevStatusRef.current = order.status;
    return undefined;
  }, [order?.status]);

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
        navigate('/');
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

  const handleRefresh = useCallback(async () => {
    await loadOrderData(false);
  }, [loadOrderData]);

  const { containerRef, isRefreshing, pullDistance, progress } = usePullToRefresh(handleRefresh);

  const getStatusColor = (status) => {
    switch (normalizeOrderStatus(status)) {
      case 'pending': return '#FFA500';
      case 'preparing': return '#4CAF50';
      case 'ready': return '#2196F3';
      case 'delivering': return '#2196F3';
      case 'completed': return '#9E9E9E';
      case 'cancelled': return '#F44336';
      case 'rejected': return '#F44336';
      default: return '#9E9E9E';
    }
  };

  const getStatusIcon = (status) => {
    switch (normalizeOrderStatus(status)) {
      case 'pending': return '...';
      case 'preparing': return 'OK';
      case 'ready': return 'RDY';
      case 'delivering': return 'WAY';
      case 'completed': return 'OK';
      case 'cancelled': return 'X';
      case 'rejected': return 'X';
      default: return '.';
    }
  };

  const paymentStatusLabel = () => paymentStatusText(order?.payment_status, lang);

  if (loading) {
    return (
      <div ref={containerRef} className="order-tracking-page">
        <PullToRefresh
          isRefreshing={isRefreshing}
          pullDistance={pullDistance}
          progress={progress}
        />
        <div className="tracking-loading">
          <div className="tracking-spinner"></div>
          <p>{t('Загрузка заказа...', 'Buyurtma yuklanmoqda...')}</p>
        </div>
      </div>
    );
  }

  if (error || !order) {
    return (
      <div ref={containerRef} className="order-tracking-page">
        <PullToRefresh
          isRefreshing={isRefreshing}
          pullDistance={pullDistance}
          progress={progress}
        />
        <header className="app-header">
          <div className="app-header-inner">
            <div className="app-header-spacer" aria-hidden="true" />
            <div className="app-header-title">
              <h1 className="app-header-title-text">{t('Заказ', 'Buyurtma')}</h1>
            </div>
            <div className="app-header-spacer" aria-hidden="true" />
          </div>
        </header>
        <div className="tracking-error">
          <p className="tracking-error-icon">!</p>
          <p className="tracking-error-message">{error || t('Заказ не найден', 'Buyurtma topilmadi')}</p>
        </div>
      </div>
    );
  }

  const normalizedStatus = normalizeOrderStatus(order.status);
  const orderType = resolveOrderType(order);
  const currentStatusOrder = STATUS_ORDER[normalizedStatus] || 0;
  const isCancelled = ['cancelled', 'rejected'].includes(normalizedStatus);
  const canShowQR = ['preparing', 'ready'].includes(normalizedStatus) && order.qr_code;
  const orderPhotoUrl = resolveOrderItemImageUrl(order);
  const displayTotal = Number(order?.total_with_delivery ?? order?.total_price ?? 0);
  const orderCode = order.booking_code || order.booking_id || order.order_id || bookingId;

  return (
    <div ref={containerRef} className="order-tracking-page">
      <PullToRefresh
        isRefreshing={isRefreshing}
        pullDistance={pullDistance}
        progress={progress}
      />
      <header className="app-header">
        <div className="app-header-inner">
          <div className="app-header-spacer" aria-hidden="true" />
          <div className="app-header-title">
            <h1 className="app-header-title-text">{t('Заказ', 'Buyurtma')} #{orderCode}</h1>
          </div>
          <div className="app-header-spacer" aria-hidden="true" />
        </div>
      </header>

      {/* Order Status Card */}
      <div className="order-status-card">
        <div className={`status-badge ${statusPulse ? 'pulse' : ''}`} style={{ backgroundColor: getStatusColor(order.status) }}>
          {getStatusIcon(normalizedStatus)} {statusText(normalizedStatus, lang, orderType)}
        </div>
        {paymentStatusLabel() && (
          <div className="payment-status-chip">
            {paymentStatusLabel()}
          </div>
        )}

        {timeline?.estimated_ready_time && ['preparing'].includes(normalizedStatus) && (
          <div className="estimated-time">
            {t('Будет готов', 'Tayyor bo\'ladi')}: {timeline.estimated_ready_time}
          </div>
        )}

        <div className="order-details">
          <h3>{order.offer_title}</h3>
          <p className="quantity">
            {t('Количество', 'Miqdor')}: {order.quantity} {t('шт', 'dona')}
          </p>
          <p className="price">
            {t('Сумма', 'Summa')}: {Math.round(displayTotal).toLocaleString()} {t('сум', 'so\'m')}
          </p>
        </div>

        {orderPhotoUrl && (
          <img
            src={orderPhotoUrl}
            alt={order.offer_title}
            className="order-photo"
            loading="lazy"
            decoding="async"
          />
        )}
      </div>

      {/* Timeline */}
      {timeline && !isCancelled && (
        <div className="timeline-container">
          <h2>{t('История заказа', 'Buyurtma tarixi')}</h2>
          <div className="timeline">
            {timeline.timeline.map((item, index) => {
              const itemStatus = normalizeOrderStatus(item.status);
              const isActive = (STATUS_ORDER[itemStatus] || 0) <= currentStatusOrder;
              const isCurrent = itemStatus === normalizedStatus;

              return (
                <div key={index} className={`timeline-item ${isActive ? 'active' : ''} ${isCurrent ? 'current' : ''}`}>
                  <div className="timeline-marker">
                    <div className="timeline-dot"></div>
                    {index < timeline.timeline.length - 1 && <div className="timeline-line"></div>}
                  </div>
                  <div className="timeline-content">
                    <h4>{statusText(itemStatus, lang, orderType)}</h4>
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
          <p className="store-address">Manzil: {order.store_address}</p>
        )}
        {order.store_phone && (
          <div className="store-phone">
            <a className="store-phone-btn" href={`tel:${phoneLink(order.store_phone)}`}>
              📞 {t('Связаться с магазином', "Do'kon bilan bog'lanish")}
            </a>
            <span className="store-phone-number">{formatPhone(order.store_phone)}</span>
          </div>
        )}
      </div>

      {/* Pickup/Delivery Info */}
      {(order.pickup_address || order.delivery_address) && (
        <div className="delivery-info-card">
          <h3>{order.delivery_address ? t('Доставка', 'Yetkazib berish') : t('Самовывоз', 'Olib ketish')}</h3>
          {order.delivery_address && (
            <>
              <p className="delivery-address">Manzil: {order.delivery_address}</p>
              {order.delivery_cost && (
                <p className="delivery-cost">
                  {t('Стоимость доставки', 'Yetkazib berish narxi')}: {order.delivery_cost.toLocaleString()} {t('сум', 'so\'m')}
                </p>
              )}
            </>
          )}
          {order.pickup_address && (
            <p className="pickup-address">Manzil: {order.pickup_address}</p>
          )}
          {order.pickup_time && (
            <p className="pickup-time">Vaqt: {order.pickup_time}</p>
          )}
        </div>
      )}

      {/* QR Code Button */}
      {canShowQR && (
        <button onClick={handleShowQR} className="btn-primary qr-button">
          {t('Показать QR код', 'QR kodni ko\'rsatish')}
        </button>
      )}

      {/* QR Code Modal */}
      {showQR && order.qr_code && (
        <div className="qr-modal" onClick={handleCloseQR}>
          <div className="qr-modal-content" onClick={(e) => e.stopPropagation()}>
            <button onClick={handleCloseQR} className="close-btn">x</button>
            <h2>{t('QR код для выдачи', 'Olib ketish uchun QR kod')}</h2>
            <p className="qr-instruction">
              {t('Покажите этот код в магазине', 'Bu kodni do\'konda ko\'rsating')}
            </p>
            <img
              src={order.qr_code}
              alt="QR Code"
              className="qr-code-image"
              loading="eager"
              decoding="async"
            />
            <p className="booking-code">{order.booking_code}</p>
          </div>
        </div>
      )}

      <BottomNav currentPage="profile" cartCount={cartCount} />
    </div>
  );
}

export default OrderTrackingPage;





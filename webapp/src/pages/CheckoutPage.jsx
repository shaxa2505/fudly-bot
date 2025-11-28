import React, { useState, useEffect } from 'react';
import { getCurrentUser, getUserCity } from '../utils/auth';
import { API_BASE_URL } from '../api/client';
import BottomNav from '../components/BottomNav';
import './CheckoutPage.css';

const DELIVERY_TYPE = {
  PICKUP: 'pickup',
  DELIVERY: 'delivery'
};

function CheckoutPage({ user, onNavigate }) {
  const [cart, setCart] = useState(() => {
    const saved = localStorage.getItem('fudly_cart')
    return saved ? new Map(Object.entries(JSON.parse(saved))) : new Map()
  })
  const [cartData, setCartData] = useState([]);
  const [deliveryType, setDeliveryType] = useState(DELIVERY_TYPE.PICKUP);
  const [address, setAddress] = useState('');
  const [deliveryInfo, setDeliveryInfo] = useState(null);
  const [loading, setLoading] = useState(false);
  const [calculatingDelivery, setCalculatingDelivery] = useState(false);
  const [error, setError] = useState(null);

  const lang = user?.language || 'ru';
  const t = (ru, uz) => (lang === 'uz' ? uz : ru);
  const city = getUserCity() || 'Ташкент';

  useEffect(() => {
    if (cart.size === 0) {
      onNavigate('cart');
    } else {
      // Convert cart Map to array with mock data for now
      const items = Array.from(cart.entries()).map(([id, qty]) => ({
        id: parseInt(id),
        title: `Товар ${id}`,
        price: 50000,
        quantity: qty,
        storeId: 1,
        storeAddress: 'Адрес магазина'
      }))
      setCartData(items)
    }
  }, [cart, onNavigate]);

  useEffect(() => {
    if (deliveryType === DELIVERY_TYPE.DELIVERY && address.length > 5) {
      const timer = setTimeout(() => {
        calculateDelivery();
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [address, deliveryType]);

  const calculateDelivery = async () => {
    if (!address || address.length < 5) return;

    setCalculatingDelivery(true);
    setError(null);

    try {
      const currentUser = getCurrentUser();
      const storeId = cart[0]?.storeId || 1; // Use first item's store

      const response = await fetch(`${API_BASE_URL}/api/v1/orders/calculate-delivery`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: currentUser.user_id,
          city,
          address,
          store_id: storeId
        })
      });

      if (!response.ok) {
        throw new Error('Failed to calculate delivery');
      }

      const data = await response.json();
      setDeliveryInfo(data);

      if (!data.can_deliver) {
        setError(data.message || t('Доставка недоступна', 'Yetkazib berish mavjud emas'));
      }
    } catch (err) {
      console.error('Error calculating delivery:', err);
      setError(t('Ошибка расчета доставки', 'Yetkazib berish xatosi'));
    } finally {
      setCalculatingDelivery(false);
    }
  };

  const calculateTotal = () => {
    const itemsTotal = cartData.reduce((sum, item) => sum + (item.price * item.quantity), 0);
    const deliveryCost = (deliveryType === DELIVERY_TYPE.DELIVERY && deliveryInfo?.delivery_cost) 
      ? deliveryInfo.delivery_cost 
      : 0;
    return itemsTotal + deliveryCost;
  };

  const handlePlaceOrder = async () => {
    if (deliveryType === DELIVERY_TYPE.DELIVERY) {
      if (!address || address.length < 5) {
        setError(t('Введите адрес доставки', 'Yetkazib berish manzilini kiriting'));
        return;
      }
      if (!deliveryInfo?.can_deliver) {
        setError(t('Доставка по этому адресу недоступна', 'Bu manzilga yetkazib berish mavjud emas'));
        return;
      }
    }

    setLoading(true);
    setError(null);

    try {
      const currentUser = getCurrentUser();

      // Create bookings for each cart item
      for (const item of cartData) {
        const bookingData = {
          offer_id: item.id,
          user_id: currentUser.user_id,
          quantity: item.quantity,
          delivery_address: deliveryType === DELIVERY_TYPE.DELIVERY ? address : null,
          pickup_address: deliveryType === DELIVERY_TYPE.PICKUP ? item.storeAddress : null
        };

        const response = await fetch(`${API_BASE_URL}/api/v1/bookings`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(bookingData)
        });

        if (!response.ok) {
          throw new Error('Failed to create booking');
        }
      }

      // Clear cart and navigate to profile
      setCart(new Map())
      localStorage.setItem('fudly_cart', JSON.stringify({}))
      
      // Show success message
      if (window.Telegram?.WebApp) {
        window.Telegram.WebApp.showAlert(
          t('Заказ успешно оформлен!', 'Buyurtma muvaffaqiyatli qabul qilindi!'),
          () => onNavigate('profile')
        );
      } else {
        alert(t('Заказ успешно оформлен!', 'Buyurtma muvaffaqiyatli qabul qilindi!'));
        onNavigate('profile');
      }
    } catch (err) {
      console.error('Error placing order:', err);
      setError(t('Ошибка при оформлении заказа', 'Buyurtma qabul qilishda xato'));
      setLoading(false);
    }
  };

  const total = calculateTotal();
  const itemsTotal = cartData.reduce((sum, item) => sum + (item.price * item.quantity), 0);
  const deliveryCost = (deliveryType === DELIVERY_TYPE.DELIVERY && deliveryInfo?.delivery_cost) 
    ? deliveryInfo.delivery_cost 
    : 0;

  return (
    <div className="checkout-page">
      <div className="checkout-header">
        <button onClick={() => onNavigate('cart')} className="back-button">
          ← {t('Назад', 'Orqaga')}
        </button>
        <h1>{t('Оформление заказа', 'Buyurtmani rasmiylashtirish')}</h1>
      </div>

      <div className="checkout-content">
        {/* Delivery Type Selection */}
        <div className="delivery-type-section">
          <h2>{t('Способ получения', 'Olish usuli')}</h2>
          <div className="delivery-options">
            <button
              className={`delivery-option ${deliveryType === DELIVERY_TYPE.PICKUP ? 'active' : ''}`}
              onClick={() => setDeliveryType(DELIVERY_TYPE.PICKUP)}
            >
              <span className="option-icon">🏪</span>
              <div className="option-content">
                <h3>{t('Самовывоз', 'Olib ketish')}</h3>
                <p>{t('Заберу сам из магазина', 'O\'zim do\'kondan olaman')}</p>
              </div>
              {deliveryType === DELIVERY_TYPE.PICKUP && <span className="check-mark">✓</span>}
            </button>

            <button
              className={`delivery-option ${deliveryType === DELIVERY_TYPE.DELIVERY ? 'active' : ''}`}
              onClick={() => setDeliveryType(DELIVERY_TYPE.DELIVERY)}
            >
              <span className="option-icon">🚚</span>
              <div className="option-content">
                <h3>{t('Доставка', 'Yetkazib berish')}</h3>
                <p>{t('Доставить по адресу', 'Manzilga yetkazib berish')}</p>
              </div>
              {deliveryType === DELIVERY_TYPE.DELIVERY && <span className="check-mark">✓</span>}
            </button>
          </div>
        </div>

        {/* Delivery Address Input */}
        {deliveryType === DELIVERY_TYPE.DELIVERY && (
          <div className="address-section">
            <h2>{t('Адрес доставки', 'Yetkazib berish manzili')}</h2>
            <div className="address-input-group">
              <input
                type="text"
                placeholder={t('Улица, дом, квартира...', 'Ko\'cha, uy, xonadon...')}
                value={address}
                onChange={(e) => setAddress(e.target.value)}
                className="address-input"
              />
              <p className="city-label">📍 {city}</p>
            </div>

            {calculatingDelivery && (
              <div className="calculating-delivery">
                <div className="mini-spinner"></div>
                <p>{t('Рассчитываем стоимость...', 'Narxni hisoblayapmiz...')}</p>
              </div>
            )}

            {deliveryInfo && !calculatingDelivery && (
              <div className={`delivery-result ${deliveryInfo.can_deliver ? 'success' : 'error'}`}>
                {deliveryInfo.can_deliver ? (
                  <>
                    <p className="delivery-cost-label">
                      {t('Стоимость доставки', 'Yetkazib berish narxi')}: 
                      <span className="delivery-cost-value">
                        {deliveryInfo.delivery_cost.toLocaleString()} {t('сум', 'so\'m')}
                      </span>
                    </p>
                    {deliveryInfo.estimated_time && (
                      <p className="delivery-time">⏱️ {deliveryInfo.estimated_time}</p>
                    )}
                    {deliveryInfo.min_order_amount && itemsTotal < deliveryInfo.min_order_amount && (
                      <p className="min-order-warning">
                        ⚠️ {t('Минимальная сумма заказа', 'Minimal buyurtma summasi')}: {deliveryInfo.min_order_amount.toLocaleString()} {t('сум', 'so\'m')}
                      </p>
                    )}
                  </>
                ) : (
                  <p className="delivery-error">❌ {deliveryInfo.message}</p>
                )}
              </div>
            )}
          </div>
        )}

        {/* Order Summary */}
        <div className="order-summary">
          <h2>{t('Ваш заказ', 'Sizning buyurtmangiz')}</h2>
          <div className="summary-items">
            {cartData.map((item, index) => (
              <div key={index} className="summary-item">
                <div className="item-info">
                  <p className="item-title">{item.title}</p>
                  <p className="item-quantity">{item.quantity} {t('шт', 'dona')}</p>
                </div>
                <p className="item-price">{(item.price * item.quantity).toLocaleString()}</p>
              </div>
            ))}
          </div>

          <div className="summary-totals">
            <div className="summary-row">
              <span>{t('Товары', 'Mahsulotlar')}:</span>
              <span>{itemsTotal.toLocaleString()} {t('сум', 'so\'m')}</span>
            </div>
            {deliveryCost > 0 && (
              <div className="summary-row">
                <span>{t('Доставка', 'Yetkazib berish')}:</span>
                <span>{deliveryCost.toLocaleString()} {t('сум', 'so\'m')}</span>
              </div>
            )}
            <div className="summary-row total">
              <span>{t('Итого', 'Jami')}:</span>
              <span>{total.toLocaleString()} {t('сум', 'so\'m')}</span>
            </div>
          </div>
        </div>

        {/* Error Message */}
        {error && (
          <div className="error-message">
            <p>⚠️ {error}</p>
          </div>
        )}

        {/* Place Order Button */}
        <button
          onClick={handlePlaceOrder}
          disabled={loading || (deliveryType === DELIVERY_TYPE.DELIVERY && !deliveryInfo?.can_deliver)}
          className="place-order-button"
        >
          {loading ? (
            <>
              <div className="button-spinner"></div>
              {t('Оформление...', 'Rasmiylashtirish...')}
            </>
          ) : (
            <>
              {t('Оформить заказ', 'Buyurtma berish')} • {total.toLocaleString()} {t('сум', 'so\'m')}
            </>
          )}
        </button>
      </div>

      <BottomNav currentPage="cart" onNavigate={onNavigate} cartCount={cart.size} />
    </div>
  );
}

export default CheckoutPage;

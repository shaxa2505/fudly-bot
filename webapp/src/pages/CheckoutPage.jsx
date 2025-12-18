import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../api/client';
import { getCurrentUser, getUserCity } from '../utils/auth';
import { getUnitLabel } from '../utils/helpers';
import BottomNav from '../components/BottomNav';
import './CheckoutPage.css';

const DELIVERY_TYPE = {
  PICKUP: 'pickup',
  DELIVERY: 'delivery'
};

const PAYMENT_METHOD = {
  CASH: 'cash',
  CARD_TRANSFER: 'card_transfer',
  CLICK: 'click',
  PAYME: 'payme'
};

// Helper to read cart from localStorage (new format: { offerId: { offer, quantity } })
const getCartFromStorage = () => {
  try {
    const saved = localStorage.getItem('fudly_cart_v2');
    return saved ? JSON.parse(saved) : {};
  } catch {
    return {};
  }
};

function CheckoutPage({ user }) {
  const navigate = useNavigate();
  // New cart format: { offerId: { offer: {...}, quantity: number } }
  const [cart, setCart] = useState(getCartFromStorage);
  const [cartSummaryLoading, setCartSummaryLoading] = useState(false);
  const [deliveryType, setDeliveryType] = useState(DELIVERY_TYPE.PICKUP);
  const [paymentMethod, setPaymentMethod] = useState(PAYMENT_METHOD.CASH);
  const [address, setAddress] = useState('');
  const [deliveryInfo, setDeliveryInfo] = useState(null);
  const [loading, setLoading] = useState(false);
  const [calculatingDelivery, setCalculatingDelivery] = useState(false);
  const [error, setError] = useState(null);
  const [paymentProviders, setPaymentProviders] = useState([]);

  const lang = user?.language || 'uz';
  const t = (ru, uz) => (lang === 'uz' ? uz : ru);
  const city = getUserCity() || 'Toshkent';

  // Convert cart object to items array
  const cartItems = useMemo(() => {
    return Object.values(cart).map(item => ({
      offer_id: item.offer.id,
      title: item.offer.title,
      price: item.offer.discount_price,
      quantity: item.quantity,
      store_id: item.offer.store_id,
      store_name: item.offer.store_name,
      store_address: item.offer.store_address,
      photo: item.offer.photo,
      unit: item.offer.unit,
    }));
  }, [cart]);

  const cartCount = useMemo(() => {
    return Object.values(cart).reduce((sum, item) => sum + item.quantity, 0);
  }, [cart]);

  useEffect(() => {
    if (Object.keys(cart).length === 0) {
      navigate('/cart');
      return;
    }
    // Load available payment providers
    loadPaymentProviders();
  }, [cart, navigate]);

  const loadPaymentProviders = async () => {
    try {
      const providers = await api.getPaymentProviders();
      setPaymentProviders(providers);
    } catch (err) {
      console.warn('Failed to load payment providers:', err);
    }
  };

  useEffect(() => {
    if (deliveryType === DELIVERY_TYPE.DELIVERY && address.length > 5) {
      const timer = setTimeout(() => {
        calculateDelivery();
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [address, deliveryType, cartItems]);

  const calculateDelivery = async () => {
    if (!address || address.length < 5 || cartItems.length === 0) return;

    setCalculatingDelivery(true);
    setError(null);

    try {
      const currentUser = getCurrentUser() || user;
      if (!currentUser) {
        throw new Error(t('Пользователь не найден', 'Foydalanuvchi topilmadi'));
      }

      const storeId = cartItems[0]?.store_id || cartItems[0]?.storeId || 1;

      const data = await api.calculateDelivery({
        user_id: currentUser.user_id || currentUser.id,
        city,
        address,
        store_id: storeId,
      });
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

    if (!cartItems.length) {
      setError(t('Корзина пуста', 'Savat bo\'sh'));
      return;
    }

    setLoading(true);
    setError(null);

    // Calculate totals early for payment link
    const itemsTotalCalc = cartItems.reduce((sum, item) => sum + (item.price * item.quantity), 0);
    const deliveryCostCalc = (deliveryType === DELIVERY_TYPE.DELIVERY && deliveryInfo?.delivery_cost)
      ? deliveryInfo.delivery_cost
      : 0;
    const totalCalc = itemsTotalCalc + deliveryCostCalc;

    try {
      const currentUser = getCurrentUser() || user;
      if (!currentUser) {
        throw new Error(t('Пользователь не найден', 'Foydalanuvchi topilmadi'));
      }

      const orderPayload = {
        user_id: currentUser.user_id || currentUser.id,
        items: cartItems.map(item => ({
          offer_id: item.offer_id || item.id,
          quantity: item.quantity,
        })),
        delivery_type: deliveryType,
        delivery_address: deliveryType === DELIVERY_TYPE.DELIVERY ? address : null,
        pickup_address: deliveryType === DELIVERY_TYPE.PICKUP
          ? (cartItems[0]?.store_address || cartItems[0]?.storeAddress || null)
          : null,
        payment_method: paymentMethod,
      };

      const orderResult = await api.createOrder(orderPayload);

      // Clear cart
      setCart({});
      localStorage.setItem('fudly_cart_v2', JSON.stringify({}));

      // Handle online payment if selected
      if (paymentMethod === PAYMENT_METHOD.CLICK || paymentMethod === PAYMENT_METHOD.PAYME) {
        // Check if provider is available
        const isProviderAvailable = paymentProviders.includes(paymentMethod);
        
        if (!isProviderAvailable) {
          // Payment provider not integrated - show error
          if (window.Telegram?.WebApp) {
            window.Telegram.WebApp.showAlert(
              t('Этот способ оплаты временно недоступен. Выберите другой способ оплаты.',
                'Bu to\'lov usuli vaqtincha mavjud emas. Boshqa to\'lov usulini tanlang.'),
              () => navigate('/cart')
            );
          } else {
            alert(t('Этот способ оплаты временно недоступен', 'Bu to\'lov usuli vaqtincha mavjud emas'));
            navigate('/cart');
          }
          return;
        }
        
        try {
          const returnUrl = window.location.origin + '/profile';
          // Get store_id from cart items (assuming single store checkout)
          const storeId = cartItems[0]?.store_id || null;

          const paymentData = await api.createPaymentLink(
            orderResult.booking_id || orderResult.id,
            paymentMethod,
            returnUrl,
            storeId,
            totalCalc,
            currentUser.user_id || currentUser.id
          );

          if (paymentData.payment_url) {
            // Redirect to payment page
            if (window.Telegram?.WebApp) {
              window.Telegram.WebApp.openLink(paymentData.payment_url);
            } else {
              window.location.href = paymentData.payment_url;
            }
            return;
          }
        } catch (payErr) {
          console.error('Payment link creation failed:', payErr);
          // Order is created, but payment link failed - show message and continue
          if (window.Telegram?.WebApp) {
            window.Telegram.WebApp.showAlert(
              t('Заказ создан, но ошибка создания ссылки на оплату. Оплатите позже в профиле.',
                'Buyurtma yaratildi, lekin to\'lov havolasida xato. Keyinroq profildan to\'lang.'),
              () => navigate('/profile')
            );
          }
          return;
        }
      }

      // Show success message for cash/card transfer
      if (window.Telegram?.WebApp) {
        window.Telegram.WebApp.showAlert(
          t('Заказ успешно оформлен!', 'Buyurtma muvaffaqiyatli qabul qilindi!'),
          () => navigate('/profile')
        );
      } else {
        alert(t('Заказ успешно оформлен!', 'Buyurtma muvaffaqiyatli qabul qilindi!'));
        navigate('/profile');
      }
    } catch (err) {
      console.error('Error placing order:', err);
      setError(err.message || t('Ошибка при оформлении заказа', 'Buyurtma qabul qilishda xato'));
      setLoading(false);
    }
  };

  // Calculate totals from cartItems (already computed from cart)
  const itemsTotal = cartItems.reduce((sum, item) => sum + (item.price * item.quantity), 0);
  const deliveryCost = (deliveryType === DELIVERY_TYPE.DELIVERY && deliveryInfo?.delivery_cost)
    ? deliveryInfo.delivery_cost
    : 0;
  const total = itemsTotal + deliveryCost;

  return (
    <div className="checkout-page">
      <div className="checkout-header">
        <button onClick={() => navigate('/cart')} className="back-button">
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
            {cartSummaryLoading && (
              <div className="summary-item">
                <div className="item-info">
                  <p className="item-title">{t('Загрузка...', 'Yuklanmoqda...')}</p>
                </div>
              </div>
            )}
            {!cartSummaryLoading && cartItems.map((item, index) => (
              <div key={index} className="summary-item">
                <div className="item-info">
                  <p className="item-title">{item.title}</p>
                  <p className="item-quantity">{item.quantity} {getUnitLabel(item.unit)}</p>
                </div>
                <p className="item-price">{Math.round(item.price * item.quantity).toLocaleString()}</p>
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

        {/* Payment Method Selection */}
        <div className="payment-method-section">
          <h2>{t('Способ оплаты', 'To\'lov usuli')}</h2>
          <div className="payment-options">
            <button
              className={`payment-option ${paymentMethod === PAYMENT_METHOD.CASH ? 'active' : ''}`}
              onClick={() => setPaymentMethod(PAYMENT_METHOD.CASH)}
            >
              <span className="option-icon">💵</span>
              <div className="option-content">
                <h3>{t('Наличные', 'Naqd pul')}</h3>
                <p>{t('Оплата при получении', 'Olishda to\'lash')}</p>
              </div>
              {paymentMethod === PAYMENT_METHOD.CASH && <span className="check-mark">✓</span>}
            </button>

            <button
              className={`payment-option ${paymentMethod === PAYMENT_METHOD.CARD_TRANSFER ? 'active' : ''}`}
              onClick={() => setPaymentMethod(PAYMENT_METHOD.CARD_TRANSFER)}
            >
              <span className="option-icon">💳</span>
              <div className="option-content">
                <h3>{t('Перевод на карту', 'Kartaga o\'tkazish')}</h3>
                <p>{t('Отправьте скриншот оплаты', 'To\'lov skrinshotini yuboring')}</p>
              </div>
              {paymentMethod === PAYMENT_METHOD.CARD_TRANSFER && <span className="check-mark">✓</span>}
            </button>

            {paymentProviders.includes('click') && (
              <button
                className={`payment-option payment-online ${paymentMethod === PAYMENT_METHOD.CLICK ? 'active' : ''}`}
                onClick={() => setPaymentMethod(PAYMENT_METHOD.CLICK)}
              >
                <span className="option-icon">
                  <img src="https://click.uz/favicon.ico" alt="Click" className="payment-logo" onError={(e) => e.target.style.display = 'none'} />
                </span>
                <div className="option-content">
                  <h3>Click</h3>
                  <p>{t('Онлайн оплата через Click', 'Click orqali onlayn to\'lov')}</p>
                </div>
                {paymentMethod === PAYMENT_METHOD.CLICK && <span className="check-mark">✓</span>}
              </button>
            )}

            {paymentProviders.includes('payme') && (
              <button
                className={`payment-option payment-online ${paymentMethod === PAYMENT_METHOD.PAYME ? 'active' : ''}`}
                onClick={() => setPaymentMethod(PAYMENT_METHOD.PAYME)}
              >
                <span className="option-icon">
                  <img src="https://payme.uz/favicon.ico" alt="Payme" className="payment-logo" onError={(e) => e.target.style.display = 'none'} />
                </span>
                <div className="option-content">
                  <h3>Payme</h3>
                  <p>{t('Онлайн оплата через Payme', 'Payme orqali onlayn to\'lov')}</p>
                </div>
                {paymentMethod === PAYMENT_METHOD.PAYME && <span className="check-mark">✓</span>}
              </button>
            )}
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

      <BottomNav currentPage="cart" cartCount={cartCount} />
    </div>
  );
}

export default CheckoutPage;

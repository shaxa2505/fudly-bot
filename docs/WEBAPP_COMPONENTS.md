# Дополнительные компоненты для мини-приложения

## 🛒 Страница корзины

### CartPage.tsx

```typescript
import React, { useState, useEffect } from 'react';
import { api } from '../api/client';
import './CartPage.css';

interface CartItem {
  offer_id: number;
  quantity: number;
  title: string;
  price: number;
  photo?: string;
}

interface CartData {
  items: CartItem[];
  total: number;
  items_count: number;
}

export const CartPage: React.FC = () => {
  const [cart, setCart] = useState<Map<number, number>>(new Map());
  const [cartData, setCartData] = useState<CartData | null>(null);
  const [loading, setLoading] = useState(false);
  const [orderPlaced, setOrderPlaced] = useState(false);

  // Load cart from localStorage
  useEffect(() => {
    const savedCart = localStorage.getItem('fudly_cart');
    if (savedCart) {
      try {
        const parsed = JSON.parse(savedCart);
        setCart(new Map(Object.entries(parsed)));
      } catch (e) {
        console.error('Error loading cart:', e);
      }
    }
  }, []);

  // Calculate cart whenever it changes
  useEffect(() => {
    if (cart.size === 0) {
      setCartData(null);
      return;
    }

    const loadCartData = async () => {
      try {
        const items = Array.from(cart.entries());
        const offerIds = items.map(([id, qty]) => `${id}:${qty}`).join(',');

        const data = await api.calculateCart(items.map(([id, qty]) => ({
          offerId: id,
          quantity: qty,
        })));

        setCartData(data);
      } catch (error) {
        console.error('Error calculating cart:', error);
      }
    };

    loadCartData();
  }, [cart]);

  // Save cart to localStorage
  useEffect(() => {
    if (cart.size > 0) {
      const obj = Object.fromEntries(cart);
      localStorage.setItem('fudly_cart', JSON.stringify(obj));
    } else {
      localStorage.removeItem('fudly_cart');
    }
  }, [cart]);

  const updateQuantity = (offerId: number, delta: number) => {
    setCart(prev => {
      const next = new Map(prev);
      const current = next.get(offerId) || 0;
      const newQty = current + delta;

      if (newQty <= 0) {
        next.delete(offerId);
      } else {
        next.set(offerId, newQty);
      }

      return next;
    });
  };

  const removeItem = (offerId: number) => {
    setCart(prev => {
      const next = new Map(prev);
      next.delete(offerId);
      return next;
    });
  };

  const clearCart = () => {
    if (confirm('Очистить всю корзину?')) {
      setCart(new Map());
      setCartData(null);
    }
  };

  const placeOrder = async () => {
    if (!cartData || cartData.items.length === 0) return;

    setLoading(true);
    try {
      const userId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id || 0;

      const orderData = {
        items: cartData.items.map(item => ({
          offer_id: item.offer_id,
          quantity: item.quantity,
        })),
        user_id: userId,
        delivery_address: null,
        phone: null,
        comment: null,
      };

      const result = await api.createOrder(orderData);

      setOrderPlaced(true);
      setCart(new Map());
      setCartData(null);

      // Show success message via Telegram
      window.Telegram?.WebApp?.showAlert(
        `Заказ #${result.order_id} оформлен!
Сумма: ${result.total.toLocaleString()} сум
Товаров: ${result.items_count} шт.`
      );

      // Close mini app after 2 seconds
      setTimeout(() => {
        window.Telegram?.WebApp?.close();
      }, 2000);

    } catch (error) {
      console.error('Error placing order:', error);
      window.Telegram?.WebApp?.showAlert('Ошибка при оформлении заказа');
    } finally {
      setLoading(false);
    }
  };

  if (orderPlaced) {
    return (
      <div className="cart-page empty">
        <div className="success-message">
          <div className="icon">✅</div>
          <h2>Заказ оформлен!</h2>
          <p>Мы свяжемся с вами в ближайшее время</p>
        </div>
      </div>
    );
  }

  if (!cartData || cartData.items.length === 0) {
    return (
      <div className="cart-page empty">
        <div className="empty-cart">
          <div className="icon">🛒</div>
          <h2>Корзина пуста</h2>
          <p>Добавьте товары из каталога</p>
          <button onClick={() => window.history.back()}>
            Вернуться к каталогу
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="cart-page">
      <header className="cart-header">
        <button className="back-btn" onClick={() => window.history.back()}>
          ← Назад
        </button>
        <h1>Корзина ({cartData.items_count})</h1>
        <button className="clear-btn" onClick={clearCart}>
          Очистить
        </button>
      </header>

      <div className="cart-items">
        {cartData.items.map(item => (
          <div key={item.offer_id} className="cart-item">
            <div className="item-image">
              <img
                src={item.photo || '/placeholder.png'}
                alt={item.title}
              />
            </div>

            <div className="item-info">
              <h3>{item.title}</h3>
              <p className="item-price">
                {item.price.toLocaleString()} сум
              </p>
            </div>

            <div className="item-controls">
              <button
                className="qty-btn"
                onClick={() => updateQuantity(item.offer_id, -1)}
              >
                −
              </button>
              <span className="qty">{item.quantity}</span>
              <button
                className="qty-btn"
                onClick={() => updateQuantity(item.offer_id, 1)}
              >
                +
              </button>
            </div>

            <button
              className="remove-btn"
              onClick={() => removeItem(item.offer_id)}
            >
              🗑️
            </button>
          </div>
        ))}
      </div>

      <div className="cart-footer">
        <div className="total-section">
          <div className="total-row">
            <span>Товары ({cartData.items_count} шт.)</span>
            <span>{cartData.total.toLocaleString()} сум</span>
          </div>
          <div className="total-row">
            <span>Доставка</span>
            <span className="free">Бесплатно</span>
          </div>
          <div className="total-row final">
            <span>Итого</span>
            <span>{cartData.total.toLocaleString()} сум</span>
          </div>
        </div>

        <button
          className="checkout-btn"
          onClick={placeOrder}
          disabled={loading}
        >
          {loading ? 'Оформление...' : 'Оформить заказ'}
        </button>
      </div>
    </div>
  );
};
```

### CartPage.css

```css
.cart-page {
  min-height: 100vh;
  background: #f5f5f5;
  display: flex;
  flex-direction: column;
}

.cart-page.empty {
  justify-content: center;
  align-items: center;
}

.cart-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px;
  background: var(--tg-theme-bg-color, #fff);
  border-bottom: 1px solid #e0e0e0;
  position: sticky;
  top: 0;
  z-index: 10;
}

.cart-header h1 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.back-btn,
.clear-btn {
  padding: 8px 12px;
  border: none;
  background: none;
  color: var(--tg-theme-button-color, #3390ec);
  font-size: 14px;
  cursor: pointer;
}

/* Empty cart */
.empty-cart,
.success-message {
  text-align: center;
  padding: 40px 20px;
}

.empty-cart .icon,
.success-message .icon {
  font-size: 64px;
  margin-bottom: 16px;
}

.empty-cart h2,
.success-message h2 {
  font-size: 24px;
  margin: 0 0 8px 0;
}

.empty-cart p,
.success-message p {
  color: #888;
  margin: 0 0 24px 0;
}

.empty-cart button {
  padding: 12px 24px;
  border: none;
  border-radius: 8px;
  background: var(--tg-theme-button-color, #3390ec);
  color: #fff;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
}

/* Cart items */
.cart-items {
  flex: 1;
  padding: 16px;
  overflow-y: auto;
}

.cart-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: #fff;
  border-radius: 12px;
  margin-bottom: 12px;
}

.item-image {
  width: 60px;
  height: 60px;
  border-radius: 8px;
  overflow: hidden;
  background: #f0f0f0;
  flex-shrink: 0;
}

.item-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.item-info {
  flex: 1;
}

.item-info h3 {
  margin: 0 0 4px 0;
  font-size: 14px;
  font-weight: 600;
}

.item-price {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  color: var(--tg-theme-button-color, #3390ec);
}

.item-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  background: #f5f5f5;
  border-radius: 8px;
}

.qty-btn {
  width: 28px;
  height: 28px;
  border: none;
  background: #fff;
  border-radius: 6px;
  font-size: 18px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.qty {
  min-width: 24px;
  text-align: center;
  font-weight: 600;
}

.remove-btn {
  width: 36px;
  height: 36px;
  border: none;
  background: #fee;
  border-radius: 8px;
  font-size: 18px;
  cursor: pointer;
}

/* Footer */
.cart-footer {
  padding: 16px;
  background: #fff;
  border-top: 1px solid #e0e0e0;
}

.total-section {
  margin-bottom: 16px;
}

.total-row {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 14px;
}

.total-row.final {
  font-size: 18px;
  font-weight: 700;
  padding-top: 8px;
  border-top: 1px solid #e0e0e0;
}

.total-row .free {
  color: #4caf50;
}

.checkout-btn {
  width: 100%;
  padding: 16px;
  border: none;
  border-radius: 12px;
  background: var(--tg-theme-button-color, #3390ec);
  color: #fff;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s;
}

.checkout-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.checkout-btn:active:not(:disabled) {
  opacity: 0.8;
}
```

---

## ❤️ Страница избранного

### FavoritesPage.tsx

```typescript
import React, { useState, useEffect } from 'react';
import { api } from '../api/client';
import { OfferCard } from '../components/OfferCard';
import './FavoritesPage.css';

interface Offer {
  id: number;
  title: string;
  discount_price: number;
  original_price: number;
  discount_percent: number;
  store_name: string;
  photo?: string;
}

export const FavoritesPage: React.FC = () => {
  const [favorites, setFavorites] = useState<Offer[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadFavorites();
  }, []);

  const loadFavorites = async () => {
    setLoading(true);
    try {
      const data = await api.getFavorites();
      setFavorites(data);
    } catch (error) {
      console.error('Error loading favorites:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleRemoveFavorite = async (offerId: number) => {
    try {
      await api.removeFavorite(offerId);
      setFavorites(prev => prev.filter(o => o.id !== offerId));
    } catch (error) {
      console.error('Error removing favorite:', error);
    }
  };

  if (loading) {
    return (
      <div className="favorites-page">
        <header>
          <button onClick={() => window.history.back()}>← Назад</button>
          <h1>Избранное</h1>
        </header>
        <div className="loading">Загрузка...</div>
      </div>
    );
  }

  if (favorites.length === 0) {
    return (
      <div className="favorites-page empty">
        <div className="empty-state">
          <div className="icon">❤️</div>
          <h2>Нет избранных товаров</h2>
          <p>Добавьте товары в избранное, чтобы быстро находить их</p>
          <button onClick={() => window.history.back()}>
            Перейти к каталогу
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="favorites-page">
      <header>
        <button onClick={() => window.history.back()}>← Назад</button>
        <h1>Избранное ({favorites.length})</h1>
      </header>

      <div className="favorites-grid">
        {favorites.map(offer => (
          <OfferCard
            key={offer.id}
            offer={offer}
            isFavorite={true}
            onToggleFavorite={() => handleRemoveFavorite(offer.id)}
          />
        ))}
      </div>
    </div>
  );
};
```

### FavoritesPage.css

```css
.favorites-page {
  min-height: 100vh;
  background: #f5f5f5;
}

.favorites-page.empty {
  display: flex;
  align-items: center;
  justify-content: center;
}

.favorites-page header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px;
  background: var(--tg-theme-bg-color, #fff);
  border-bottom: 1px solid #e0e0e0;
  position: sticky;
  top: 0;
  z-index: 10;
}

.favorites-page header button {
  padding: 8px;
  border: none;
  background: none;
  color: var(--tg-theme-button-color, #3390ec);
  font-size: 16px;
  cursor: pointer;
}

.favorites-page header h1 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.empty-state {
  text-align: center;
  padding: 40px 20px;
}

.empty-state .icon {
  font-size: 64px;
  margin-bottom: 16px;
}

.empty-state h2 {
  font-size: 24px;
  margin: 0 0 8px 0;
}

.empty-state p {
  color: #888;
  margin: 0 0 24px 0;
}

.empty-state button {
  padding: 12px 24px;
  border: none;
  border-radius: 8px;
  background: var(--tg-theme-button-color, #3390ec);
  color: #fff;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
}

.favorites-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 12px;
  padding: 16px;
}

.loading {
  text-align: center;
  padding: 40px;
  color: #888;
}
```

---

## 🔧 Обновленный API клиент

### api/client.ts (расширенная версия)

```typescript
import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_URL || 'https://your-bot-api.railway.app/api/v1';

// Create axios instance with interceptors
const client = axios.create({
  baseURL: API_BASE,
  timeout: 10000,
});

// Add auth header to all requests
client.interceptors.request.use((config) => {
  const initData = window.Telegram?.WebApp?.initData;
  if (initData) {
    config.headers['X-Telegram-Init-Data'] = initData;
  }
  return config;
});

// Handle errors
client.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Error:', error);

    if (error.response?.status === 401) {
      window.Telegram?.WebApp?.showAlert('Требуется авторизация');
    } else if (error.response?.status >= 500) {
      window.Telegram?.WebApp?.showAlert('Ошибка сервера. Попробуйте позже.');
    }

    return Promise.reject(error);
  }
);

export const api = {
  // Categories
  async getCategories() {
    const { data } = await client.get('/categories');
    return data;
  },

  // Offers
  async getOffers(params: {
    category?: string;
    search?: string;
    min_price?: number;
    max_price?: number;
    min_discount?: number;
    sort_by?: string;
    limit?: number;
    offset?: number;
  }) {
    const { data } = await client.get('/offers', { params });
    return data;
  },

  async getOffer(offerId: number) {
    const { data } = await client.get(`/offers/${offerId}`);
    return data;
  },

  // Favorites
  async getFavorites() {
    const { data } = await client.get('/favorites');
    return data;
  },

  async addFavorite(offerId: number) {
    const { data } = await client.post('/favorites/add', { offer_id: offerId });
    return data;
  },

  async removeFavorite(offerId: number) {
    const { data } = await client.post('/favorites/remove', { offer_id: offerId });
    return data;
  },

  // Cart
  async calculateCart(items: Array<{ offerId: number; quantity: number }>) {
    const offerIds = items.map(i => `${i.offerId}:${i.quantity}`).join(',');
    const { data } = await client.get('/cart/calculate', {
      params: { offer_ids: offerIds },
    });
    return data;
  },

  // Orders
  async createOrder(orderData: any) {
    const { data } = await client.post('/orders', orderData);
    return data;
  },

  // Stores
  async getStores(params?: { city?: string; business_type?: string }) {
    const { data } = await client.get('/stores', { params });
    return data;
  },

  async getNearbyStores(latitude: number, longitude: number, radiusKm = 5) {
    const { data } = await client.post('/stores/nearby', {
      latitude,
      longitude,
    }, {
      params: { radius_km: radiusKm },
    });
    return data;
  },

  // Search
  async getSearchSuggestions(query: string, limit = 5) {
    const { data } = await client.get('/search/suggestions', {
      params: { query, limit },
    });
    return data;
  },

  // Stats
  async getHotDealsStats(city = 'Ташкент') {
    const { data } = await client.get('/stats/hot-deals', {
      params: { city },
    });
    return data;
  },
};
```

---

## 🎨 Компонент карточки товара

### components/OfferCard.tsx

```typescript
import React from 'react';
import './OfferCard.css';

interface Offer {
  id: number;
  title: string;
  discount_price: number;
  original_price: number;
  discount_percent: number;
  store_name: string;
  photo?: string;
}

interface Props {
  offer: Offer;
  isFavorite: boolean;
  onToggleFavorite: () => void;
  onAddToCart?: () => void;
}

export const OfferCard: React.FC<Props> = ({
  offer,
  isFavorite,
  onToggleFavorite,
  onAddToCart,
}) => {
  return (
    <div className="offer-card" onClick={() => {
      // Navigate to detail page
      window.location.href = `/offer/${offer.id}`;
    }}>
      <div className="card-image">
        <img
          src={offer.photo || '/placeholder.png'}
          alt={offer.title}
          loading="lazy"
        />
        <div className="discount-badge">
          -{offer.discount_percent}%
        </div>
        <button
          className="favorite-btn"
          onClick={(e) => {
            e.stopPropagation();
            onToggleFavorite();
          }}
        >
          {isFavorite ? '❤️' : '🤍'}
        </button>
      </div>

      <div className="card-content">
        <h3>{offer.title}</h3>
        <p className="store-name">{offer.store_name}</p>

        <div className="price-row">
          <span className="discount-price">
            {offer.discount_price.toLocaleString()} сум
          </span>
          <span className="original-price">
            {offer.original_price.toLocaleString()} сум
          </span>
        </div>

        {onAddToCart && (
          <button
            className="add-to-cart-btn"
            onClick={(e) => {
              e.stopPropagation();
              onAddToCart();
            }}
          >
            В корзину
          </button>
        )}
      </div>
    </div>
  );
};
```

---

## 📱 Telegram WebApp инициализация

### App.tsx (главный компонент)

```typescript
import React, { useEffect } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { HomePage } from './pages/HomePage';
import { FavoritesPage } from './pages/FavoritesPage';
import { CartPage } from './pages/CartPage';
import './App.css';

function App() {
  useEffect(() => {
    // Initialize Telegram WebApp
    const tg = window.Telegram?.WebApp;

    if (tg) {
      tg.ready();
      tg.expand();

      // Set theme
      document.documentElement.style.setProperty(
        '--tg-theme-bg-color',
        tg.themeParams.bg_color || '#ffffff'
      );
      document.documentElement.style.setProperty(
        '--tg-theme-button-color',
        tg.themeParams.button_color || '#3390ec'
      );
      document.documentElement.style.setProperty(
        '--tg-theme-text-color',
        tg.themeParams.text_color || '#000000'
      );
    }
  }, []);

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/favorites" element={<FavoritesPage />} />
        <Route path="/cart" element={<CartPage />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
```

---

Готово! Все компоненты созданы. 🎉

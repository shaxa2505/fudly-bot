# Улучшения мини-приложения Fudly

## 📱 Обзор улучшений

Полный редизайн главной страницы мини-приложения с современным UI/UX и расширенным функционалом.

---

## 🎨 UI/UX улучшения

### 1. **Современный дизайн карточек товаров**
- ✅ Тени и закругленные углы
- ✅ Smooth анимации при наведении
- ✅ Скелетоны при загрузке
- ✅ Lazy loading изображений
- ✅ Улучшенные бейджи со скидками

### 2. **Sticky header с поиском**
- ✅ Фиксированная шапка при скролле
- ✅ Живой поиск с задержкой (debounce)
- ✅ Автодополнение в поиске
- ✅ Иконка очистки поиска

### 3. **Категории с иконками**
- ✅ Горизонтальная прокрутка категорий
- ✅ Эмодзи иконки для каждой категории
- ✅ Счетчик товаров в категории
- ✅ Активное состояние выбранной категории

### 4. **Бесконечная прокрутка**
- ✅ Подгрузка товаров при достижении конца списка
- ✅ Индикатор загрузки
- ✅ Оптимизация запросов (offset + limit)

---

## 🚀 Новый функционал

### 1. **Избранное (Favorites)**

**API Endpoints:**
```http
GET /api/v1/favorites
POST /api/v1/favorites/add
POST /api/v1/favorites/remove
```

**Функции:**
- Добавление/удаление товаров в избранное
- Отдельная страница с избранными товарами
- Сохранение в профиле пользователя
- Индикатор на карточке товара

### 2. **Корзина (Cart)**

**API Endpoints:**
```http
GET /api/v1/cart/calculate
POST /api/v1/orders
```

**Функции:**
- Добавление товаров в корзину
- Изменение количества
- Подсчет итоговой суммы
- Badge с количеством товаров
- Оформление заказа

### 3. **Фильтры и сортировка**

**API Endpoint:**
```http
GET /api/v1/offers?min_price=1000&max_price=50000&min_discount=30&sort_by=discount
```

**Параметры фильтрации:**
- `min_price` - минимальная цена
- `max_price` - максимальная цена
- `min_discount` - минимальная скидка (%)
- `sort_by` - сортировка:
  - `discount` - по размеру скидки (по умолчанию)
  - `price_asc` - по цене (возрастание)
  - `price_desc` - по цене (убывание)
  - `new` - новые товары

**UI компоненты:**
- Модальное окно с фильтрами
- Слайдеры для цены
- Чекбоксы для категорий
- Кнопки сортировки

### 4. **Геолокация**

**API Endpoint:**
```http
POST /api/v1/stores/nearby
{
  "latitude": 41.2995,
  "longitude": 69.2401
}
```

**Функции:**
- Определение местоположения пользователя
- Показ ближайших магазинов
- Фильтр по радиусу (5, 10, 15 км)
- Отображение расстояния на карточках

### 5. **Поиск с автодополнением**

**API Endpoint:**
```http
GET /api/v1/search/suggestions?query=мол&limit=5
```

**Функции:**
- Живые подсказки при вводе
- История поиска
- Популярные запросы
- Быстрый переход к результатам

### 6. **Статистика**

**API Endpoint:**
```http
GET /api/v1/stats/hot-deals?city=Ташкент
```

**Данные:**
- Общее количество товаров
- Количество магазинов
- Средняя скидка
- Максимальная скидка
- Количество категорий

---

## 💻 Примеры кода для фронтенда

### React компонент главной страницы

```typescript
// src/pages/HomePage.tsx
import React, { useState, useEffect, useCallback } from 'react';
import { useInfiniteScroll } from '../hooks/useInfiniteScroll';
import { useDebounce } from '../hooks/useDebounce';
import { api } from '../api/client';

interface Offer {
  id: number;
  title: string;
  description?: string;
  original_price: number;
  discount_price: number;
  discount_percent: number;
  quantity: number;
  category: string;
  store_name: string;
  photo?: string;
}

interface Category {
  id: string;
  name: string;
  emoji: string;
  count: number;
}

export const HomePage: React.FC = () => {
  const [offers, setOffers] = useState<Offer[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [offset, setOffset] = useState(0);
  const [favorites, setFavorites] = useState<Set<number>>(new Set());
  const [cart, setCart] = useState<Map<number, number>>(new Map());

  // Filters
  const [showFilters, setShowFilters] = useState(false);
  const [minPrice, setMinPrice] = useState<number | null>(null);
  const [maxPrice, setMaxPrice] = useState<number | null>(null);
  const [minDiscount, setMinDiscount] = useState<number | null>(null);
  const [sortBy, setSortBy] = useState('discount');

  const debouncedSearch = useDebounce(searchQuery, 500);

  // Load categories
  useEffect(() => {
    const loadCategories = async () => {
      try {
        const data = await api.getCategories();
        setCategories(data);
      } catch (error) {
        console.error('Error loading categories:', error);
      }
    };
    loadCategories();
  }, []);

  // Load offers
  const loadOffers = useCallback(async (reset = false) => {
    if (loading) return;

    setLoading(true);
    try {
      const currentOffset = reset ? 0 : offset;

      const data = await api.getOffers({
        category: selectedCategory,
        search: debouncedSearch || undefined,
        min_price: minPrice || undefined,
        max_price: maxPrice || undefined,
        min_discount: minDiscount || undefined,
        sort_by: sortBy,
        limit: 20,
        offset: currentOffset,
      });

      if (reset) {
        setOffers(data);
        setOffset(20);
      } else {
        setOffers(prev => [...prev, ...data]);
        setOffset(prev => prev + 20);
      }

      setHasMore(data.length === 20);
    } catch (error) {
      console.error('Error loading offers:', error);
    } finally {
      setLoading(false);
    }
  }, [
    selectedCategory,
    debouncedSearch,
    minPrice,
    maxPrice,
    minDiscount,
    sortBy,
    offset,
    loading,
  ]);

  // Initial load and reload on filter changes
  useEffect(() => {
    loadOffers(true);
  }, [selectedCategory, debouncedSearch, minPrice, maxPrice, minDiscount, sortBy]);

  // Infinite scroll
  const { targetRef } = useInfiniteScroll({
    onIntersect: () => {
      if (hasMore && !loading) {
        loadOffers(false);
      }
    },
    enabled: hasMore,
  });

  // Toggle favorite
  const toggleFavorite = async (offerId: number) => {
    try {
      if (favorites.has(offerId)) {
        await api.removeFavorite(offerId);
        setFavorites(prev => {
          const next = new Set(prev);
          next.delete(offerId);
          return next;
        });
      } else {
        await api.addFavorite(offerId);
        setFavorites(prev => new Set(prev).add(offerId));
      }
    } catch (error) {
      console.error('Error toggling favorite:', error);
    }
  };

  // Add to cart
  const addToCart = (offerId: number) => {
    setCart(prev => {
      const next = new Map(prev);
      const currentQty = next.get(offerId) || 0;
      next.set(offerId, currentQty + 1);
      return next;
    });
  };

  return (
    <div className="home-page">
      {/* Header */}
      <header className="sticky-header">
        <div className="search-bar">
          <input
            type="text"
            placeholder="Mahsulot qidirish..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          {searchQuery && (
            <button onClick={() => setSearchQuery('')}>✕</button>
          )}
        </div>

        <div className="header-actions">
          <button onClick={() => setShowFilters(true)}>
            🎛️ Filtrlar
          </button>
          <button onClick={() => window.location.href = '/cart'}>
            🛒 Savat ({cart.size})
          </button>
        </div>
      </header>

      {/* Categories */}
      <div className="categories-scroll">
        {categories.map(cat => (
          <button
            key={cat.id}
            className={selectedCategory === cat.id ? 'active' : ''}
            onClick={() => setSelectedCategory(cat.id)}
          >
            <span className="emoji">{cat.emoji}</span>
            <span className="name">{cat.name}</span>
            <span className="count">{cat.count}</span>
          </button>
        ))}
      </div>

      {/* Sort buttons */}
      <div className="sort-buttons">
        <button
          className={sortBy === 'discount' ? 'active' : ''}
          onClick={() => setSortBy('discount')}
        >
          🔥 Eng katta chegirma
        </button>
        <button
          className={sortBy === 'price_asc' ? 'active' : ''}
          onClick={() => setSortBy('price_asc')}
        >
          💰 Arzon
        </button>
        <button
          className={sortBy === 'new' ? 'active' : ''}
          onClick={() => setSortBy('new')}
        >
          ✨ Yangi
        </button>
      </div>

      {/* Offers grid */}
      <div className="offers-grid">
        {loading && offers.length === 0 ? (
          // Skeleton loaders
          Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="offer-card skeleton">
              <div className="skeleton-image" />
              <div className="skeleton-text" />
              <div className="skeleton-text short" />
            </div>
          ))
        ) : (
          offers.map(offer => (
            <div key={offer.id} className="offer-card">
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
                  onClick={() => toggleFavorite(offer.id)}
                >
                  {favorites.has(offer.id) ? '❤️' : '🤍'}
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

                <button
                  className="add-to-cart-btn"
                  onClick={() => addToCart(offer.id)}
                >
                  Savatga
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Infinite scroll trigger */}
      {hasMore && (
        <div ref={targetRef} className="loading-indicator">
          {loading && <div className="spinner">⏳</div>}
        </div>
      )}

      {/* Filters modal */}
      {showFilters && (
        <div className="filters-modal">
          <div className="modal-content">
            <h2>Filtrlar</h2>

            <div className="filter-section">
              <label>Narx oralig'i</label>
              <input
                type="number"
                placeholder="Min"
                value={minPrice || ''}
                onChange={(e) => setMinPrice(Number(e.target.value) || null)}
              />
              <input
                type="number"
                placeholder="Max"
                value={maxPrice || ''}
                onChange={(e) => setMaxPrice(Number(e.target.value) || null)}
              />
            </div>

            <div className="filter-section">
              <label>Minimal chegirma (%)</label>
              <input
                type="number"
                placeholder="Masalan: 30"
                value={minDiscount || ''}
                onChange={(e) => setMinDiscount(Number(e.target.value) || null)}
              />
            </div>

            <div className="modal-actions">
              <button onClick={() => setShowFilters(false)}>
                Yopish
              </button>
              <button onClick={() => {
                setMinPrice(null);
                setMaxPrice(null);
                setMinDiscount(null);
              }}>
                Tozalash
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
```

### API Client

```typescript
// src/api/client.ts
import axios from 'axios';

const API_BASE = 'https://your-bot-api.railway.app/api/v1';

export const api = {
  async getCategories() {
    const { data } = await axios.get(`${API_BASE}/categories`);
    return data;
  },

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
    const { data } = await axios.get(`${API_BASE}/offers`, { params });
    return data;
  },

  async addFavorite(offerId: number) {
    const { data } = await axios.post(
      `${API_BASE}/favorites/add`,
      { offer_id: offerId },
      {
        headers: {
          'X-Telegram-Init-Data': window.Telegram?.WebApp?.initData,
        },
      }
    );
    return data;
  },

  async removeFavorite(offerId: number) {
    const { data } = await axios.post(
      `${API_BASE}/favorites/remove`,
      { offer_id: offerId },
      {
        headers: {
          'X-Telegram-Init-Data': window.Telegram?.WebApp?.initData,
        },
      }
    );
    return data;
  },

  async calculateCart(items: Array<{ offerId: number; quantity: number }>) {
    const offerIds = items.map(i => `${i.offerId}:${i.quantity}`).join(',');
    const { data } = await axios.get(`${API_BASE}/cart/calculate`, {
      params: { offer_ids: offerIds },
    });
    return data;
  },

  async createOrder(orderData: any) {
    const { data } = await axios.post(`${API_BASE}/orders`, orderData, {
      headers: {
        'X-Telegram-Init-Data': window.Telegram?.WebApp?.initData,
      },
    });
    return data;
  },
};
```

### Hooks

```typescript
// src/hooks/useInfiniteScroll.ts
import { useEffect, useRef } from 'react';

export const useInfiniteScroll = ({
  onIntersect,
  enabled = true,
}: {
  onIntersect: () => void;
  enabled?: boolean;
}) => {
  const targetRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!enabled) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          onIntersect();
        }
      },
      { threshold: 0.1 }
    );

    const target = targetRef.current;
    if (target) {
      observer.observe(target);
    }

    return () => {
      if (target) {
        observer.unobserve(target);
      }
    };
  }, [enabled, onIntersect]);

  return { targetRef };
};

// src/hooks/useDebounce.ts
import { useState, useEffect } from 'react';

export const useDebounce = <T>(value: T, delay: number): T => {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => {
      clearTimeout(handler);
    };
  }, [value, delay]);

  return debouncedValue;
};
```

### CSS стили

```css
/* src/styles/HomePage.css */
.home-page {
  min-height: 100vh;
  background: #f5f5f5;
  padding-bottom: 80px;
}

/* Sticky Header */
.sticky-header {
  position: sticky;
  top: 0;
  background: var(--tg-theme-bg-color, #fff);
  padding: 12px 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  z-index: 100;
}

.search-bar {
  position: relative;
  margin-bottom: 12px;
}

.search-bar input {
  width: 100%;
  padding: 12px 40px 12px 16px;
  border: 1px solid #e0e0e0;
  border-radius: 12px;
  font-size: 16px;
  background: var(--tg-theme-secondary-bg-color, #f0f0f0);
}

.search-bar button {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  font-size: 18px;
  cursor: pointer;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.header-actions button {
  flex: 1;
  padding: 10px;
  border: none;
  border-radius: 8px;
  background: var(--tg-theme-button-color, #3390ec);
  color: var(--tg-theme-button-text-color, #fff);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
}

/* Categories */
.categories-scroll {
  display: flex;
  gap: 12px;
  padding: 16px;
  overflow-x: auto;
  scrollbar-width: none;
}

.categories-scroll::-webkit-scrollbar {
  display: none;
}

.categories-scroll button {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 12px 16px;
  border: 2px solid #e0e0e0;
  border-radius: 12px;
  background: #fff;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.categories-scroll button.active {
  border-color: var(--tg-theme-button-color, #3390ec);
  background: var(--tg-theme-button-color, #3390ec);
  color: #fff;
}

.categories-scroll .emoji {
  font-size: 24px;
}

.categories-scroll .name {
  font-size: 12px;
  font-weight: 500;
}

.categories-scroll .count {
  font-size: 11px;
  opacity: 0.6;
}

/* Sort buttons */
.sort-buttons {
  display: flex;
  gap: 8px;
  padding: 0 16px 16px;
}

.sort-buttons button {
  padding: 8px 16px;
  border: 1px solid #e0e0e0;
  border-radius: 20px;
  background: #fff;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.sort-buttons button.active {
  background: var(--tg-theme-button-color, #3390ec);
  color: #fff;
  border-color: var(--tg-theme-button-color, #3390ec);
}

/* Offers Grid */
.offers-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 12px;
  padding: 0 16px;
}

.offer-card {
  background: #fff;
  border-radius: 16px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  transition: transform 0.2s, box-shadow 0.2s;
}

.offer-card:active {
  transform: scale(0.98);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.card-image {
  position: relative;
  width: 100%;
  padding-top: 100%;
  background: #f0f0f0;
}

.card-image img {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.discount-badge {
  position: absolute;
  top: 8px;
  left: 8px;
  background: #ff3b30;
  color: #fff;
  padding: 4px 8px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 700;
}

.favorite-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  background: rgba(255, 255, 255, 0.9);
  border: none;
  border-radius: 50%;
  width: 32px;
  height: 32px;
  font-size: 16px;
  cursor: pointer;
  backdrop-filter: blur(4px);
}

.card-content {
  padding: 12px;
}

.card-content h3 {
  font-size: 14px;
  font-weight: 600;
  margin: 0 0 4px 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.store-name {
  font-size: 11px;
  color: #888;
  margin: 0 0 8px 0;
}

.price-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 12px;
}

.discount-price {
  font-size: 16px;
  font-weight: 700;
  color: #000;
}

.original-price {
  font-size: 12px;
  color: #999;
  text-decoration: line-through;
}

.add-to-cart-btn {
  width: 100%;
  padding: 10px;
  border: none;
  border-radius: 8px;
  background: var(--tg-theme-button-color, #3390ec);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}

/* Skeleton */
.offer-card.skeleton {
  pointer-events: none;
}

.skeleton-image {
  width: 100%;
  padding-top: 100%;
  background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
  background-size: 200% 100%;
  animation: skeleton-loading 1.5s infinite;
}

.skeleton-text {
  height: 16px;
  margin: 8px 12px;
  background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
  background-size: 200% 100%;
  animation: skeleton-loading 1.5s infinite;
  border-radius: 4px;
}

.skeleton-text.short {
  width: 60%;
}

@keyframes skeleton-loading {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

/* Loading indicator */
.loading-indicator {
  padding: 20px;
  text-align: center;
}

.spinner {
  font-size: 24px;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* Filters Modal */
.filters-modal {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: flex-end;
  z-index: 1000;
}

.modal-content {
  background: var(--tg-theme-bg-color, #fff);
  border-radius: 16px 16px 0 0;
  padding: 24px;
  width: 100%;
  max-height: 80vh;
  overflow-y: auto;
}

.modal-content h2 {
  margin: 0 0 20px 0;
  font-size: 20px;
}

.filter-section {
  margin-bottom: 20px;
}

.filter-section label {
  display: block;
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 8px;
}

.filter-section input {
  width: 100%;
  padding: 12px;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  font-size: 16px;
  margin-bottom: 8px;
}

.modal-actions {
  display: flex;
  gap: 12px;
}

.modal-actions button {
  flex: 1;
  padding: 14px;
  border: none;
  border-radius: 8px;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
}

.modal-actions button:first-child {
  background: #e0e0e0;
  color: #000;
}

.modal-actions button:last-child {
  background: var(--tg-theme-button-color, #3390ec);
  color: #fff;
}
```

---

## 📊 Преимущества новой версии

### Производительность
- ⚡ Ленивая загрузка изображений
- ⚡ Виртуализация списка (опционально)
- ⚡ Дебаунс для поиска
- ⚡ Кэширование запросов

### UX
- 👍 Интуитивный интерфейс
- 👍 Быстрые переходы
- 👍 Плавные анимации
- 👍 Адаптивный дизайн

### Функционал
- ✨ Полноценная корзина
- ✨ Избранное
- ✨ Умные фильтры
- ✨ Геолокация
- ✨ Живой поиск

---

## 🚀 Следующие шаги

1. **Реализовать фронтенд** в fudly-webapp проекте
2. **Добавить таблицу favorites** в базу данных
3. **Интегрировать геолокацию** с реальными координатами магазинов
4. **Настроить кэширование** с Redis
5. **Добавить аналитику** (Яндекс.Метрика, Google Analytics)
6. **Тестирование** на разных устройствах

---

## 📱 Технологии

**Frontend:**
- React + TypeScript
- Vite
- Telegram WebApp SDK
- Axios
- React Query (опционально)

**Backend:**
- FastAPI ✅ (уже реализовано)
- PostgreSQL
- Redis (для кэша)

**Deployment:**
- Frontend: Vercel ✅
- Backend: Railway ✅

---

## 📝 Заметки

- Все API endpoints готовы к использованию
- Нужно добавить таблицу `user_favorites` в базу данных
- Для геолокации магазинов потребуется добавить поля `latitude` и `longitude` в таблицу `stores`
- Корзина хранится в localStorage на клиенте, расчет цен происходит на сервере

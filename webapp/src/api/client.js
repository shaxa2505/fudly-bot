import axios from 'axios'
import { captureException } from '../utils/sentry'
import { LRUCache } from '../utils/lruCache'

const API_BASE = import.meta.env.VITE_API_URL || 'https://fudly-bot-production.up.railway.app/api/v1'

// Flag to track if API is available - start as false for demo mode
let apiAvailable = false
let apiCheckTime = 0
const API_CHECK_INTERVAL = 60000 // Re-check every 60 seconds

// LRU cache for GET requests with automatic eviction
const requestCache = new LRUCache(100, 30000) // 100 items, 30s TTL
const CACHE_TTL = 30000 // 30 seconds cache

// Demo data for when API is unavailable
const DEMO_OFFERS = [
  {
    id: 1,
    title: 'Olma - Qizil',
    description: 'Yangi uzilgan olmalar, shirin va mazali',
    discount_price: 15000,
    original_price: 20000,
    discount_percent: 25,
    quantity: 50,
    unit: 'kg',
    category: 'fruits',
    city: 'Toshkent',
    photo: 'https://images.unsplash.com/photo-1560806887-1e4cd0b6cbd6?w=300',
    store_id: 1,
    store_name: 'Fresh Market',
    rating: 4.5,
  },
  {
    id: 2,
    title: 'Banan',
    description: 'Import bananlar, pishgan',
    discount_price: 25000,
    original_price: 32000,
    discount_percent: 22,
    quantity: 30,
    unit: 'kg',
    category: 'fruits',
    city: 'Toshkent',
    photo: 'https://images.unsplash.com/photo-1571771894821-ce9b6c11b08e?w=300',
    store_id: 1,
    store_name: 'Fresh Market',
    rating: 4.7,
  },
  {
    id: 3,
    title: 'Sut 1L',
    description: 'Yangi sut, tabiiy',
    discount_price: 12000,
    original_price: 15000,
    discount_percent: 20,
    quantity: 100,
    unit: 'dona',
    category: 'dairy',
    city: 'Toshkent',
    photo: 'https://images.unsplash.com/photo-1563636619-e9143da7973b?w=300',
    store_id: 2,
    store_name: 'Sut Mahsulotlari',
    rating: 4.3,
  },
  {
    id: 4,
    title: 'Non - Obi non',
    description: 'Issiq tandirda pishirilgan',
    discount_price: 5000,
    original_price: 7000,
    discount_percent: 29,
    quantity: 200,
    unit: 'dona',
    category: 'bakery',
    city: 'Toshkent',
    photo: 'https://images.unsplash.com/photo-1509440159596-0249088772ff?w=300',
    store_id: 3,
    store_name: 'Novvoyxona',
    rating: 4.9,
  },
  {
    id: 5,
    title: 'Pomidor',
    description: 'Mahalliy pomidor, yangi',
    discount_price: 8000,
    original_price: 12000,
    discount_percent: 33,
    quantity: 80,
    unit: 'kg',
    category: 'vegetables',
    city: 'Toshkent',
    photo: 'https://images.unsplash.com/photo-1546470427-227c7369a9b8?w=300',
    store_id: 1,
    store_name: 'Fresh Market',
    rating: 4.4,
  },
  {
    id: 6,
    title: 'Bodring',
    description: 'Yangi bodringlar',
    discount_price: 6000,
    original_price: 8000,
    discount_percent: 25,
    quantity: 60,
    unit: 'kg',
    category: 'vegetables',
    city: 'Toshkent',
    photo: 'https://images.unsplash.com/photo-1449300079323-02e209d9d3a6?w=300',
    store_id: 1,
    store_name: 'Fresh Market',
    rating: 4.2,
  },
  {
    id: 7,
    title: "Mol go'shti",
    description: "Yangi mol go'shti",
    discount_price: 85000,
    original_price: 100000,
    discount_percent: 15,
    quantity: 25,
    unit: 'kg',
    category: 'meat',
    city: 'Toshkent',
    photo: 'https://images.unsplash.com/photo-1603048297172-c92544798d5a?w=300',
    store_id: 4,
    store_name: "Go'sht Do'koni",
    rating: 4.6,
  },
  {
    id: 8,
    title: 'Qatiq 500ml',
    description: 'Tabiiy qatiq',
    discount_price: 8000,
    original_price: 10000,
    discount_percent: 20,
    quantity: 50,
    unit: 'dona',
    category: 'dairy',
    city: 'Toshkent',
    photo: 'https://images.unsplash.com/photo-1628088062854-d1870b4553da?w=300',
    store_id: 2,
    store_name: 'Sut Mahsulotlari',
    rating: 4.1,
  },
  {
    id: 9,
    title: 'Apelsin',
    description: 'Shirin apelsinlar',
    discount_price: 22000,
    original_price: 28000,
    discount_percent: 21,
    quantity: 40,
    unit: 'kg',
    category: 'fruits',
    city: 'Toshkent',
    photo: 'https://images.unsplash.com/photo-1547514701-42782101795e?w=300',
    store_id: 1,
    store_name: 'Fresh Market',
    rating: 4.5,
  },
  {
    id: 10,
    title: 'Piyoz',
    description: 'Mahalliy piyoz',
    discount_price: 4000,
    original_price: 6000,
    discount_percent: 33,
    quantity: 100,
    unit: 'kg',
    category: 'vegetables',
    city: 'Toshkent',
    photo: 'https://images.unsplash.com/photo-1518977956812-cd3dbadaaf31?w=300',
    store_id: 1,
    store_name: 'Fresh Market',
    rating: 4.3,
  },
  {
    id: 11,
    title: 'Tuxum 30 dona',
    description: 'Yangi tovuq tuxumi',
    discount_price: 45000,
    original_price: 55000,
    discount_percent: 18,
    quantity: 30,
    unit: 'dona',
    category: 'dairy',
    city: 'Toshkent',
    photo: 'https://images.unsplash.com/photo-1582722872445-44dc5f7e3c8f?w=300',
    store_id: 2,
    store_name: 'Sut Mahsulotlari',
    rating: 4.4,
  },
  {
    id: 12,
    title: "Tovuq go'shti",
    description: "Yangi tovuq go'shti",
    discount_price: 38000,
    original_price: 45000,
    discount_percent: 16,
    quantity: 35,
    unit: 'kg',
    category: 'meat',
    city: 'Toshkent',
    photo: 'https://images.unsplash.com/photo-1604503468506-a8da13d82791?w=300',
    store_id: 4,
    store_name: "Go'sht Do'koni",
    rating: 4.7,
  },
]

const DEMO_STORES = [
  { id: 1, name: 'Fresh Market', address: 'Toshkent, Chilonzor 7-kvartal', rating: 4.5, photo: 'https://images.unsplash.com/photo-1604719312566-8912e9227c6a?w=300' },
  { id: 2, name: 'Sut Mahsulotlari', address: 'Toshkent, Yunusobod', rating: 4.2, photo: 'https://images.unsplash.com/photo-1534723452862-4c874018d66d?w=300' },
  { id: 3, name: 'Novvoyxona', address: 'Toshkent, Mirzo Ulugbek', rating: 4.8, photo: 'https://images.unsplash.com/photo-1517433670267-30f41c09aea8?w=300' },
  { id: 4, name: "Go'sht Do'koni", address: 'Toshkent, Sergeli', rating: 4.6, photo: 'https://images.unsplash.com/photo-1588347818036-558601350947?w=300' },
]

const DEMO_CATEGORIES = [
  { id: 'fruits', name: 'Mevalar', icon: '🍎' },
  { id: 'vegetables', name: 'Sabzavotlar', icon: '🥬' },
  { id: 'dairy', name: 'Sut mahsulotlari', icon: '🥛' },
  { id: 'bakery', name: 'Non mahsulotlari', icon: '🍞' },
  { id: 'meat', name: "Go'sht", icon: '🥩' },
]

// Cleanup expired cache entries every 5 minutes
setInterval(() => {
  const cleaned = requestCache.cleanup()
  if (cleaned > 0) {
    console.log(`[Cache] Cleaned ${cleaned} expired entries`)
  }
}, 5 * 60 * 1000)

// Retry configuration
const RETRY_CONFIG = {
  retries: 2,
  retryDelay: 500,
  retryCondition: (error) => {
    return !error.response || (error.response.status >= 500 && error.response.status <= 599)
  },
}

// Helper function to delay
const delay = (ms) => new Promise(resolve => setTimeout(resolve, ms))

// Create axios instance
const client = axios.create({
  baseURL: API_BASE,
  timeout: 10000, // 10s timeout
})

// Add auth header
client.interceptors.request.use((config) => {
  if (window.Telegram?.WebApp?.initData) {
    config.headers['X-Telegram-Init-Data'] = window.Telegram.WebApp.initData
  }
  config.__retryCount = config.__retryCount || 0
  return config
})

// Handle errors with retry logic
client.interceptors.response.use(
  (response) => response,
  async (error) => {
    const config = error.config

    if (
      config &&
      config.__retryCount < RETRY_CONFIG.retries &&
      RETRY_CONFIG.retryCondition(error)
    ) {
      config.__retryCount += 1
      const backoffDelay = RETRY_CONFIG.retryDelay * Math.pow(2, config.__retryCount - 1)
      await delay(backoffDelay)
      return client(config)
    }

    // Log failed requests to Sentry (after all retries exhausted)
    if (error.response?.status >= 400) {
      captureException(error, {
        url: config?.url,
        method: config?.method,
        status: error.response?.status,
        data: error.response?.data,
      })
    }

    return Promise.reject(error)
  }
)

// Check if API is available (with caching)
const checkApiAvailable = async () => {
  const now = Date.now()
  if (now - apiCheckTime < API_CHECK_INTERVAL) {
    return apiAvailable
  }

  try {
    await client.get('/health', { timeout: 3000 })
    apiAvailable = true
  } catch (error) {
    apiAvailable = false
    console.warn('[API] Backend unavailable, using demo mode')
  }

  apiCheckTime = now
  return apiAvailable
}

// Safe cached GET with fallback
const safeCachedGet = async (url, params = {}, ttl = CACHE_TTL, fallback = null) => {
  const cacheKey = `${url}?${JSON.stringify(params)}`

  // Try to get from cache first
  const cached = requestCache.get(cacheKey)
  if (cached !== null) {
    return cached
  }

  try {
    const response = await client.get(url, { params })
    const data = response.data
    requestCache.set(cacheKey, data)
    apiAvailable = true
    return data
  } catch (error) {
    apiAvailable = false
    console.warn(`[API] Request failed for ${url}, using fallback`)
    return fallback
  }
}

// Cached GET request helper with LRU cache
const cachedGet = async (url, params = {}, ttl = CACHE_TTL) => {
  const cacheKey = `${url}?${JSON.stringify(params)}`

  // Try to get from cache
  const cached = requestCache.get(cacheKey)
  if (cached !== null) {
    return cached
  }

  // Fetch from API
  const response = await client.get(url, { params })
  const data = response.data

  // Store in cache (LRU handles eviction automatically)
  requestCache.set(cacheKey, data)

  return data
}

// Clear cache for specific URL pattern
const clearCache = (urlPattern) => {
  const keys = requestCache.keys()
  let cleared = 0

  keys.forEach(key => {
    if (key.includes(urlPattern)) {
      requestCache.delete(key)
      cleared++
    }
  })

  if (cleared > 0) {
    console.log(`[Cache] Cleared ${cleared} entries matching: ${urlPattern}`)
  }
}

// Get cache statistics (for debugging)
const getCacheStats = () => requestCache.getStats()

const api = {
  // Helper to convert Telegram file_id to photo URL
  getPhotoUrl(photo) {
    if (!photo) return null

    // Already a URL
    if (photo.startsWith('http://') || photo.startsWith('https://')) {
      return photo
    }

    // Telegram file_id - use our API endpoint
    if (photo.startsWith('AgAC') || photo.length > 50) {
      return `${API_BASE}/photo/${encodeURIComponent(photo)}`
    }

    return null
  },

  // Auth endpoints
  async validateAuth(initData) {
    try {
      const { data } = await client.post('/auth/validate', { init_data: initData })
      return data
    } catch (error) {
      console.warn('[API] Auth validation failed')
      return null
    }
  },

  async getProfile(userId) {
    try {
      return await cachedGet('/user/profile', { user_id: userId }, 60000)
    } catch (error) {
      console.warn('[API] Profile fetch failed')
      return null
    }
  },

  async getUserOrders(userId, status = null) {
    try {
      const params = { user_id: userId }
      if (status) params.status = status
      return await cachedGet('/user/orders', params, 10000)
    } catch (error) {
      return []
    }
  },

  async getUserBookings(userId, status = null) {
    try {
      const params = { user_id: userId }
      if (status) params.status = status
      const data = await cachedGet('/orders', params, 10000)
      return data.bookings || data.orders || data || []
    } catch (error) {
      return []
    }
  },

  async getStores(params = {}) {
    const data = await safeCachedGet('/stores', params, 60000, DEMO_STORES)
    return Array.isArray(data) ? data : DEMO_STORES
  },

  async getStore(storeId) {
    try {
      return await cachedGet(`/stores/${storeId}`, {}, 60000)
    } catch (error) {
      return DEMO_STORES.find(s => s.id === storeId) || null
    }
  },

  async getStoreOffers(storeId) {
    const data = await safeCachedGet('/offers', { store_id: storeId }, 30000, DEMO_OFFERS.filter(o => o.store_id === storeId))
    return Array.isArray(data) ? data : []
  },

  async getStoreReviews(storeId) {
    try {
      return await cachedGet(`/stores/${storeId}/reviews`, {}, 120000)
    } catch (error) {
      return { reviews: [], average_rating: 0, total_reviews: 0 }
    }
  },

  // Offers endpoints - shorter cache for freshness
  async getOffers(params) {
    const data = await safeCachedGet('/offers', params, 20000, DEMO_OFFERS)
    return Array.isArray(data) ? data : DEMO_OFFERS
  },

  async getOfferById(offerId) {
    if (!offerId) return null
    try {
      return await cachedGet(`/offers/${offerId}`, {}, 20000)
    } catch (error) {
      return DEMO_OFFERS.find(o => o.id === offerId) || null
    }
  },

  async getFlashDeals(city = 'Ташкент', limit = 10) {
    const data = await safeCachedGet('/flash-deals', { city, limit }, 30000, DEMO_OFFERS.slice(0, 2))
    return Array.isArray(data) ? data : []
  },

  async getFavorites() {
    try {
      const { data } = await client.get('/favorites')
      return data
    } catch {
      return []
    }
  },

  async addFavorite(offerId) {
    const { data } = await client.post('/favorites/add', { offer_id: offerId })
    return data
  },

  async removeFavorite(offerId) {
    const { data } = await client.post('/favorites/remove', { offer_id: offerId })
    return data
  },

  async calculateCart(items) {
    const offerIds = items.map(i => `${i.offerId}:${i.quantity}`).join(',')
    const { data } = await client.get('/cart/calculate', {
      params: { offer_ids: offerIds },
    })
    return data
  },

  async createOrder(orderData) {
    try {
      const { data } = await client.post('/orders', orderData)
      return data
    } catch (error) {
      // Extract error message from response
      const errorMsg = error.response?.data?.error || error.response?.data?.message || error.message
      throw new Error(errorMsg || 'Order creation failed')
    }
  },

  // Order tracking endpoints (Week 2)
  async getOrderStatus(bookingId) {
    const { data } = await client.get(`/orders/${bookingId}/status`)
    return data
  },

  async getOrderTimeline(bookingId) {
    const { data } = await client.get(`/orders/${bookingId}/timeline`)
    return data
  },

  async getOrderQR(bookingId) {
    const { data } = await client.get(`/orders/${bookingId}/qr`)
    return data
  },

  async calculateDelivery(deliveryData) {
    const { data } = await client.post('/orders/calculate-delivery', deliveryData)
    return data
  },

  // Payment endpoints
  async getPaymentCard(storeId) {
    const { data } = await client.get(`/payment-card/${storeId}`)
    return data
  },

  async uploadPaymentProof(orderId, photoFile) {
    const formData = new FormData()
    formData.append('photo', photoFile)

    const { data } = await client.post(`/orders/${orderId}/payment-proof`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
    return data
  },

  // Recently viewed endpoints
  async addRecentlyViewed(userId, offerId) {
    try {
      const { data } = await client.post('/user/recently-viewed', { user_id: userId, offer_id: offerId })
      return data
    } catch (error) {
      console.warn('addRecentlyViewed error:', error)
      return null
    }
  },

  async getRecentlyViewed(userId, limit = 20) {
    try {
      const { data } = await client.get('/user/recently-viewed', { params: { user_id: userId, limit } })
      return data.offers || []
    } catch (error) {
      console.warn('getRecentlyViewed error:', error)
      return []
    }
  },

  // Search history endpoints
  async addSearchHistory(userId, query) {
    try {
      const { data } = await client.post('/user/search-history', { user_id: userId, query })
      return data
    } catch (error) {
      console.warn('addSearchHistory error:', error)
      return null
    }
  },

  async getSearchHistory(userId, limit = 10) {
    try {
      const { data } = await client.get('/user/search-history', { params: { user_id: userId, limit } })
      return data.history || []
    } catch (error) {
      console.warn('getSearchHistory error:', error)
      return []
    }
  },

  async clearSearchHistory(userId) {
    try {
      const { data } = await client.delete('/user/search-history', { params: { user_id: userId } })
      return data
    } catch (error) {
      console.warn('clearSearchHistory error:', error)
      return null
    }
  },

  // Online payment endpoints
  async getPaymentProviders() {
    try {
      const { data } = await client.get('/payment/providers')
      // API returns [{ id: 'click', ... }] - extract IDs as strings
      const providers = data.providers || []
      return providers.map(p => typeof p === 'string' ? p : p.id)
    } catch (error) {
      console.warn('getPaymentProviders error:', error)
      return []
    }
  },

  async createPaymentLink(orderId, provider, returnUrl = null, storeId = null, amount = null, userId = null) {
    try {
      const { data } = await client.post('/payment/create', {
        order_id: orderId,
        provider: provider,
        return_url: returnUrl,
        store_id: storeId,
        amount: amount,
        user_id: userId,
      })
      return data
    } catch (error) {
      console.warn('createPaymentLink error:', error)
      throw error
    }
  },

  // Check if API is available
  isApiAvailable() {
    return apiAvailable
  },

  // Force check API availability
  async checkApi() {
    return await checkApiAvailable()
  },
}

// Export cache utilities for external use
export { clearCache, getCacheStats }

export default api
export const API_BASE_URL = API_BASE

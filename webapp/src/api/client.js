import axios from 'axios'
import { captureException } from '../utils/sentry'
import LRUCache from '../utils/lruCache'

const API_BASE = import.meta.env.VITE_API_URL || 'https://fudly-bot-production.up.railway.app/api/v1'

// In-memory cache for GET requests
const CACHE_TTL = 30000 // 30 seconds cache
const CACHE_MAX_TTL = 600000 // 10 minutes max TTL for LRU eviction
const requestCache = new LRUCache(100, CACHE_MAX_TTL)
const inFlightRequests = new Map()

// Retry configuration
const RETRY_CONFIG = {
  retries: 2,
  retryDelay: 500,
  retryCondition: (error) => {
    const config = error?.config
    if (!config || !config.__idempotent) {
      return false
    }
    return !error.response || (error.response.status >= 500 && error.response.status <= 599)
  },
}

const IDEMPOTENT_METHODS = new Set(['get', 'head', 'options', 'put', 'delete'])

const INITDATA_KEY = 'fudly_init_data'
const INITDATA_TS_KEY = 'fudly_init_data_ts'
const INITDATA_TTL_MS = 24 * 60 * 60 * 1000

const getSessionStorage = () => {
  try {
    return window.sessionStorage
  } catch {
    return null
  }
}

const getLocalStorage = () => {
  try {
    return window.localStorage
  } catch {
    return null
  }
}

const readStoredInitData = (userId = null) => {
  const suffix = userId ? `_${userId}` : ''
  const storages = [getSessionStorage(), getLocalStorage()].filter(Boolean)
  if (!storages.length) return null

  for (const storage of storages) {
    const initData = storage.getItem(`${INITDATA_KEY}${suffix}`)
    if (!initData) continue
    const tsRaw = storage.getItem(`${INITDATA_TS_KEY}${suffix}`)
    const ts = tsRaw ? Number(tsRaw) : 0
    if (!ts || Date.now() - ts > INITDATA_TTL_MS) {
      storage.removeItem(`${INITDATA_KEY}${suffix}`)
      storage.removeItem(`${INITDATA_TS_KEY}${suffix}`)
      continue
    }
    return initData
  }

  return null
}

export const saveTelegramInitData = (initData, userId = null) => {
  const storage = getSessionStorage() || getLocalStorage()
  if (!storage || !initData) return
  const suffix = userId ? `_${userId}` : ''
  storage.setItem(`${INITDATA_KEY}${suffix}`, initData)
  storage.setItem(`${INITDATA_TS_KEY}${suffix}`, String(Date.now()))
  if (userId) {
    storage.setItem('fudly_last_user_id', String(userId))
  }
}

export const clearTelegramInitData = (userId = null) => {
  const suffix = userId ? `_${userId}` : ''
  const storages = [getSessionStorage(), getLocalStorage()].filter(Boolean)
  for (const storage of storages) {
    storage.removeItem(`${INITDATA_KEY}${suffix}`)
    storage.removeItem(`${INITDATA_TS_KEY}${suffix}`)
    if (!userId) {
      storage.removeItem('fudly_last_user_id')
    }
  }
}

export const getTelegramInitData = () => {
  const tgWebApp = window.Telegram?.WebApp
  const tgInitData = tgWebApp?.initData
  if (tgInitData) {
    return tgInitData
  }

  const tgUserId = tgWebApp?.initDataUnsafe?.user?.id
  if (tgUserId) {
    return readStoredInitData(tgUserId)
  }

  const storage = getSessionStorage() || getLocalStorage()
  const lastUserId = storage?.getItem('fudly_last_user_id')
  if (lastUserId) {
    return readStoredInitData(lastUserId)
  }

  return readStoredInitData()
}

const getCacheScopeKey = () => {
  const tgUserId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id
  if (tgUserId) {
    return `u:${tgUserId}`
  }
  const storage = getSessionStorage()
  const lastUserId =
    storage?.getItem('fudly_last_user_id') ||
    getLocalStorage()?.getItem('fudly_last_user_id')
  if (lastUserId) {
    return `u:${lastUserId}`
  }
  return 'u:anon'
}

// Helper function to delay
const delay = (ms) => new Promise(resolve => setTimeout(resolve, ms))

const generateIdempotencyKey = () => {
  if (typeof crypto !== 'undefined') {
    if (crypto.randomUUID) return crypto.randomUUID()
    if (crypto.getRandomValues) {
      const bytes = new Uint8Array(16)
      crypto.getRandomValues(bytes)
      return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
    }
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2, 10)}`
}

// Create axios instance
const client = axios.create({
  baseURL: API_BASE,
  timeout: 10000, // 10s timeout
})

// Add auth header
client.interceptors.request.use((config) => {
  const initData = getTelegramInitData()
  if (initData) {
    config.headers['X-Telegram-Init-Data'] = initData
  }
  const headers = config.headers || {}
  const hasIdempotencyKey = Boolean(headers['Idempotency-Key']) ||
    Boolean(headers['X-Idempotency-Key']) ||
    (typeof headers.get === 'function' &&
      (headers.get('Idempotency-Key') || headers.get('X-Idempotency-Key')))
  const method = (config.method || 'get').toLowerCase()
  config.__idempotent = IDEMPOTENT_METHODS.has(method) || hasIdempotencyKey
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

const serializeParams = (params) => {
  const entries = Object.entries(params || {})
  if (entries.length === 0) return ''
  entries.sort(([a], [b]) => a.localeCompare(b))
  return entries.map(([key, value]) => `${key}:${JSON.stringify(value)}`).join('&')
}

const buildCacheKey = (url, params) => `${getCacheScopeKey()}|${url}?${serializeParams(params)}`

const safeJoinUrl = (base, path) => {
  try {
    return new URL(path, base).toString()
  } catch {
    if (!base) return path
    const trimmedBase = base.endsWith('/') ? base.slice(0, -1) : base
    const trimmedPath = path.startsWith('/') ? path : `/${path}`
    return `${trimmedBase}${trimmedPath}`
  }
}

const getCachedEntry = (cacheKey) => {
  const cached = requestCache.get(cacheKey)
  if (!cached) return null
  const age = Date.now() - cached.timestamp
  if (age > cached.ttl) {
    requestCache.delete(cacheKey)
    return null
  }
  return cached.data
}

// Cached GET request helper
const cachedGet = async (url, params = {}, ttl = CACHE_TTL, options = {}) => {
  const { force = false } = options
  const cacheKey = buildCacheKey(url, params)

  if (!force) {
    const cached = getCachedEntry(cacheKey)
    if (cached !== null) return cached
  } else {
    requestCache.delete(cacheKey)
  }

  if (inFlightRequests.has(cacheKey)) {
    return inFlightRequests.get(cacheKey)
  }

  const requestPromise = client.get(url, { params })
    .then(({ data }) => {
      if (!force) {
        requestCache.set(cacheKey, { data, timestamp: Date.now(), ttl })
      } else {
        requestCache.delete(cacheKey)
      }
      return data
    })
    .finally(() => {
      inFlightRequests.delete(cacheKey)
    })

  inFlightRequests.set(cacheKey, requestPromise)
  return requestPromise
}

// Helper to invalidate cache by pattern
const invalidateCache = (pattern) => {
  for (const key of requestCache.keys()) {
    if (key.includes(pattern)) {
      requestCache.delete(key)
    }
  }
}

const api = {
  // Helper to convert Telegram file_id to photo URL
  getPhotoUrl(photo) {
    if (photo == null) return null
    if (typeof photo === 'number') {
      photo = String(photo)
    }
    if (typeof photo !== 'string') return null

    const normalized = photo.trim()
    if (!normalized) return null
    const lowered = normalized.toLowerCase()
    if (lowered === 'null' || lowered === 'undefined' || lowered === 'none' || lowered === 'nan') {
      return null
    }

    if (normalized.startsWith('data:') || normalized.startsWith('blob:')) {
      return normalized
    }

    // Already a URL
    if (normalized.startsWith('http://') || normalized.startsWith('https://')) {
      return normalized
    }

    // Relative paths from API responses
    if (normalized.startsWith('/photo/')) {
      return `${API_BASE}${normalized}`
    }

    if (normalized.startsWith('photo/')) {
      return `${API_BASE}/${normalized}`
    }

    if (normalized.startsWith('/')) {
      return safeJoinUrl(API_BASE, normalized)
    }

    if (normalized.startsWith('api/')) {
      return safeJoinUrl(API_BASE, `/${normalized}`)
    }

    // Telegram file_id or storage id - use our API endpoint
    return `${API_BASE}/photo/${encodeURIComponent(normalized)}`
  },

  // Auth endpoints
  async validateAuth(initData) {
    const { data } = await client.post('/auth/validate', { init_data: initData })
    return data
  },

  async getProfile(options = {}) {
    return cachedGet('/user/profile', {}, 60000, options) // 1 min cache
  },

  async getUserOrders(status = null) {
    const params = {}
    if (status) params.status = status
    return cachedGet('/user/orders', params, 10000) // 10s cache
  },

  async getOrders(options = {}) {
    const normalizedOptions =
      typeof options === 'boolean' ? { force: options } : (options || {})
    // Unified endpoint for both legacy bookings and orders (aiohttp Mini App API)
    const data = await cachedGet('/orders', {}, 10000, normalizedOptions)
    if (Array.isArray(data)) {
      return { orders: data, bookings: [] }
    }
    return data
  },

  async getUserBookings(status = null) {
    try {
      const data = await this.getUserOrders(status)
      return data.orders || []
    } catch (error) {
      return []
    }
  },

  async getDeliveryOrders(userId) {
    try {
      const data = await this.getOrders()
      return data.orders || []
    } catch (error) {
      console.error('Error fetching delivery orders:', error)
      return []
    }
  },

  async getStores(params = {}) {
    return cachedGet('/stores', params, 60000) || [] // 1 min cache
  },

  async getStore(storeId) {
    return cachedGet(`/stores/${storeId}`, {}, 60000)
  },

  async getOffer(offerId, options = {}) {
    if (!offerId) return null
    const normalizedOptions =
      typeof options === 'boolean' ? { force: options } : (options || {})
    return cachedGet(`/offers/${offerId}`, {}, 20000, normalizedOptions)
  },

  async getStoreOffers(storeId) {
    return cachedGet('/offers', { store_id: storeId }, 30000) || []
  },

  async getStoreReviews(storeId) {
    try {
      return await cachedGet(`/stores/${storeId}/reviews`, {}, 120000)
    } catch (error) {
      return { reviews: [], average_rating: 0, total_reviews: 0 }
    }
  },

  // Offers endpoints - shorter cache for freshness
  async getOffers(params = {}, options = {}) {
    return cachedGet('/offers', params, 20000, options) // 20s cache
  },

  async getFlashDeals(options = {}) {
    const { city = '', region = '', district = '', limit = 10 } = options
    const params = { limit }
    if (city) params.city = city
    if (region) params.region = region
    if (district) params.district = district
    return cachedGet('/flash-deals', params, 30000) // 30s cache
  },

  async getCategories(params = {}, options = {}) {
    return cachedGet('/categories', params, 60000, options) || []
  },

  async getSearchSuggestions(query, limit = 5, options = {}) {
    if (!query || query.length < 2) return []
    const params = { query, limit }
    if (options?.city) {
      params.city = options.city
    }
    if (options?.region) {
      params.region = options.region
    }
    if (options?.district) {
      params.district = options.district
    }
    return cachedGet('/search/suggestions', params, 15000) || []
  },

  async searchAll(query, options = {}) {
    const normalized = String(query || '').trim()
    if (normalized.length < 2) {
      return { query: normalized, offers: [], stores: [] }
    }
    const {
      city,
      region,
      district,
      limit_offers = 5,
      limit_stores = 5,
      offset_offers = 0,
      offset_stores = 0,
    } = options
    const params = {
      query: normalized,
      limit_offers,
      limit_stores,
      offset_offers,
      offset_stores,
    }
    if (city) params.city = city
    if (region) params.region = region
    if (district) params.district = district
    return cachedGet('/search', params, 10000, options) || { query: normalized, offers: [], stores: [] }
  },

  async reverseGeocode(lat, lon, lang = 'uz') {
    if (lat == null || lon == null) return null
    return cachedGet('/location/reverse', { lat, lon, lang }, 3600000)
  },

  async searchLocations(query, options = {}) {
    const normalized = String(query || '').trim()
    if (normalized.length < 2) return []
    const params = {
      query: normalized,
      lang: options.lang || 'uz',
      limit: options.limit || 8,
    }
    if (options.lat != null) params.lat = options.lat
    if (options.lon != null) params.lon = options.lon
    if (options.radius_km != null) params.radius_km = options.radius_km
    if (options.countrycodes != null) params.countrycodes = options.countrycodes
    return cachedGet('/location/search', params, 120000)
  },

  async getFavorites() {
    try {
      const { data } = await client.get('/favorites')
      return data
    } catch {
      return []
    }
  },

  async getFavoriteOffers() {
    try {
      const { data } = await client.get('/favorites/offers')
      return data
    } catch {
      return []
    }
  },

  async addFavorite(offerId) {
    const { data } = await client.post('/favorites/offers/add', { offer_id: offerId })
    return data
  },

  async addFavoriteStore(storeId) {
    const { data } = await client.post('/favorites/add', { store_id: storeId })
    return data
  },

  async removeFavorite(offerId) {
    const { data } = await client.post('/favorites/offers/remove', { offer_id: offerId })
    return data
  },

  async removeFavoriteStore(storeId) {
    const { data } = await client.post('/favorites/remove', { store_id: storeId })
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
      const idempotencyKey = generateIdempotencyKey()
      const { data } = await client.post('/orders', orderData, {
        headers: {
          'Idempotency-Key': idempotencyKey,
        },
      })
      return data
    } catch (error) {
      // Extract error message from response
      const errorMsg =
        error.response?.data?.detail ||
        error.response?.data?.error ||
        error.response?.data?.message ||
        error.message
      throw new Error(errorMsg || 'Order creation failed')
    }
  },

  // Order tracking endpoints (v24+ unified orders)
  async getOrderStatus(orderId) {
    const { data } = await client.get(`/orders/${orderId}/status`)
    return data
  },

  async getOrderTimeline(orderId) {
    const { data } = await client.get(`/orders/${orderId}/timeline`)
    return data
  },

  async getOrderQR(orderId) {
    const { data } = await client.get(`/orders/${orderId}/qr`)
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

  // Recently viewed endpoints
  async addRecentlyViewed(offerId) {
    try {
      const { data } = await client.post('/user/recently-viewed', { offer_id: offerId })
      return data
    } catch (error) {
      console.warn('addRecentlyViewed error:', error)
      return null
    }
  },

  async getRecentlyViewed(limit = 20) {
    try {
      const { data } = await client.get('/user/recently-viewed', { params: { limit } })
      return data.offers || []
    } catch (error) {
      console.warn('getRecentlyViewed error:', error)
      return []
    }
  },

  // Search history endpoints
  async addSearchHistory(query) {
    try {
      const { data } = await client.post('/user/search-history', { query })
      return data
    } catch (error) {
      console.warn('addSearchHistory error:', error)
      return null
    }
  },

  async getSearchHistory(limit = 10) {
    try {
      const { data } = await client.get('/user/search-history', { params: { limit } })
      return data.history || []
    } catch (error) {
      console.warn('getSearchHistory error:', error)
      return []
    }
  },

  async clearSearchHistory() {
    try {
      const { data } = await client.delete('/user/search-history')
      return data
    } catch (error) {
      console.warn('clearSearchHistory error:', error)
      return null
    }
  },

  async getNotificationSettings() {
    const { data } = await client.get('/user/notifications')
    return data
  },

  async setNotificationEnabled(enabled) {
    const { data } = await client.post('/user/notifications', { enabled })
    return data
  },

  // Online payment endpoints
  async getPaymentProviders(storeId = null) {
    try {
      const { data } = await client.get('/payment/providers', {
        params: storeId ? { store_id: storeId } : {},
      })
      // API returns [{ id: 'click', ... }] - extract IDs as strings
      const providers = data.providers || []
      return providers.map(p => typeof p === 'string' ? p : p.id)
    } catch (error) {
      console.warn('getPaymentProviders error:', error)
      return []
    }
  },

  async createPaymentLink(orderId, provider, returnUrl = null, storeId = null, amount = null) {
    try {
      const { data } = await client.post('/payment/create', {
        order_id: orderId,
        provider: provider,
        return_url: returnUrl,
        store_id: storeId,
        amount: amount,
      })
      return data
    } catch (error) {
      console.warn('createPaymentLink error:', error)
      throw error
    }
  },

  async cancelOrder(orderId) {
    const { data } = await client.post(`/orders/${orderId}/cancel`)
    // Invalidate orders cache to force refresh
    invalidateCache('/orders')
    invalidateCache('/user/orders')
    return data
  },
}

export default api
export const API_BASE_URL = API_BASE

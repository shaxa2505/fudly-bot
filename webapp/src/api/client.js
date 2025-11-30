import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_URL || 'https://fudly-bot-production.up.railway.app/api/v1'

// Retry configuration
const RETRY_CONFIG = {
  retries: 3,
  retryDelay: 1000, // 1 second
  retryCondition: (error) => {
    // Retry on network errors or 5xx server errors
    return !error.response || (error.response.status >= 500 && error.response.status <= 599)
  },
}

// Helper function to delay
const delay = (ms) => new Promise(resolve => setTimeout(resolve, ms))

// Create axios instance
const client = axios.create({
  baseURL: API_BASE,
  timeout: 15000, // Increased timeout to 15s
})

// Add auth header
client.interceptors.request.use((config) => {
  if (window.Telegram?.WebApp?.initData) {
    config.headers['X-Telegram-Init-Data'] = window.Telegram.WebApp.initData
  }
  // Add retry count to config
  config.__retryCount = config.__retryCount || 0
  return config
})

// Handle errors with retry logic
client.interceptors.response.use(
  (response) => response,
  async (error) => {
    const config = error.config

    // Check if we should retry
    if (
      config &&
      config.__retryCount < RETRY_CONFIG.retries &&
      RETRY_CONFIG.retryCondition(error)
    ) {
      config.__retryCount += 1

      // Calculate delay with exponential backoff
      const backoffDelay = RETRY_CONFIG.retryDelay * Math.pow(2, config.__retryCount - 1)

      console.log(`Retrying request (${config.__retryCount}/${RETRY_CONFIG.retries}) after ${backoffDelay}ms...`)

      await delay(backoffDelay)
      return client(config)
    }

    // Log error
    console.error('API Error:', error)

    // Show user-friendly error for server errors
    if (error.response?.status >= 500) {
      window.Telegram?.WebApp?.showAlert?.('Serverda xatolik. Keyinroq urinib ko\'ring.')
    } else if (!error.response) {
      window.Telegram?.WebApp?.showAlert?.('Internet aloqasi yo\'q. Tarmoqni tekshiring.')
    }

    return Promise.reject(error)
  }
)

const api = {
  // Auth endpoints
  async validateAuth(initData) {
    const { data } = await client.post('/auth/validate', { init_data: initData })
    return data
  },

  async getProfile(userId) {
    const { data } = await client.get('/user/profile', { params: { user_id: userId } })
    return data
  },

  async getUserOrders(userId, status = null) {
    const params = { user_id: userId }
    if (status) params.status = status
    const { data } = await client.get('/user/orders', { params })
    return data
  },

  async getUserBookings(userId, status = null) {
    try {
      const params = { user_id: userId }
      if (status) params.status = status
      const { data } = await client.get('/user/bookings', { params })
      return data.bookings || data || []
    } catch (error) {
      console.warn('getUserBookings not available:', error)
      return []
    }
  },

  async getStores(params = {}) {
    const { data } = await client.get('/stores', { params })
    return data || []
  },

  async getStore(storeId) {
    const { data } = await client.get(`/stores/${storeId}`)
    return data
  },

  async getStoreOffers(storeId) {
    const { data } = await client.get('/offers', { params: { store_id: storeId } })
    return data || []
  },

  // Offers endpoints
  async getOffers(params) {
    const { data } = await client.get('/offers', { params })
    return data
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
    const { data } = await client.post('/orders', orderData)
    return data
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
}

export default api
export const API_BASE_URL = API_BASE

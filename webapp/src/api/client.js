import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_URL || 'https://fudly-bot-production.up.railway.app/api/v1'

const client = axios.create({
  baseURL: API_BASE,
  timeout: 10000,
})

// Add auth header
client.interceptors.request.use((config) => {
  if (window.Telegram?.WebApp?.initData) {
    config.headers['X-Telegram-Init-Data'] = window.Telegram.WebApp.initData
  }
  return config
})

// Handle errors
client.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Error:', error)
    if (error.response?.status >= 500) {
      window.Telegram?.WebApp?.showAlert?.('Serverda xatolik. Keyinroq urinib ko\'ring.')
    }
    return Promise.reject(error)
  }
)

const api = {
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
}

export default api

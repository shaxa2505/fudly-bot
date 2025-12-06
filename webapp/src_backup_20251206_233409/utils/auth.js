// Telegram Mini App Authentication Utility
// Validates user and handles registration flow

import api from '../api/client'

/**
 * Initialize Telegram WebApp and validate authentication
 * @returns {Promise<Object>} User profile or null if validation fails
 */
export const initializeTelegramAuth = async () => {
  const tg = window.Telegram?.WebApp

  if (!tg) {
    console.error('Telegram WebApp is not available')
    return null
  }

  // Expand WebApp to full height
  tg.expand()

  // Enable closing confirmation
  tg.enableClosingConfirmation()

  // Set theme colors
  tg.setHeaderColor('#FF6B35')
  tg.setBackgroundColor('#FAFAFA')

  // Get initData for authentication
  const initData = tg.initData
  const user = tg.initDataUnsafe?.user

  if (!initData || !user) {
    console.error('No initData available')
    return null
  }

  try {
    // Validate with backend
    const response = await api.post('/auth/validate', {
      init_data: initData
    })

    const profile = response.data

    // Check if user is registered
    if (!profile.registered || !profile.phone) {
      // User needs to register in bot first
      tg.showAlert(
        profile.language === 'uz'
          ? "Iltimos, avval botda ro'yxatdan o'ting"
          : "Пожалуйста, сначала зарегистрируйтесь в боте",
        () => {
          // Open bot for registration
          tg.openTelegramLink(`https://t.me/${import.meta.env.VITE_BOT_USERNAME}?start=register`)
          tg.close()
        }
      )
      return null
    }

    // Save to localStorage
    localStorage.setItem('fudly_user', JSON.stringify(profile))

    return profile
  } catch (error) {
    console.error('Auth validation failed:', error)

    if (error.response?.status === 401) {
      tg.showAlert(
        user.language_code === 'uz'
          ? "Autentifikatsiya xatosi"
          : "Ошибка аутентификации"
      )
    }

    return null
  }
}

/**
 * Get current user from localStorage
 * @returns {Object|null} User profile or null
 */
export const getCurrentUser = () => {
  const userStr = localStorage.getItem('fudly_user')
  if (!userStr) return null

  try {
    return JSON.parse(userStr)
  } catch (e) {
    console.error('Failed to parse user from localStorage:', e)
    return null
  }
}

/**
 * Get user ID (from Telegram or localStorage)
 * @returns {number} User ID or 0 if not available
 */
export const getUserId = () => {
  // Try Telegram first
  const telegramUser = window.Telegram?.WebApp?.initDataUnsafe?.user
  if (telegramUser?.id) {
    return telegramUser.id
  }

  // Fallback to localStorage
  const user = getCurrentUser()
  return user?.user_id || 0
}

/**
 * Get user's city
 * @returns {string|null} City name or null
 */
export const getUserCity = () => {
  const user = getCurrentUser()
  return user?.city || null
}

/**
 * Get user's language
 * @returns {string} Language code ('ru' or 'uz')
 */
export const getUserLanguage = () => {
  const user = getCurrentUser()
  if (user?.language) return user.language

  const telegramLang = window.Telegram?.WebApp?.initDataUnsafe?.user?.language_code
  return telegramLang === 'uz' ? 'uz' : 'ru'
}

/**
 * Logout user (clear localStorage)
 */
export const logout = () => {
  localStorage.removeItem('fudly_user')
  window.Telegram?.WebApp?.close()
}

/**
 * Check if user is authenticated and registered
 * @returns {boolean} True if user is fully registered
 */
export const isAuthenticated = () => {
  const user = getCurrentUser()
  return !!(user?.registered && user?.phone)
}

/**
 * Require authentication - redirect to bot if not authenticated
 * @returns {Promise<boolean>} True if authenticated, false otherwise
 */
export const requireAuth = async () => {
  if (isAuthenticated()) {
    return true
  }

  const profile = await initializeTelegramAuth()
  return !!profile
}

export default {
  initializeTelegramAuth,
  getCurrentUser,
  getUserId,
  getUserCity,
  getUserLanguage,
  logout,
  isAuthenticated,
  requireAuth
}

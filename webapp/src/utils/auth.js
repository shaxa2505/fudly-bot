// Telegram Mini App Authentication Utility
// Validates user and handles registration flow

import api from '../api/client'
import { readStorageItem, writeStorageItem, removeStorageItem } from './storage'

const USER_KEY = 'fudly_user'
const PHONE_KEY = 'fudly_phone'

const parseUserFromInitData = (initData) => {
  if (!initData || typeof initData !== 'string') return null
  try {
    const params = new URLSearchParams(initData)
    const rawUser = params.get('user')
    if (!rawUser) return null
    const parsed = JSON.parse(rawUser)
    return parsed && typeof parsed === 'object' ? parsed : null
  } catch {
    return null
  }
}

const resolveUserId = (explicitId = null) => {
  if (explicitId != null) return explicitId
  const telegramWebApp = window.Telegram?.WebApp
  const telegramUser =
    telegramWebApp?.initDataUnsafe?.user ||
    parseUserFromInitData(telegramWebApp?.initData)
  if (telegramUser?.id) return telegramUser.id
  const storedId = readStorageItem('fudly_last_user_id')
  return storedId || null
}

const buildScopedKey = (baseKey, userId) => (
  userId ? `${baseKey}_${userId}` : baseKey
)

const readScopedItem = (baseKey, userId = null) => {
  const resolvedId = resolveUserId(userId)
  if (resolvedId) {
    const scoped = readStorageItem(buildScopedKey(baseKey, resolvedId))
    if (scoped != null) return scoped
  }
  return readStorageItem(baseKey)
}

const writeScopedItem = (baseKey, value, userId = null) => {
  const resolvedId = resolveUserId(userId)
  const key = buildScopedKey(baseKey, resolvedId)
  writeStorageItem(key, value)
  if (resolvedId) {
    removeStorageItem(baseKey)
  }
  return key
}

export const getStoredUser = (userId = null) => {
  const raw = readScopedItem(USER_KEY, userId)
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch (e) {
    console.error('Failed to parse user from storage:', e)
    return null
  }
}

export const setStoredUser = (profile, userId = null) => {
  if (!profile) return null
  const resolvedId = resolveUserId(
    userId ?? profile?.user_id ?? profile?.id ?? null
  )
  writeScopedItem(USER_KEY, JSON.stringify(profile), resolvedId)
  return resolvedId
}

export const clearStoredUser = (userId = null) => {
  const resolvedId = resolveUserId(userId)
  if (resolvedId) {
    removeStorageItem(buildScopedKey(USER_KEY, resolvedId))
  }
  removeStorageItem(USER_KEY)
}

export const getStoredPhone = (userId = null) => {
  return readScopedItem(PHONE_KEY, userId) || ''
}

export const setStoredPhone = (phone, userId = null) => {
  if (!phone) return null
  const resolvedId = resolveUserId(userId)
  writeScopedItem(PHONE_KEY, String(phone), resolvedId)
  return resolvedId
}

export const clearStoredPhone = (userId = null) => {
  const resolvedId = resolveUserId(userId)
  if (resolvedId) {
    removeStorageItem(buildScopedKey(PHONE_KEY, resolvedId))
  }
  removeStorageItem(PHONE_KEY)
}

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
  tg.setHeaderColor('#F9F9F9')
  tg.setBackgroundColor('#F9F9F9')

  // Get initData for authentication
  const initData = tg.initData
  const user = tg.initDataUnsafe?.user
  
  if (!initData || !user) {
    console.error('No initData available')
    return null
  }

  try {
    // Validate with backend
    const profile = await api.validateAuth(initData)
    
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

    // Save to sessionStorage (reduce persistence of PII)
    setStoredUser(profile)
    
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
 * Get current user from storage
 * @returns {Object|null} User profile or null
 */
export const getCurrentUser = () => {
  return getStoredUser()
}

/**
 * Get user ID (from Telegram or localStorage)
 * @returns {number} User ID or 0 if not available
 */
export const getUserId = () => {
  // Try Telegram first
  const telegramWebApp = window.Telegram?.WebApp
  const telegramUser =
    telegramWebApp?.initDataUnsafe?.user ||
    parseUserFromInitData(telegramWebApp?.initData)
  if (telegramUser?.id) {
    return telegramUser.id
  }
  
  // Fallback to localStorage
  const user = getCurrentUser()
  return user?.user_id || user?.id || 0
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
  const user = getCurrentUser()
  const userId = user?.user_id || user?.id
  const clearByPrefix = (storage, prefix) => {
    if (!storage) return
    const keys = []
    for (let i = 0; i < storage.length; i += 1) {
      const key = storage.key(i)
      if (key && key.startsWith(prefix)) {
        keys.push(key)
      }
    }
    keys.forEach((key) => storage.removeItem(key))
  }

  const clearKey = (storage, key) => {
    if (!storage) return
    storage.removeItem(key)
  }

  clearStoredUser(userId)
  clearStoredPhone(userId)
  removeStorageItem('fudly_init_data')
  removeStorageItem('fudly_init_data_ts')
  removeStorageItem('fudly_last_user_id')
  clearKey(localStorage, 'fudly_cart_v2')
  clearKey(localStorage, 'fudly_favorites')
  clearKey(localStorage, 'fudly_pending_payment')
  clearByPrefix(localStorage, 'fudly_cart_user_')
  clearByPrefix(localStorage, 'fudly_favorites_user_')
  clearByPrefix(localStorage, 'fudly_pending_payment_user_')
  if (userId) {
    removeStorageItem(`fudly_init_data_${userId}`)
  }

  try {
    const storage = window.sessionStorage
    storage.removeItem('fudly_init_data')
    storage.removeItem('fudly_init_data_ts')
    storage.removeItem('fudly_last_user_id')
    clearKey(storage, 'fudly_cart_v2')
    clearKey(storage, 'fudly_favorites')
    clearKey(storage, 'fudly_pending_payment')
    clearByPrefix(storage, 'fudly_cart_user_')
    clearByPrefix(storage, 'fudly_favorites_user_')
    clearByPrefix(storage, 'fudly_pending_payment_user_')
    if (userId) {
      storage.removeItem(`fudly_init_data_${userId}`)
      storage.removeItem(`fudly_init_data_ts_${userId}`)
    }
  } catch {
    // ignore storage errors
  }

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

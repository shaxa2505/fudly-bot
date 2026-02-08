import { getUserId } from './auth'

const STORAGE_KEY = 'fudly_pending_payment'
const STORAGE_PREFIX = 'fudly_pending_payment_user_'
const PENDING_TTL_MS = 48 * 60 * 60 * 1000

const getStorageKeys = () => {
  const userId = getUserId()
  const primaryKey = userId ? `${STORAGE_PREFIX}${userId}` : STORAGE_KEY
  const fallbackKey = userId ? STORAGE_KEY : null
  return { userId, primaryKey, fallbackKey }
}

const normalizePendingPayment = (parsed) => {
  if (!parsed || typeof parsed !== 'object') return null
  const createdAt = Number(
    parsed.createdAt ||
    parsed.created_at ||
    parsed.timestamp ||
    0
  )
  return {
    orderId: Number(parsed.orderId || parsed.order_id || 0) || null,
    storeId: parsed.storeId ?? parsed.store_id ?? null,
    total: parsed.total ?? parsed.amount ?? null,
    provider: parsed.provider || 'click',
    cart: parsed.cart || parsed.cartSnapshot || null,
    createdAt: createdAt || Date.now(),
    updatedAt: Number(parsed.updatedAt || parsed.updated_at || createdAt || Date.now()),
  }
}

export const readPendingPayment = () => {
  try {
    const { userId, primaryKey, fallbackKey } = getStorageKeys()
    let raw = localStorage.getItem(primaryKey)
    let sourceKey = primaryKey

    if (!raw && fallbackKey) {
      raw = localStorage.getItem(fallbackKey)
      sourceKey = fallbackKey
    }

    if (!raw) return null

    const parsed = JSON.parse(raw)
    const normalized = normalizePendingPayment(parsed)
    if (!normalized) return null

    if (normalized.createdAt && Date.now() - normalized.createdAt > PENDING_TTL_MS) {
      localStorage.removeItem(sourceKey)
      return null
    }

    if (fallbackKey && sourceKey === fallbackKey && userId) {
      try {
        localStorage.setItem(primaryKey, JSON.stringify({
          ...normalized,
          updatedAt: Date.now(),
        }))
        localStorage.removeItem(fallbackKey)
      } catch {
        // ignore storage errors
      }
    }

    return normalized
  } catch {
    return null
  }
}

export const savePendingPayment = (payload) => {
  if (!payload) return null
  const { userId, primaryKey, fallbackKey } = getStorageKeys()
  const createdAt = Number(payload.createdAt || payload.created_at || Date.now())
  const normalized = {
    orderId: payload.orderId || payload.order_id || null,
    storeId: payload.storeId ?? payload.store_id ?? null,
    total: payload.total ?? payload.amount ?? null,
    provider: payload.provider || 'click',
    cart: payload.cart || payload.cartSnapshot || null,
    createdAt,
    updatedAt: Date.now(),
  }
  try {
    localStorage.setItem(primaryKey, JSON.stringify(normalized))
    if (userId && fallbackKey) {
      localStorage.removeItem(fallbackKey)
    }
  } catch {
    // ignore storage errors
  }
  return normalized
}

export const clearPendingPayment = () => {
  try {
    const { primaryKey, fallbackKey } = getStorageKeys()
    localStorage.removeItem(primaryKey)
    if (fallbackKey && fallbackKey !== primaryKey) {
      localStorage.removeItem(fallbackKey)
    }
  } catch {
    // ignore storage errors
  }
}

export default {
  readPendingPayment,
  savePendingPayment,
  clearPendingPayment,
}

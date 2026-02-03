import { getUserId } from './auth'

const STORAGE_KEY = 'fudly_pending_payment'
const STORAGE_PREFIX = 'fudly_pending_payment_user_'
const PENDING_TTL_MS = 48 * 60 * 60 * 1000

const getStorageKey = () => {
  const userId = getUserId()
  if (userId) {
    return `${STORAGE_PREFIX}${userId}`
  }
  return STORAGE_KEY
}

export const readPendingPayment = () => {
  try {
    const storageKey = getStorageKey()
    const raw = localStorage.getItem(storageKey)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return null

    const createdAt = Number(
      parsed.createdAt ||
      parsed.created_at ||
      parsed.timestamp ||
      0
    )
    if (createdAt && Date.now() - createdAt > PENDING_TTL_MS) {
      localStorage.removeItem(storageKey)
      return null
    }

    return {
      orderId: Number(parsed.orderId || parsed.order_id || 0) || null,
      storeId: parsed.storeId ?? parsed.store_id ?? null,
      total: parsed.total ?? parsed.amount ?? null,
      provider: parsed.provider || 'click',
      cart: parsed.cart || parsed.cartSnapshot || null,
      createdAt: createdAt || Date.now(),
      updatedAt: Number(parsed.updatedAt || parsed.updated_at || createdAt || Date.now()),
    }
  } catch {
    return null
  }
}

export const savePendingPayment = (payload) => {
  if (!payload) return null
  const storageKey = getStorageKey()
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
    localStorage.setItem(storageKey, JSON.stringify(normalized))
  } catch {
    // ignore storage errors
  }
  return normalized
}

export const clearPendingPayment = () => {
  try {
    localStorage.removeItem(getStorageKey())
  } catch {
    // ignore storage errors
  }
}

export default {
  readPendingPayment,
  savePendingPayment,
  clearPendingPayment,
}

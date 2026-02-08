export const normalizeOrderStatus = (status) => {
  if (!status) return 'pending'
  const normalized = String(status).trim().toLowerCase()
  if (normalized === 'confirmed') return 'preparing'
  if (normalized === 'active') return 'pending'
  return normalized
}

export const normalizePaymentStatus = (status, paymentMethod = null) => {
  if (status == null) return ''
  const normalized = String(status).trim().toLowerCase()
  if (!normalized) return ''
  if (normalized === 'paid') return 'confirmed'
  if (normalized === 'payment_rejected') return 'rejected'
  if (normalized === 'pending') {
    const method = paymentMethod ? String(paymentMethod).trim().toLowerCase() : ''
    if (method === 'cash') return 'not_required'
    return 'awaiting_payment'
  }
  return normalized
}

export const isPaymentPending = (status) => (
  ['awaiting_payment', 'awaiting_proof', 'proof_submitted'].includes(status)
)

export const isPaymentSettled = (status) => (
  ['confirmed', 'not_required'].includes(status)
)

export const resolveOrderType = (order) => {
  const rawType = order?.order_type
  if (rawType === 'pickup' || rawType === 'delivery') return rawType
  if (order?.delivery_address) return 'delivery'
  return 'pickup'
}

export const statusText = (status, lang, orderType = 'delivery') => {
  const normalized = normalizeOrderStatus(status)
  const type = orderType === 'pickup' ? 'pickup' : 'delivery'

  const pickup = {
    pending: lang === 'uz' ? 'Tasdiq kutilmoqda' : 'Ожидает подтверждения',
    preparing: lang === 'uz' ? 'Tayyorlanmoqda' : 'Готовится',
    ready: lang === 'uz' ? 'Tayyor' : 'Готов к выдаче',
    delivering: lang === 'uz' ? "Yo'lda" : 'В пути',
    completed: lang === 'uz' ? 'Berildi' : 'Выдано',
    rejected: lang === 'uz' ? 'Rad etildi' : 'Отклонён',
    cancelled: lang === 'uz' ? 'Bekor qilindi' : 'Отменён',
  }

  const delivery = {
    pending: lang === 'uz' ? 'Tasdiq kutilmoqda' : 'Ожидает подтверждения',
    preparing: lang === 'uz' ? 'Tayyorlanmoqda' : 'Готовится',
    ready: lang === 'uz' ? 'Tayyor' : 'Собран',
    delivering: lang === 'uz' ? "Yo'lda" : 'В пути',
    completed: lang === 'uz' ? 'Yetkazildi' : 'Доставлено',
    rejected: lang === 'uz' ? 'Rad etildi' : 'Отклонён',
    cancelled: lang === 'uz' ? 'Bekor qilindi' : 'Отменён',
  }

  const table = type === 'pickup' ? pickup : delivery
  return table[normalized] || normalized
}

export const paymentStatusText = (status, lang) => {
  if (!status) return null
  const normalized = String(status).trim().toLowerCase()
  const labels = {
    awaiting_payment: lang === 'uz' ? "To'lov kutilmoqda" : 'Ожидается оплата',
    awaiting_proof: lang === 'uz' ? 'Chek kutilmoqda' : 'Ожидается чек',
    proof_submitted: lang === 'uz' ? 'Tekshirilmoqda' : 'На проверке',
    rejected: lang === 'uz' ? "To'lov rad etildi" : 'Оплата отклонена',
    payment_rejected: lang === 'uz' ? "To'lov rad etildi" : 'Оплата отклонена',
    confirmed: lang === 'uz' ? "To'lov tasdiqlandi" : 'Оплата подтверждена',
    not_required: lang === 'uz' ? "To'lov talab qilinmaydi" : 'Оплата не требуется',
  }
  return labels[normalized] || null
}

export const displayStatusText = (status, lang, orderType) => {
  const paymentLabel = paymentStatusText(status, lang)
  if (paymentLabel) return paymentLabel
  return statusText(status, lang, orderType)
}

export const deriveDisplayStatus = (order) => {
  const baseStatus = normalizeOrderStatus(order?.order_status || order?.status || 'pending')
  if (['completed', 'cancelled', 'rejected'].includes(baseStatus)) {
    return baseStatus
  }
  const paymentStatus = order?.payment_status
  if (paymentStatus === 'awaiting_payment') return 'awaiting_payment'
  if (paymentStatus === 'awaiting_proof') return 'awaiting_proof'
  if (paymentStatus === 'proof_submitted') return 'proof_submitted'
  if (paymentStatus === 'rejected') return 'payment_rejected'
  if (paymentStatus === 'payment_rejected') return 'payment_rejected'
  return baseStatus || 'pending'
}

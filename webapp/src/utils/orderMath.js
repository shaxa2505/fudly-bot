const toNumber = (value, fallback = 0) => {
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : fallback
}

const defaultPrice = (item) =>
  item?.price ?? item?.discount_price ?? item?.original_price ?? 0

const defaultQuantity = (item) => item?.quantity ?? 1

export const calcItemsTotal = (items = [], options = {}) => {
  if (!Array.isArray(items) || items.length === 0) return 0
  const getPrice = typeof options.getPrice === 'function' ? options.getPrice : defaultPrice
  const getQuantity = typeof options.getQuantity === 'function'
    ? options.getQuantity
    : defaultQuantity

  return items.reduce((sum, item) => (
    sum + (toNumber(getPrice(item)) * toNumber(getQuantity(item) || 1))
  ), 0)
}

export const calcQuantity = (items = [], getQuantity) => {
  if (!Array.isArray(items) || items.length === 0) return 0
  const quantityFn = typeof getQuantity === 'function' ? getQuantity : defaultQuantity
  return items.reduce((sum, item) => sum + toNumber(quantityFn(item) || 1), 0)
}

export const calcDeliveryFee = (totalPrice, itemsTotal, options = {}) => {
  const isDelivery = options.isDelivery
  if (isDelivery === false) return 0

  const explicitFee = options.deliveryFee
  if (explicitFee !== undefined && explicitFee !== null && explicitFee !== '') {
    return Math.max(0, toNumber(explicitFee))
  }

  if (totalPrice === undefined || totalPrice === null) return 0
  return Math.max(0, toNumber(totalPrice) - toNumber(itemsTotal))
}

export const calcTotalPrice = (itemsTotal, deliveryFee, options = {}) => {
  const explicitTotal = options.totalPrice
  if (explicitTotal !== undefined && explicitTotal !== null && explicitTotal !== '') {
    return toNumber(explicitTotal)
  }
  return toNumber(itemsTotal) + toNumber(deliveryFee)
}

export default {
  calcItemsTotal,
  calcQuantity,
  calcDeliveryFee,
  calcTotalPrice,
}

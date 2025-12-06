import { memo } from 'react'

/**
 * Order summary component
 * Shows cart items, totals, delivery fee
 */
const OrderSummary = memo(function OrderSummary({
  subtotal,
  deliveryFee,
  total,
  itemsCount,
  orderType,
}) {
  const formatPrice = (price) => {
    return price.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' ')
  }

  return (
    <div className="order-summary">
      <h3 className="summary-title">📊 Buyurtma tafsilotlari</h3>

      <div className="summary-row">
        <span className="summary-label">Mahsulotlar ({itemsCount} ta):</span>
        <span className="summary-value">{formatPrice(subtotal)} so'm</span>
      </div>

      {orderType === 'delivery' && deliveryFee > 0 && (
        <div className="summary-row">
          <span className="summary-label">🚚 Yetkazib berish:</span>
          <span className="summary-value">{formatPrice(deliveryFee)} so'm</span>
        </div>
      )}

      <div className="summary-divider"></div>

      <div className="summary-row summary-total">
        <span className="summary-label">Jami to'lov:</span>
        <span className="summary-value highlight">{formatPrice(total)} so'm</span>
      </div>

      {orderType === 'pickup' && (
        <div className="summary-note">
          💡 Do'kondan olib ketishda to'lov amalga oshiriladi
        </div>
      )}

      {orderType === 'delivery' && (
        <div className="summary-note">
          💡 Yetkazib berganda to'lov amalga oshiriladi
        </div>
      )}
    </div>
  )
})

export default OrderSummary

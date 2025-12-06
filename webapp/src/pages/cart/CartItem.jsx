import { memo } from 'react'

/**
 * Cart item component
 * Shows single cart item with quantity controls
 */
const CartItem = memo(function CartItem({
  item,
  onIncrement,
  onDecrement,
  onRemove,
}) {
  const { offer, quantity } = item

  const formatPrice = (price) => {
    return price.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' ')
  }

  const itemTotal = (offer.discount_price || 0) * quantity

  const stockLimit = offer.stock || offer.quantity || 99
  const isMaxReached = quantity >= stockLimit

  return (
    <div className="cart-item">
      {/* Image */}
      <div className="cart-item-image">
        {offer.photo ? (
          <img src={offer.photo} alt={offer.title} />
        ) : (
          <div className="cart-item-placeholder">📦</div>
        )}
      </div>

      {/* Info */}
      <div className="cart-item-info">
        <h4 className="cart-item-title">{offer.title}</h4>
        <p className="cart-item-store">{offer.store_name}</p>
        
        <div className="cart-item-price">
          <span className="price-current">{formatPrice(offer.discount_price)} so'm</span>
          {offer.original_price > offer.discount_price && (
            <span className="price-original">{formatPrice(offer.original_price)} so'm</span>
          )}
        </div>

        <div className="cart-item-total">
          Jami: <strong>{formatPrice(itemTotal)} so'm</strong>
        </div>
      </div>

      {/* Quantity Controls */}
      <div className="cart-item-controls">
        <button
          className="qty-btn qty-minus"
          onClick={() => onDecrement(offer.id)}
          aria-label="Kamaytirish"
        >
          −
        </button>
        
        <span className="qty-value">{quantity}</span>
        
        <button
          className="qty-btn qty-plus"
          onClick={() => onIncrement(offer.id)}
          disabled={isMaxReached}
          aria-label="Ko'paytirish"
          title={isMaxReached ? `Maksimal miqdor: ${stockLimit}` : ''}
        >
          +
        </button>
      </div>

      {/* Remove Button */}
      <button
        className="cart-item-remove"
        onClick={() => onRemove(offer.id)}
        aria-label="O'chirish"
      >
        🗑️
      </button>
    </div>
  )
}, (prevProps, nextProps) => {
  // Custom comparison for memo optimization
  return (
    prevProps.item.offer.id === nextProps.item.offer.id &&
    prevProps.item.quantity === nextProps.item.quantity
  )
})

export default CartItem

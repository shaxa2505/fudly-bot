import { memo, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { PLACEHOLDER_IMAGE, resolveOfferImageUrl } from '../utils/imageUtils'
import QuantityControl from './QuantityControl'
import './OfferCard.css'

const OfferCard = memo(function OfferCard({ offer, cartQuantity = 0, onAddToCart, onRemoveFromCart }) {
  const navigate = useNavigate()
  const [imageLoaded, setImageLoaded] = useState(false)
  const [imageError, setImageError] = useState(false)
  const [isAdding, setIsAdding] = useState(false)

  const handleCardClick = () => {
    navigate('/product', { state: { offer } })
  }

  // Get stock limit from offer
  const stockLimit = Number(offer.quantity ?? offer.stock ?? 0)
  const isOutOfStock = stockLimit <= 0
  const isMaxReached = !isOutOfStock && cartQuantity >= stockLimit
  const disableIncrement = isOutOfStock || isMaxReached
  const minOrderAmount = Number(offer.min_order_amount || 0)
  const showDelivery = Boolean(offer.delivery_enabled)
  const showStoreName = Boolean(offer.store_name)

  const handleAddClick = useCallback((e) => {
    e.stopPropagation()
    if (isOutOfStock || isMaxReached) {
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('warning')
      return
    }

    // Haptic feedback
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light')

    // Add animation
    setIsAdding(true)
    setTimeout(() => setIsAdding(false), 300)

    onAddToCart?.(offer)
  }, [isOutOfStock, isMaxReached, offer, onAddToCart])

  const handleRemoveClick = useCallback((e) => {
    e.stopPropagation()
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light')
    onRemoveFromCart?.(offer)
  }, [offer, onRemoveFromCart])

  const originalPrice = Number(offer.original_price) || 0
  const discountPrice = Number(offer.discount_price) || 0
  const priceValue = discountPrice || originalPrice
  const hasDiscount = originalPrice > discountPrice && discountPrice > 0
  const computedPercent = hasDiscount && originalPrice > 0
    ? Math.round((1 - discountPrice / originalPrice) * 100)
    : 0
  const rawDiscountPercent = Number(offer.discount_percent) || 0
  const discountPercent = rawDiscountPercent || computedPercent
  const showDiscountPercent = discountPercent > 0 && (hasDiscount || rawDiscountPercent > 0)
  const isFrozen = Boolean(offer.is_frozen) || String(offer.category || '').toLowerCase() === 'frozen'

  // Get photo URL (handles Telegram file_id conversion)
  const photoUrl = resolveOfferImageUrl(offer)
  const fallbackUrl = PLACEHOLDER_IMAGE

  return (
    <div
      className={`offer-card ${cartQuantity > 0 ? 'in-cart' : ''} ${isAdding ? 'adding' : ''} ${isOutOfStock ? 'out-of-stock' : ''}`}
      onClick={handleCardClick}
    >
      {/* Image Section */}
      <div className={`card-image-container ${imageLoaded && !imageError ? 'has-image' : ''}`}>
        {/* Image skeleton while loading */}
        {!imageLoaded && !imageError && (
          <div className="image-skeleton shimmer" />
        )}
        {showDiscountPercent && (
          <div className="image-discount-badge">-{discountPercent}%</div>
        )}
        {isOutOfStock && (
          <div className="image-stock-badge">Tugagan</div>
        )}

        <img
          src={photoUrl || fallbackUrl}
          alt={offer.title}
          className={`card-image ${imageLoaded ? 'loaded' : ''}`}
          loading="lazy"
          decoding="async"
          onLoad={() => setImageLoaded(true)}
          onError={(e) => {
            if (!e.target.dataset.fallback) {
              e.target.dataset.fallback = 'true'
              e.target.src = fallbackUrl
              setImageError(true)
              setImageLoaded(true)
            }
          }}
        />
      </div>

      {/* Content Section */}
      <div className="card-content">
        <div className="price-row">
          <div className="price-stack">
            <div className="price-line">
              <div className={`price-main ${hasDiscount ? 'discounted' : ''}`}>
                {Math.round(priceValue).toLocaleString('ru-RU')}
                <span className="currency"> so'm</span>
              </div>
            </div>
            {hasDiscount && (
              <div className="price-original">
                {Math.round(originalPrice).toLocaleString('ru-RU')} so'm
              </div>
            )}
          </div>
        </div>
        <h3 className="offer-title">
          {offer.title}
          {isFrozen && (
            <span className="offer-title-tag"> - Muzlatilgan</span>
          )}
        </h3>
        {(showStoreName || showDelivery) && (
          <div className="offer-meta">
            {showStoreName && (
              <span className="offer-store">{offer.store_name}</span>
            )}
            {showDelivery && (
              <span className="offer-badge">Yetkazib berish</span>
            )}
            {showDelivery && minOrderAmount > 0 && (
              <span className="offer-badge secondary">
                Min {Math.round(minOrderAmount).toLocaleString('ru-RU')} so'm
              </span>
            )}
          </div>
        )}
        <div className="card-control">
          {cartQuantity > 0 ? (
            <QuantityControl
              value={cartQuantity}
              size="sm"
              className="card-stepper"
              onDecrement={handleRemoveClick}
              onIncrement={handleAddClick}
              disableIncrement={disableIncrement}
              stopPropagation
            />
          ) : isOutOfStock ? (
            <div className="card-stock-empty">Tugagan</div>
          ) : (
            <button
              type="button"
              className={`add-to-cart-inline ${isAdding ? 'pulse' : ''}`}
              onClick={handleAddClick}
              disabled={disableIncrement}
              aria-label="Savatga qo'shish"
            >
              +
            </button>
          )}
        </div>
      </div>
    </div>
  )
})

export default OfferCard

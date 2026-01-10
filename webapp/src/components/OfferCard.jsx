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
  const stockLimit = offer.quantity || offer.stock || 99
  const isMaxReached = cartQuantity >= stockLimit

  const handleAddClick = useCallback((e) => {
    e.stopPropagation()
    if (isMaxReached) {
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('warning')
      return
    }

    // Haptic feedback
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light')

    // Add animation
    setIsAdding(true)
    setTimeout(() => setIsAdding(false), 300)

    onAddToCart?.(offer)
  }, [isMaxReached, offer, onAddToCart])

  const handleRemoveClick = useCallback((e) => {
    e.stopPropagation()
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light')
    onRemoveFromCart?.(offer)
  }, [offer, onRemoveFromCart])

  const discountPercent = Math.round(offer.discount_percent ||
    ((offer.original_price - offer.discount_price) / offer.original_price * 100))
  const hasDiscount = offer.original_price > offer.discount_price
  const isFrozen = Boolean(offer.is_frozen) || String(offer.category || '').toLowerCase() === 'frozen'

  // Get photo URL (handles Telegram file_id conversion)
  const photoUrl = resolveOfferImageUrl(offer)
  const fallbackUrl = PLACEHOLDER_IMAGE

  return (
    <div className={`offer-card ${cartQuantity > 0 ? 'in-cart' : ''} ${isAdding ? 'adding' : ''}`} onClick={handleCardClick}>
      {/* Image Section */}
      <div className={`card-image-container ${imageLoaded && !imageError ? 'has-image' : ''}`}>
        {/* Discount Badge */}
        {discountPercent > 0 && (
          <div className="discount-badge">-{discountPercent}%</div>
        )}
        {/* Image skeleton while loading */}
        {!imageLoaded && !imageError && (
          <div className="image-skeleton shimmer" />
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

        {/* Add/Quantity Control */}
        <div className={`card-action ${cartQuantity > 0 ? 'is-qty' : 'is-add'}`}>
          {cartQuantity > 0 ? (
            <QuantityControl
              value={cartQuantity}
              size="sm"
              onDecrement={handleRemoveClick}
              onIncrement={handleAddClick}
              disableIncrement={isMaxReached}
              stopPropagation
            />
          ) : (
            <button
              className={`add-to-cart-fab add-to-cart-btn ${isAdding ? 'pulse' : ''}`}
              onClick={handleAddClick}
              aria-label="Savatga qo'shish"
            >
              <span aria-hidden="true">+</span>
            </button>
          )}
        </div>
      </div>

      {/* Content Section */}
      <div className="card-content">
        <div className="price-section">
          <div className={`price-main ${hasDiscount ? 'discounted' : ''}`}>
            {Math.round(offer.discount_price).toLocaleString('ru-RU')}
            <span className="currency"> so'm</span>
          </div>
          {hasDiscount && (
            <div className="price-original">
              {Math.round(offer.original_price).toLocaleString('ru-RU')} so'm
            </div>
          )}
        </div>
        <h3 className="offer-title">{offer.title}</h3>
        {isFrozen && (
          <div className="offer-tag">
            <span className="offer-tag-icon" aria-hidden="true">*</span>
            <span>Muzlatkichdan</span>
          </div>
        )}
      </div>
    </div>
  )
})

export default OfferCard

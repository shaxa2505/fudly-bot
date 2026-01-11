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

  const originalPrice = Number(offer.original_price) || 0
  const discountPrice = Number(offer.discount_price) || 0
  const priceValue = discountPrice || originalPrice
  const hasDiscount = originalPrice > discountPrice && discountPrice > 0
  const computedPercent = hasDiscount && originalPrice > 0
    ? Math.round((1 - discountPrice / originalPrice) * 100)
    : 0
  const discountPercent = Number(offer.discount_percent) || computedPercent
  const showPercentOnly = !hasDiscount && discountPercent > 0
  const isFrozen = Boolean(offer.is_frozen) || String(offer.category || '').toLowerCase() === 'frozen'

  // Get photo URL (handles Telegram file_id conversion)
  const photoUrl = resolveOfferImageUrl(offer)
  const fallbackUrl = PLACEHOLDER_IMAGE

  return (
    <div className={`offer-card ${cartQuantity > 0 ? 'in-cart' : ''} ${isAdding ? 'adding' : ''}`} onClick={handleCardClick}>
      {/* Image Section */}
      <div className={`card-image-container ${imageLoaded && !imageError ? 'has-image' : ''}`}>
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
      </div>

      {/* Content Section */}
      <div className="card-content">
        <div className="price-section">
          <div className="price-row">
            <div className={`price-main ${hasDiscount ? 'discounted' : ''}`}>
              {Math.round(priceValue).toLocaleString('ru-RU')}
              <span className="currency"> so'm</span>
            </div>
            {showPercentOnly && (
              <span className="price-discount">-{discountPercent}%</span>
            )}
          </div>
          {hasDiscount && (
            <div className="price-original">
              {Math.round(originalPrice).toLocaleString('ru-RU')} so'm
            </div>
          )}
        </div>
        <h3 className="offer-title">{offer.title}</h3>
        <div className="card-footer">
          {isFrozen && (
            <span className="offer-tag">Muzlatilgan</span>
          )}
          {cartQuantity > 0 ? (
            <QuantityControl
              value={cartQuantity}
              size="sm"
              className="card-stepper"
              onDecrement={handleRemoveClick}
              onIncrement={handleAddClick}
              disableIncrement={isMaxReached}
              stopPropagation
            />
          ) : (
            <button
              className={`add-to-cart-inline ${isAdding ? 'pulse' : ''}`}
              onClick={handleAddClick}
              aria-label="Savatga qo'shish"
            >
              Qo'shish
            </button>
          )}
        </div>
      </div>
    </div>
  )
})

export default OfferCard

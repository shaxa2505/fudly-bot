import { memo, useState, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useFavorites } from '../context/FavoritesContext'
import { getUnitLabel } from '../utils/helpers'
import api from '../api/client'
import './OfferCardNew.css'

const OfferCard = memo(function OfferCard({ offer, cartQuantity = 0, onAddToCart, onRemoveFromCart }) {
  const navigate = useNavigate()
  const { isFavorite, toggleFavorite } = useFavorites()
  const [imageLoaded, setImageLoaded] = useState(false)
  const [imageError, setImageError] = useState(false)
  const [isAdding, setIsAdding] = useState(false)

  const isInFavorites = isFavorite(offer.id)

  const handleCardClick = () => {
    const productPath = offer?.id ? `/product/${offer.id}` : '/product'
    navigate(productPath, { state: { offer } })
  }

  // Get stock limit from offer
  const stockLimit = offer.quantity || offer.stock || 99
  const isMaxReached = cartQuantity >= stockLimit

  // Stock progress calculation
  const stockProgress = useMemo(() => {
    const maxStock = Math.max(10, Math.min(100, stockLimit))
    const current = stockLimit
    const percent = Math.min(100, Math.round((current / maxStock) * 100))
    let level = 'high'
    if (current <= 5) level = 'low'
    else if (current <= 15) level = 'medium'
    return { percent, level, current }
  }, [stockLimit])

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

  const handleFavoriteClick = useCallback((e) => {
    e.stopPropagation()
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('medium')
    toggleFavorite(offer)
  }, [offer, toggleFavorite])

  const hasPriceData = offer.original_price > 0 && offer.discount_price > 0
  const discountPercent = offer.discount_percent != null
    ? Math.round(offer.discount_percent)
    : hasPriceData
      ? Math.max(0, Math.round((1 - offer.discount_price / offer.original_price) * 100))
      : 0

  const formatExpiry = (date) => {
    if (!date) return null
    const d = new Date(date)
    const now = new Date()
    const diffDays = Math.ceil((d - now) / (1000 * 60 * 60 * 24))
    if (diffDays <= 0) return null
    if (diffDays <= 3) return `${diffDays} kun`
    if (diffDays <= 7) return `${diffDays} kun`
    return null
  }

  const expiryText = formatExpiry(offer.expiry_date)

  const storeName = offer.store_name || offer.store?.name || offer.storeName || ''
  const storeAddress = offer.store_address || offer.store?.address || offer.address || ''
  const showStoreMeta = Boolean(storeName || storeAddress)

  // Get photo URL (handles Telegram file_id conversion) and also image_url field
  const photoUrl = api.getPhotoUrl(offer.image_url || offer.photo)
  // Better placeholder with dynamic initial
  const fallbackInitial = encodeURIComponent((offer.title?.[0] || 'F').toUpperCase())
  const fallbackUrl = `https://placehold.co/300x300/F0F4F8/C1CBD8?text=${fallbackInitial}`

  return (
    <div className={`card card--product ${cartQuantity > 0 ? 'in-cart' : ''} ${isAdding ? 'adding' : ''}`} onClick={handleCardClick}>
      {/* Image Section */}
      <div className="card__image">
        {/* Discount Badge */}
        {discountPercent > 0 && (
          <span className="badge--percentage">-{discountPercent}%</span>
        )}

        {/* Image skeleton while loading */}
        {!imageLoaded && !imageError && (
          <div className="skeleton skeleton--image animate-shimmer" />
        )}

        <img
          src={photoUrl || fallbackUrl}
          alt={offer.title}
          className={imageLoaded ? 'loaded' : ''}
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
      <div className="card__content">
        <h3 className="card__title">{offer.title}</h3>

        {/* Rating */}
        <div className="card__rating">
          <span className="card__rating-star">⭐</span>
          <span>{offer.rating || '4.8'}</span>
        </div>

        {/* Prices */}
        <div className="card__price">
          <span className="card__price-current">
            {Math.round(offer.discount_price).toLocaleString('ru-RU')} so'm
          </span>
          {offer.original_price > offer.discount_price && (
            <span className="card__price-old">
              {Math.round(offer.original_price).toLocaleString('ru-RU')}
            </span>
          )}
        </div>
      </div>

      {/* Add to Cart CTA - Circle Button */}
      {cartQuantity > 0 ? (
        <div className="card__quantity">
          <button className="card__quantity-btn" onClick={handleRemoveClick}>−</button>
          <span className="card__quantity-value">{cartQuantity}</span>
          <button
            className={`card__quantity-btn ${isMaxReached ? 'disabled' : ''}`}
            onClick={handleAddClick}
            disabled={isMaxReached}
          >+</button>
        </div>
      ) : (
        <button className={`card__cta ${isAdding ? 'adding' : ''}`} onClick={handleAddClick}>
          +
        </button>
      )}
    </div>
  )
})

export default OfferCard

import { memo, useState, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useFavorites } from '../context/FavoritesContext'
import { getUnitLabel } from '../utils/helpers'
import api from '../api/client'
import './OfferCard.css'

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

  // Get photo URL (handles Telegram file_id conversion) and also image_url field
  const photoUrl = api.getPhotoUrl(offer.image_url || offer.photo)
  // Better placeholder with product icon
  const fallbackUrl = 'https://placehold.co/300x300/F8F9FA/CBD5E1?text=🛒'

  return (
    <div className={`offer-card ${cartQuantity > 0 ? 'in-cart' : ''} ${isAdding ? 'adding' : ''}`} onClick={handleCardClick}>
      {/* Image Section */}
      <div className="card-image-container">
        {/* Discount Badge */}
        {discountPercent > 0 && (
          <div className="discount-badge">-{discountPercent}%</div>
        )}

        {/* Favorite Button */}
        <button
          className={`favorite-btn ${isInFavorites ? 'active' : ''}`}
          onClick={handleFavoriteClick}
          aria-label={isInFavorites ? "Sevimlilardan o'chirish" : "Sevimlilarga qo'shish"}
        >
          {isInFavorites ? (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="#E53935">
              <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>
            </svg>
          ) : (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#999" strokeWidth="2">
              <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>
            </svg>
          )}
        </button>

        {/* Expiry Badge */}
        {expiryText && (
          <div className="expiry-badge">⏰ {expiryText}</div>
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
        <h3 className="offer-title">{offer.title}</h3>

        {/* Stock Progress Bar */}
        {stockLimit < 99 && (
          <div className="stock-progress">
            <div className="stock-progress-bar">
              <div
                className={`stock-progress-fill ${stockProgress.level}`}
                style={{ width: `${stockProgress.percent}%` }}
              />
            </div>
            <div className={`stock-label ${stockProgress.level === 'low' ? 'low' : ''}`}>
              <span>{stockProgress.level === 'low' ? '🔥 Tez tugaydi!' : 'Qoldi'}</span>
              <span>{stockProgress.current} {getUnitLabel(offer.unit)}</span>
            </div>
          </div>
        )}

        {/* Prices */}
        <div className="price-section">
          <div className="price-main">
            {Math.round(offer.discount_price).toLocaleString('ru-RU')}
            <span className="currency"> so'm</span>
          </div>
          {offer.original_price > offer.discount_price && (
            <div className="price-original">
              {Math.round(offer.original_price).toLocaleString('ru-RU')}
            </div>
          )}
        </div>

        {/* Add to Cart Button */}
        <div className="cart-action">
          {cartQuantity > 0 ? (
            <div className="quantity-control">
              <button className="qty-btn" onClick={handleRemoveClick}>−</button>
              <span className="qty-num">{cartQuantity}{stockLimit < 99 ? `/${stockLimit}` : ''}</span>
              <button
                className={`qty-btn qty-plus ${isMaxReached ? 'disabled' : ''}`}
                onClick={handleAddClick}
                disabled={isMaxReached}
              >+</button>
            </div>
          ) : (
            <button className={`add-to-cart-btn ${isAdding ? 'pulse' : ''}`} onClick={handleAddClick}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                <path d="M12 5v14M5 12h14" stroke="white" strokeWidth="2.5" strokeLinecap="round"/>
              </svg>
            </button>
          )}
        </div>
      </div>
    </div>
  )
})

export default OfferCard

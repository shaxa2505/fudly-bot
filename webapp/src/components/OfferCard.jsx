import { memo, useState, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { Heart, Clock } from 'lucide-react'
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
    navigate('/product', { state: { offer } })
  }

  // Get stock limit from offer
  const stockLimit = offer.quantity || offer.stock || 99
  const isMaxReached = cartQuantity >= stockLimit

  // Stock progress calculation
  const stockProgress = useMemo(() => {
    const maxStock = 50 // Assume 50 is "full stock" for visual purposes
    const current = stockLimit
    const percent = Math.min(100, (current / maxStock) * 100)
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

    // Optimistic update - update UI immediately
    toggleFavorite(offer)

    // Sync with backend in background
    const userId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id
    if (userId) {
      const isCurrentlyFavorite = isFavorite(offer.id)
      const apiCall = isCurrentlyFavorite ? api.removeFavorite : api.addFavorite

      apiCall(offer.id).catch((error) => {
        // Rollback on error
        console.error('Failed to sync favorite:', error)
        toggleFavorite(offer)
        window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('error')
      })
    }
  }, [offer, toggleFavorite, isFavorite])

  const discountPercent = Math.round(offer.discount_percent ||
    ((offer.original_price - offer.discount_price) / offer.original_price * 100))

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

  // Get photo URL (handles Telegram file_id conversion)
  const photoUrl = api.getPhotoUrl(offer.photo)
  const fallbackUrl = 'https://placehold.co/300x300/F5F5F5/CCCCCC?text=📷'

  return (
    <div className={`offer-card ${cartQuantity > 0 ? 'in-cart' : ''} ${isAdding ? 'adding' : ''}`} onClick={handleCardClick}>
      {/* Image Section */}
      <div className={`card-image-container ${imageLoaded && !imageError ? 'has-image' : ''}`}>
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
          <Heart
            size={20}
            fill={isInFavorites ? '#E53935' : 'none'}
            color={isInFavorites ? '#E53935' : '#999'}
            strokeWidth={2}
          />
        </button>

        {/* Expiry Badge */}
        {expiryText && (
          <div className="expiry-badge">
            <Clock size={14} strokeWidth={2} aria-hidden="true" />
            <span>{expiryText}</span>
          </div>
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
        {offer.store_name && <span className="store-name">{offer.store_name}</span>}
        <h3 className="offer-title">{offer.title}</h3>

        {/* Stock Progress Bar */}
        {stockLimit < 50 && (
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
            {Math.round(offer.discount_price / 100).toLocaleString('ru-RU')}
            <span className="currency"> so'm</span>
          </div>
          {offer.original_price > offer.discount_price && (
            <div className="price-original">
              {Math.round(offer.original_price / 100).toLocaleString('ru-RU')}
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

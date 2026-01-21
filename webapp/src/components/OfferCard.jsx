import { memo, useState, useCallback, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useToast } from '../context/ToastContext'
import { PLACEHOLDER_IMAGE, resolveOfferImageUrl } from '../utils/imageUtils'
import './OfferCard.css'

const LOADED_IMAGE_CACHE = new Set()

const OfferCard = memo(function OfferCard({
  offer,
  cartQuantity = 0,
  onAddToCart,
  onRemoveFromCart,
  imagePriority = false,
}) {
  const navigate = useNavigate()
  const { toast } = useToast()
  const [isAdding, setIsAdding] = useState(false)

  // Get photo URL (handles Telegram file_id conversion)
  const photoUrl = resolveOfferImageUrl(offer)
  const fallbackUrl = PLACEHOLDER_IMAGE
  const resolvedUrl = photoUrl || fallbackUrl
  const [imageLoaded, setImageLoaded] = useState(() => LOADED_IMAGE_CACHE.has(resolvedUrl))
  const [imageError, setImageError] = useState(false)

  useEffect(() => {
    setImageError(false)
    setImageLoaded(LOADED_IMAGE_CACHE.has(resolvedUrl))
  }, [resolvedUrl])

  const handleCardClick = () => {
    navigate('/product', { state: { offer } })
  }

  // Get stock limit from offer
  const stockLimit = Number(offer.quantity ?? offer.stock ?? 0)
  const isOutOfStock = stockLimit <= 0
  const isMaxReached = !isOutOfStock && cartQuantity >= stockLimit
  const storeName = offer.store_name || offer.store || ''

  const handleAddClick = useCallback((e) => {
    e.stopPropagation()
    if (isOutOfStock || isMaxReached) {
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('warning')
      return
    }

    // Haptic feedback
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light')

    onAddToCart?.(offer)
    if (cartQuantity === 0) {
      setIsAdding(true)
      setTimeout(() => setIsAdding(false), 300)
      toast?.success("Savatga qo'shildi", 1800)
    }
  }, [cartQuantity, isOutOfStock, isMaxReached, offer, onAddToCart, toast])

  const handleRemoveClick = useCallback((e) => {
    e.stopPropagation()
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light')
    onRemoveFromCart?.(offer)
  }, [offer, onRemoveFromCart])

  const originalPrice = Number(offer.original_price) || 0
  const discountPrice = Number(offer.discount_price) || 0
  const priceValue = discountPrice > 0 ? discountPrice : originalPrice
  const hasOldPrice = originalPrice > priceValue && priceValue > 0
  const isLowStock = !isOutOfStock && stockLimit > 0 && stockLimit <= 5
  const locationText = offer.store_address || offer.address || offer.district || offer.region || ''

  const formatTime = (value) => {
    if (!value) return ''
    const raw = String(value).trim()
    if (!raw) return ''
    const timePart = raw.includes('T') ? raw.split('T')[1] : raw
    const match = timePart.match(/\d{2}:\d{2}/)
    return match ? match[0] : timePart
  }

  const timeFrom = formatTime(offer.available_from)
  const timeUntil = formatTime(offer.available_until)
  const timeRange = timeFrom && timeUntil ? `${timeFrom} - ${timeUntil}` : ''
  const titleText = offer.title || storeName || 'Mahsulot'
  const ratingValue = Number(offer.rating ?? offer.rating_avg ?? offer.store_rating ?? 0)
  const ratingCount = Number(offer.reviews_count ?? offer.review_count ?? offer.total_reviews ?? 0)
  const showRating = Number.isFinite(ratingValue) && ratingValue > 0
  const ratingText = showRating ? ratingValue.toFixed(1) : ''
  const ratingCountLabel = ratingCount > 0
    ? `(${ratingCount}${ratingCount >= 100 ? '+' : ''})`
    : ''
  const showStoreName = Boolean(
    storeName &&
    storeName !== titleText &&
    !showRating &&
    !locationText
  )

  const handleFavoriteClick = useCallback((e) => {
    e.stopPropagation()
  }, [])

  return (
    <div
      className={`offer-card ${cartQuantity > 0 ? 'in-cart' : ''} ${isOutOfStock ? 'out-of-stock' : ''}`}
      onClick={handleCardClick}
    >
      <div className="offer-media">
        <div className="offer-image-wrap">
          {!imageLoaded && !imageError && (
            <div className="offer-image-skeleton shimmer" />
          )}
          <img
            src={resolvedUrl}
            alt={titleText}
            className={`offer-image ${imageLoaded ? 'loaded' : ''}`}
            loading={imagePriority ? 'eager' : 'lazy'}
            fetchPriority={imagePriority ? 'high' : 'auto'}
            decoding="async"
            onLoad={() => {
              LOADED_IMAGE_CACHE.add(resolvedUrl)
              setImageLoaded(true)
            }}
            onError={(e) => {
              if (!e.target.dataset.fallback) {
                e.target.dataset.fallback = 'true'
                e.target.src = fallbackUrl
                setImageError(true)
                LOADED_IMAGE_CACHE.add(fallbackUrl)
                setImageLoaded(true)
              }
            }}
          />
          <div className="offer-tags">
            {timeRange && (
              <span className="offer-tag">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2"/>
                  <path d="M12 7v5l3 2" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                </svg>
                {timeRange}
              </span>
            )}
            {isLowStock && (
              <span className="offer-tag offer-tag--alert">Kam qoldi</span>
            )}
          </div>
          <button
            type="button"
            className="offer-favorite"
            onClick={handleFavoriteClick}
            aria-label="Sevimlilarga qo'shish"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M12 21s-7-4.35-7-10a4 4 0 017-2.4A4 4 0 0119 11c0 5.65-7 10-7 10z" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
          {isOutOfStock && (
            <div className="offer-stock-overlay">Mavjud emas</div>
          )}
        </div>
        <div className="offer-body">
          <div className="offer-top-row">
            <div className="offer-title-block">
              <h3 className="offer-title" title={titleText}>{titleText}</h3>
              {locationText && (
                <div className="offer-location">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path d="M12 21s6-5.33 6-10a6 6 0 10-12 0c0 4.67 6 10 6 10z" stroke="currentColor" strokeWidth="1.6"/>
                    <circle cx="12" cy="11" r="2.5" fill="currentColor"/>
                  </svg>
                  <span>{locationText}</span>
                </div>
              )}
            </div>
            <div className="offer-price-block">
              <span className="offer-price">{Math.round(priceValue).toLocaleString('ru-RU')} so'm</span>
              {hasOldPrice && (
                <span className="offer-old-price">{Math.round(originalPrice).toLocaleString('ru-RU')} so'm</span>
              )}
            </div>
          </div>
          <div className="offer-footer">
            <div className="offer-meta-left">
              {showRating ? (
                <div className="offer-rating" aria-label={`Reyting ${ratingText}`}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                    <path d="M12 3.5l2.47 5 5.52.8-4 3.9.94 5.5L12 16.7l-4.93 2.6.94-5.5-4-3.9 5.52-.8L12 3.5z"/>
                  </svg>
                  <span className="offer-rating-value">{ratingText}</span>
                  {ratingCountLabel && (
                    <span className="offer-rating-count">{ratingCountLabel}</span>
                  )}
                </div>
              ) : (
                showStoreName && (
                  <span className="offer-store">{storeName}</span>
                )
              )}
            </div>
            <div className="offer-action">
              {cartQuantity > 0 ? (
                <div className="offer-counter" role="group" aria-label="Savat miqdori">
                  <button
                    type="button"
                    className="offer-counter-btn"
                    onClick={handleRemoveClick}
                    aria-label="Kamaytirish"
                    disabled={cartQuantity <= 0}
                  >
                    -
                  </button>
                  <span className="offer-counter-value">{cartQuantity}</span>
                  <button
                    type="button"
                    className="offer-counter-btn"
                    onClick={handleAddClick}
                    aria-label="Ko'paytirish"
                    disabled={isOutOfStock || isMaxReached}
                  >
                    +
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  className={`offer-add-btn ${isAdding ? 'pulse' : ''}`}
                  onClick={handleAddClick}
                  disabled={isOutOfStock}
                  aria-label="Savatga qo'shish"
                >
                  Savatga qo'shish
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
})

export default OfferCard

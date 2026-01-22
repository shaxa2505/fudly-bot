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
  const storeName =
    offer.store_name ||
    offer.store ||
    offer.store_title ||
    offer.storeTitle ||
    ''

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

  const pickupStart = offer.available_from ?? offer.pickup_time_start ?? offer.pickup_from ?? offer.pickup_start
  const pickupEnd = offer.available_until ?? offer.pickup_time_end ?? offer.pickup_until ?? offer.pickup_end
  const timeFrom = formatTime(pickupStart)
  const timeUntil = formatTime(pickupEnd)
  let timeRange = ''
  if (timeFrom && timeUntil) {
    timeRange = `${timeFrom} - ${timeUntil}`
  } else if (timeFrom || timeUntil) {
    timeRange = timeFrom || timeUntil
  }
  if (!timeRange && offer.pickup_time) {
    const rawPickup = String(offer.pickup_time).trim()
    const rangeMatch = rawPickup.match(/(\d{1,2}:\d{2}).*(\d{1,2}:\d{2})/)
    timeRange = rangeMatch ? `${rangeMatch[1]} - ${rangeMatch[2]}` : rawPickup
  }
  const productTitle =
    offer.title ||
    offer.product_name ||
    offer.productTitle ||
    offer.product ||
    'Mahsulot'
  const titleText = productTitle
  const showStoreName = Boolean(storeName && storeName !== titleText)
  const ratingValue = Number(
    offer.store_rating ??
    offer.rating ??
    offer.rating_avg ??
    offer.store_rating_avg ??
    offer.avg_rating ??
    offer.store_avg_rating ??
    0
  )
  const showRating = Number.isFinite(ratingValue) && ratingValue > 0
  const ratingText = showRating ? ratingValue.toFixed(1) : ''
  const showRatingLocation = Boolean(showRating && locationText)
  const priceLabel = priceValue > 0
    ? `${Math.round(priceValue).toLocaleString('ru-RU')} so'm`
    : ''
  const oldPriceLabel = hasOldPrice
    ? Math.round(originalPrice).toLocaleString('ru-RU')
    : ''

  const handleFavoriteClick = useCallback((e) => {
    e.stopPropagation()
  }, [])

  return (
    <div
      className={`offer-card ${cartQuantity > 0 ? 'in-cart' : ''} ${isOutOfStock ? 'out-of-stock' : ''}`}
      onClick={handleCardClick}
    >
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
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" aria-hidden="true">
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
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M12 21s-7-4.35-7-10a4 4 0 017-2.4A4 4 0 0119 11c0 5.65-7 10-7 10z" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>
        {isOutOfStock && (
          <div className="offer-stock-overlay">Mavjud emas</div>
        )}
      </div>
      <div className="offer-body">
        <h3 className="offer-title" title={titleText}>{titleText}</h3>
        {showRating ? (
          <div className="offer-rating-row" aria-label={`Reyting ${ratingText}`}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M12 3.5l2.47 5 5.52.8-4 3.9.94 5.5L12 16.7l-4.93 2.6.94-5.5-4-3.9 5.52-.8L12 3.5z"/>
            </svg>
            <span className="offer-rating-value">{ratingText}</span>
            {showRatingLocation && (
              <span className="offer-rating-location">{locationText}</span>
            )}
          </div>
        ) : (
          locationText && (
            <p className="offer-location" title={locationText}>{locationText}</p>
          )
        )}
        <div className="offer-footer">
          <div className="offer-price-block">
            {showStoreName && (
              <span className="offer-store" title={storeName}>{storeName}</span>
            )}
            {oldPriceLabel && (
              <span className="offer-old-price">{oldPriceLabel}</span>
            )}
            <span className="offer-price">{priceLabel}</span>
          </div>
          <div className="offer-action">
            <button
              type="button"
              className={`offer-add-btn ${isAdding ? 'pulse' : ''}`}
              onClick={handleAddClick}
              disabled={isOutOfStock || isMaxReached}
              aria-label="Savatga qo'shish"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  )
})

export default OfferCard

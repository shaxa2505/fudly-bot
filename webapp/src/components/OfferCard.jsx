import { memo, useState, useCallback, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useToast } from '../context/ToastContext'
import { useFavorites } from '../context/FavoritesContext'
import { PLACEHOLDER_IMAGE, resolveOfferImageUrl } from '../utils/imageUtils'
import { getOfferAvailability } from '../utils/availability'
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
  const { isFavorite, toggleFavorite } = useFavorites()
  const [isAdding, setIsAdding] = useState(false)
  const [justAdded, setJustAdded] = useState(false)
  const prevQtyRef = useRef(cartQuantity)

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

  useEffect(() => {
    if (prevQtyRef.current === 0 && cartQuantity > 0) {
      setJustAdded(true)
      const timer = setTimeout(() => setJustAdded(false), 360)
      prevQtyRef.current = cartQuantity
      return () => clearTimeout(timer)
    }
    prevQtyRef.current = cartQuantity
    return undefined
  }, [cartQuantity])

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
  const normalizeText = (value) => String(value || '').trim()
  const storeNameNormalized = normalizeText(storeName).toLowerCase()

  const availability = getOfferAvailability(offer)
  const timeRange = availability.timeRange
  const isUnavailableNow = Boolean(timeRange && !availability.isAvailableNow)

  const handleAddClick = useCallback((e) => {
    e.stopPropagation()
    if (isOutOfStock || isMaxReached || isUnavailableNow) {
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('warning')
      if (isUnavailableNow && timeRange) {
        toast?.warning(`Buyurtma vaqti: ${timeRange}`, 2000)
      }
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
  }, [cartQuantity, isOutOfStock, isMaxReached, isUnavailableNow, offer, onAddToCart, timeRange, toast])

  const originalPrice = Number(offer.original_price) || 0
  const discountPrice = Number(offer.discount_price) || 0
  const priceValue = discountPrice > 0 ? discountPrice : originalPrice
  const hasOldPrice = originalPrice > priceValue && priceValue > 0
  const isLowStock = !isOutOfStock && stockLimit > 0 && stockLimit <= 5
  const locationText = offer.store_address || offer.address || offer.district || offer.region || ''

  const titleCandidates = [
    offer.title,
    offer.product_name,
    offer.productTitle,
    offer.product,
    offer.item_name,
    offer.itemTitle,
    offer.item,
    offer.name,
    offer.description,
  ]
  const productTitle = titleCandidates.find((candidate) => {
    const normalized = normalizeText(candidate)
    if (!normalized) return false
    if (storeNameNormalized && normalized.toLowerCase() === storeNameNormalized) return false
    return true
  }) || 'Mahsulot'
  const titleText = productTitle
  const showStoreName = Boolean(storeNameNormalized && storeNameNormalized !== normalizeText(titleText).toLowerCase())
  const offerId = offer?.id ?? offer?.offer_id ?? offer?.offerId
  const isFav = offerId ? isFavorite(offerId) : false
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
    if (!offerId) return
    toggleFavorite(offer)
  }, [offer, offerId, toggleFavorite])

  return (
    <div
      className={`offer-card ${justAdded ? 'just-added' : ''} ${cartQuantity > 0 ? 'in-cart' : ''} ${isOutOfStock ? 'out-of-stock' : ''} ${isUnavailableNow ? 'is-unavailable' : ''}`}
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
            const img = e.target
            if (!img.dataset.refreshAttempted && resolvedUrl.includes('/photo/')) {
              img.dataset.refreshAttempted = 'true'
              const separator = resolvedUrl.includes('?') ? '&' : '?'
              img.src = `${resolvedUrl}${separator}refresh=1`
              return
            }
            if (!img.dataset.fallback) {
              img.dataset.fallback = 'true'
              img.src = fallbackUrl
              setImageError(true)
              LOADED_IMAGE_CACHE.add(fallbackUrl)
              setImageLoaded(true)
            }
          }}
        />
        <div className="offer-tags">
          {isUnavailableNow && (
            <span className="offer-tag offer-tag--closed">Hozir yopiq</span>
          )}
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
          className={`offer-favorite ${isFav ? 'is-active' : ''}`}
          onClick={handleFavoriteClick}
          aria-label={isFav ? "Sevimlilardan o'chirish" : "Sevimlilarga qo'shish"}
          aria-pressed={isFav}
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill={isFav ? 'currentColor' : 'none'}
            aria-hidden="true"
          >
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
              disabled={isOutOfStock || isMaxReached || isUnavailableNow}
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

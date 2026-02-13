import { memo, useState, useCallback, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useToast } from '../context/ToastContext'
import { useFavorites } from '../context/FavoritesContext'
import { getUserLanguage } from '../utils/auth'
import { PLACEHOLDER_IMAGE, resolveOfferImageUrl } from '../utils/imageUtils'
import { getOfferAvailability, getTashkentNowMinutes } from '../utils/availability'
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
  const lang = getUserLanguage()
  const t = (ru, uz) => (lang === 'uz' ? uz : ru)
  const [isAdding, setIsAdding] = useState(false)
  const [justAdded, setJustAdded] = useState(false)
  const prevQtyRef = useRef(cartQuantity)
  const imageWrapRef = useRef(null)

  // Get photo URL (handles Telegram file_id conversion)
  const photoUrl = resolveOfferImageUrl(offer)
  const fallbackUrl = PLACEHOLDER_IMAGE
  const resolvedUrl = photoUrl || fallbackUrl
  const [shouldLoad, setShouldLoad] = useState(imagePriority)
  const targetUrl = shouldLoad ? resolvedUrl : fallbackUrl
  const [imageLoaded, setImageLoaded] = useState(() => LOADED_IMAGE_CACHE.has(targetUrl))
  const [imageError, setImageError] = useState(false)

  useEffect(() => {
    setImageError(false)
    setImageLoaded(LOADED_IMAGE_CACHE.has(targetUrl))
  }, [targetUrl])

  useEffect(() => {
    if (imagePriority || shouldLoad) return undefined
    const node = imageWrapRef.current
    if (!node) {
      setShouldLoad(true)
      return undefined
    }
    if (!('IntersectionObserver' in window)) {
      setShouldLoad(true)
      return undefined
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setShouldLoad(true)
          observer.disconnect()
        }
      },
      { rootMargin: '200px' }
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [imagePriority, shouldLoad])

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
  const timeBadgeLabel = availability.endLabel
    ? t(`До ${availability.endLabel}`, `${availability.endLabel} gacha`)
    : availability.startLabel
      ? t(`С ${availability.startLabel}`, `${availability.startLabel} dan`)
      : ''

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
  const normalizePercent = (value) => {
    if (value == null) return null
    let raw = value
    if (typeof raw === 'string') {
      raw = raw.replace('%', '').trim()
    }
    const num = Number(raw)
    if (!Number.isFinite(num)) return null
    if (num > 0 && num <= 1) return num * 100
    return num
  }

  let discountPercent = 0
  const percentFromOffer = normalizePercent(
    offer.discount_percent ?? offer.discountPercent ?? offer.discount
  )
  if (percentFromOffer && percentFromOffer > 0) {
    discountPercent = Math.round(percentFromOffer)
  } else if (originalPrice > 0 && discountPrice > 0 && originalPrice > discountPrice) {
    discountPercent = Math.round((1 - discountPrice / originalPrice) * 100)
  }
  const showDiscountTag = discountPercent > 0
  const isLowStock = !isOutOfStock && stockLimit > 0 && stockLimit <= 5
  const locationText = offer.store_address || offer.address || offer.district || offer.region || ''
  const locationShort = locationText ? locationText.split(',')[0].trim() : ''

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
  const priceLabel = priceValue > 0
    ? Math.round(priceValue).toLocaleString('ru-RU')
    : ''
  const oldPriceLabel = hasOldPrice
    ? `${Math.round(originalPrice / 1000)}k`
    : ''

  const handleFavoriteClick = useCallback((e) => {
    e.stopPropagation()
    if (!offerId) return
    toggleFavorite(offer)
  }, [offer, offerId, toggleFavorite])

  const parseTimeToMinutes = (label) => {
    if (!label) return null
    const match = String(label).match(/(\d{1,2}):(\d{2})/)
    if (!match) return null
    const hours = Number(match[1])
    const minutes = Number(match[2])
    if (!Number.isFinite(hours) || !Number.isFinite(minutes)) return null
    return hours * 60 + minutes
  }

  const buildTimeLeftLabel = () => {
    const endMinutes = parseTimeToMinutes(availability.endLabel)
    if (endMinutes == null) return ''
    const nowMinutes = getTashkentNowMinutes()
    let diff = endMinutes - nowMinutes
    if (diff < 0) diff += 24 * 60
    if (diff <= 0 || diff > 180) return ''
    const hoursLeft = Math.max(1, Math.ceil(diff / 60))
    return t(`${hoursLeft} ч осталось`, `${hoursLeft} soat qoldi`)
  }

  const timeLeftLabel = buildTimeLeftLabel()

  const buildClosedLabel = () => {
    if (availability.startLabel) {
      return t(`Откроется в ${availability.startLabel}`, `${availability.startLabel} da ochiladi`)
    }
    return t('Сейчас закрыто', 'Hozir yopiq')
  }

  const stockLeftLabel = t(`Осталось ${stockLimit}`, `${stockLimit} ta qoldi`)

  const metaTag = (() => {
    if (isUnavailableNow) return { text: buildClosedLabel(), variant: 'closed' }
    if (isLowStock) return { text: stockLeftLabel, variant: 'alert' }
    if (timeLeftLabel) return { text: timeLeftLabel, variant: 'time' }
    return null
  })()

  return (
    <div
      className={`offer-card ${justAdded ? 'just-added' : ''} ${cartQuantity > 0 ? 'in-cart' : ''} ${isOutOfStock ? 'out-of-stock' : ''} ${isUnavailableNow ? 'is-unavailable' : ''}`}
      onClick={handleCardClick}
    >
      <div className="offer-image-wrap" ref={imageWrapRef}>
        {shouldLoad && !imageLoaded && !imageError && (
          <div className="offer-image-skeleton shimmer" />
        )}
        <img
          src={targetUrl}
          alt={titleText}
          className={`offer-image ${imageLoaded ? 'loaded' : ''}`}
          loading={imagePriority ? 'eager' : 'lazy'}
          fetchPriority={imagePriority ? 'high' : 'auto'}
          decoding="async"
          onLoad={(e) => {
            const loadedUrl = e?.currentTarget?.currentSrc || e?.currentTarget?.src || targetUrl
            LOADED_IMAGE_CACHE.add(loadedUrl)
            setImageLoaded(true)
          }}
          onError={(e) => {
            if (!shouldLoad) return
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
        {showDiscountTag && (
          <div className={`offer-discount-badge ${discountPercent > 50 ? 'offer-discount-badge--high' : ''}`}>
            -{discountPercent}%
          </div>
        )}
        <div className={`offer-image-overlay ${metaTag ? '' : 'only-action'}`}>
          {metaTag && (
            <span className={`offer-meta-tag offer-meta-tag--${metaTag.variant}`}>
              {metaTag.text}
            </span>
          )}
          <button
            type="button"
            className={`offer-add-btn offer-add-btn--image ${isAdding ? 'pulse' : ''}`}
            onClick={handleAddClick}
            disabled={isOutOfStock || isMaxReached || isUnavailableNow}
            aria-label="Savatga qo'shish"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          </button>
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
            <path d="M12 21s-7-4.35-7-10a4 4 0 017-2.4A4 4 0 0119 11c0 5.65-7 10-7 10z" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
        {isOutOfStock && (
          <div className="offer-stock-overlay">Mavjud emas</div>
        )}
      </div>
      <div className="offer-body">
        {(showStoreName || timeBadgeLabel) && (
          <div className={`offer-body-top ${showStoreName ? '' : 'only-time'}`}>
            {showStoreName && (
              <span className="offer-store" title={storeName}>{storeName}</span>
            )}
            {timeBadgeLabel && (
              <span className="offer-time-badge">{timeBadgeLabel}</span>
            )}
          </div>
        )}
        <h3 className="offer-title" title={titleText}>{titleText}</h3>
        <div className="offer-footer">
          <div className="offer-price-block">
            <span className="offer-price">{priceLabel}</span>
            {oldPriceLabel && (
              <span className="offer-old-price">{oldPriceLabel}</span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
})

export default OfferCard

import { useState, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { useCart } from '../context/CartContext'
import { calcItemsTotal } from '../utils/orderMath'
import { getOfferAvailability } from '../utils/availability'
import api from '../api/client'
import { resolveOfferImageUrl } from '../utils/imageUtils'
import QuantityControl from '../components/QuantityControl'
import './ProductDetailPage.css'

function ProductDetailPage() {
  const location = useLocation()
  const { addToCart } = useCart()

  const initialOffer = location.state?.offer || null
  const [offer, setOffer] = useState(initialOffer)
  const [store, setStore] = useState(null)
  const [isLoadingOffer, setIsLoadingOffer] = useState(!initialOffer)
  const [quantity, setQuantity] = useState(1)
  const [addedToCart, setAddedToCart] = useState(false)
  const [imgError, setImgError] = useState(false)
  const searchParams = new URLSearchParams(location.search)
  const queryOfferIdRaw = searchParams.get('offer_id') || searchParams.get('id')
  const queryOfferId = queryOfferIdRaw ? Number(queryOfferIdRaw) : null
  const resolvedOfferId = offer?.id ?? offer?.offer_id ?? queryOfferId
  const offerId = Number.isFinite(Number(resolvedOfferId)) ? Number(resolvedOfferId) : null
  const stockValue = Number(offer?.quantity ?? offer?.stock ?? 0)
  const hasStock = stockValue > 0
  const maxQty = hasStock ? stockValue : 1

  useEffect(() => {
    setOffer(initialOffer)
  }, [initialOffer])

  useEffect(() => {
    if (!offerId) {
      setIsLoadingOffer(false)
      return
    }
    let cancelled = false
    if (!offer) {
      setIsLoadingOffer(true)
    }
    api.getOffer(offerId)
      .then((data) => {
        if (cancelled || !data) return
        setOffer(prev => ({ ...(prev || {}), ...data }))
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setIsLoadingOffer(false)
      })
    return () => {
      cancelled = true
    }
  }, [offerId])

  useEffect(() => {
    if (!offer?.store_id) {
      setStore(null)
      return
    }
    let cancelled = false
    api.getStore(offer.store_id)
      .then((data) => {
        if (cancelled) return
        setStore(data || null)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [offer?.store_id])

  // Track recently viewed
  useEffect(() => {
    const viewedId = offer?.id ?? offer?.offer_id ?? offerId
    if (viewedId) {
      const userId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id
      if (userId) {
        api.addRecentlyViewed(viewedId).catch(() => {})
      }
    }
  }, [offer?.id, offer?.offer_id, offerId])

  useEffect(() => {
    if (!hasStock) {
      setQuantity(1)
      return
    }
    setQuantity(prev => Math.min(prev, maxQty))
  }, [hasStock, maxQty])

  // Get image URL - support multiple field names and convert file_id
  const imageUrl = resolveOfferImageUrl(offer) || ''
  const hasImage = Boolean(imageUrl) && !imgError
  const originalPrice = Number(offer?.original_price ?? 0)
  const discountPrice = Number(offer?.discount_price ?? offer?.price ?? 0)
  const unitPrice = discountPrice || originalPrice || 0
  const hasDiscount = originalPrice > 0 && unitPrice > 0 && originalPrice > unitPrice
  const fallbackDiscountPercent = hasDiscount
    ? Math.round((1 - unitPrice / originalPrice) * 100)
    : 0
  const discountPercent = Number(offer?.discount_percent ?? 0) || fallbackDiscountPercent
  const totalPrice = Math.max(0, calcItemsTotal([{ price: unitPrice, quantity }]))
  const storeName = offer?.store_name || store?.name || ''
  const storeAddress = offer?.store_address || store?.address || ''
  const availability = getOfferAvailability(offer)
  const isUnavailableNow = Boolean(availability.timeRange && !availability.isAvailableNow)
  const showDiscountBadge = discountPercent > 0
  const formatPrice = (value) => Math.round(value || 0).toLocaleString('ru-RU')
  const descriptionText = offer?.description &&
    offer.description.toLowerCase() !== offer.title?.toLowerCase()
    ? offer.description
    : ''

  const formatDistanceMeters = (value) => {
    const raw = Number(value)
    if (!Number.isFinite(raw) || raw <= 0) return ''
    if (raw < 950) return `${Math.round(raw)} m`
    return `${(raw / 1000).toFixed(1)} km`
  }

  const formatDistanceKm = (value) => {
    const raw = Number(value)
    if (!Number.isFinite(raw) || raw <= 0) return ''
    return `${raw.toFixed(1)} km`
  }

  const distanceKm = offer?.distance_km ?? offer?.distanceKm ?? store?.distance
  const distanceMeters = offer?.distance_m ?? offer?.distanceM ?? offer?.distance_meters
  const distanceRaw = offer?.distance
  let distanceLabel = ''

  if (distanceKm != null) {
    distanceLabel = formatDistanceKm(distanceKm)
  } else if (distanceMeters != null) {
    distanceLabel = formatDistanceMeters(distanceMeters)
  } else if (typeof distanceRaw === 'string') {
    distanceLabel = distanceRaw.trim()
  } else if (Number.isFinite(Number(distanceRaw))) {
    const numeric = Number(distanceRaw)
    distanceLabel = numeric < 20 ? formatDistanceKm(numeric) : formatDistanceMeters(numeric)
  }

  const storeInitial = storeName ? storeName.trim().charAt(0).toUpperCase() : '?'

  const buildExpiryDisplay = () => {
    if (!offer?.expiry_date) return ''
    const expiryDate = new Date(offer.expiry_date)
    if (Number.isNaN(expiryDate.getTime())) return ''
    const now = new Date()
    const timeLabel = expiryDate.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
    const todayLabel = now.toDateString()
    const tomorrow = new Date(now)
    tomorrow.setDate(now.getDate() + 1)
    if (expiryDate.toDateString() === todayLabel) return `Today, ${timeLabel}`
    if (expiryDate.toDateString() === tomorrow.toDateString()) return `Tomorrow, ${timeLabel}`
    return `${expiryDate.toLocaleDateString('ru-RU')} ${timeLabel}`
  }

  const pickupLabel = availability.timeRange || '—'
  const expiryLabel = buildExpiryDisplay() || '—'
  const remainingLabel = hasStock ? `${stockValue} items left` : 'Out of stock'
  const co2ValueRaw =
    offer?.co2_saved ??
    offer?.co2_saved_kg ??
    offer?.saved_co2 ??
    offer?.saved_co2_kg
  const co2Value = Number(co2ValueRaw)
  const co2Label = Number.isFinite(co2Value) && co2Value > 0 ? `${co2Value} kg` : '—'

  const handleQuantityChange = (delta) => {
    if (!hasStock) {
      return
    }
    setQuantity(prev => Math.max(1, Math.min(prev + delta, maxQty)))
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light')
  }

  const handleAddToCart = () => {
    if (!hasStock || !offer) {
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('warning')
      return
    }
    if (isUnavailableNow) {
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('warning')
      const message = availability.timeRange
        ? `Buyurtma vaqti: ${availability.timeRange}`
        : "Hozir buyurtma qilish mumkin emas"
      if (window.Telegram?.WebApp?.showAlert) {
        window.Telegram?.WebApp?.showAlert?.(message)
      } else {
        // eslint-disable-next-line no-alert
        alert(message)
      }
      return
    }

    const finalQty = Math.min(quantity, maxQty)
    for (let i = 0; i < finalQty; i++) {
      addToCart(offer)
    }
    setAddedToCart(true)
    window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('success')

    // Show success feedback for 3 seconds
    setTimeout(() => setAddedToCart(false), 3000)
  }

  if (!offer && !isLoadingOffer) {
    return (
      <div className="pdp">
        <div className="pdp-error">
          <span>!</span>
          <p>Mahsulot topilmadi</p>
        </div>
      </div>
    )
  }

  if (!offer) {
    return (
      <div className="pdp">
        <div className="pdp-loading">
          <div className="pdp-loading-badge" />
          <div className="pdp-loading-line" />
          <div className="pdp-loading-line short" />
        </div>
      </div>
    )
  }


  return (
    <div className="pdp">
      {/* Hero Section */}
      <section className="pdp-hero">
        <div className={`pdp-hero-media ${hasImage ? 'has-image' : 'is-placeholder'}`}>
          {hasImage ? (
            <img
              src={imageUrl}
              alt={offer.title}
              className="pdp-image"
              loading="eager"
              fetchPriority="high"
              decoding="async"
              onError={() => setImgError(true)}
            />
          ) : (
            <div className="pdp-image-placeholder">
              <svg width="64" height="64" viewBox="0 0 24 24" fill="none">
                <rect x="3" y="3" width="18" height="18" rx="2" stroke="#ccc" strokeWidth="1.5"/>
                <circle cx="8.5" cy="8.5" r="1.5" fill="#ccc"/>
                <path d="M21 15l-5-5L5 21" stroke="#ccc" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
          )}
        </div>
      </section>

      <section className="pdp-sheet">
        <div className="pdp-sheet-inner">
          <h1 className="pdp-title">{offer.title}</h1>
          <div className="pdp-price-row">
            <span className="pdp-price-current">{formatPrice(unitPrice)} UZS</span>
            {hasDiscount && (
              <span className="pdp-price-old">{formatPrice(originalPrice)} UZS</span>
            )}
            {showDiscountBadge && (
              <span className="pdp-discount-pill">-{discountPercent}%</span>
            )}
          </div>

          {descriptionText && (
            <p className="pdp-description-text">{descriptionText}</p>
          )}

          <div className="pdp-info-grid new-grid">
            <div className="pdp-info-card">
              <div className="pdp-info-label">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" />
                  <path d="M12 7v5l3 2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                </svg>
                Pickup Time
              </div>
              <div className="pdp-info-value">{pickupLabel}</div>
            </div>
            <div className="pdp-info-card">
              <div className="pdp-info-label">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <path d="M6 2h12v4l-4 4v4l-4 4v4H6v-4l4-4v-4L6 6V2z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
                Expires In
              </div>
              <div className="pdp-info-value">{expiryLabel}</div>
            </div>
            <div className="pdp-info-card">
              <div className="pdp-info-label">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <path d="M4 7h16v10H4z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round"/>
                  <path d="M4 7l4-3h8l4 3" stroke="currentColor" strokeWidth="2" strokeLinejoin="round"/>
                </svg>
                Remaining
              </div>
              <div className="pdp-info-value">{remainingLabel}</div>
            </div>
            <div className="pdp-info-card">
              <div className="pdp-info-label">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <path d="M7 21c5.5 0 10-4.5 10-10V3S9 3 4 8c-2.6 2.6-2 6.5 1.5 10z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round"/>
                </svg>
                Saved CO2
              </div>
              <div className="pdp-info-value">{co2Label}</div>
            </div>
          </div>

          {(storeName || storeAddress) && (
            <div className="pdp-store-card">
              <div className="pdp-store-row">
                <div className="pdp-store-avatar">{storeInitial}</div>
                <div className="pdp-store-info">
                  <div className="pdp-store-name">{storeName || 'Store'}</div>
                  <div className="pdp-store-meta">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                      <path d="M12 21s-6-5-6-10a6 6 0 1112 0c0 5-6 10-6 10z" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                      <circle cx="12" cy="11" r="2" fill="currentColor"/>
                    </svg>
                    <span>{storeAddress || '—'}</span>
                    {distanceLabel && (
                      <span className="pdp-store-distance">• {distanceLabel}</span>
                    )}
                  </div>
                </div>
                <span className="pdp-store-chevron">›</span>
              </div>
              <div className="pdp-map-preview">
                <button type="button" className="pdp-map-button">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path d="M12 19l7-16-7 4-7-4 7 16z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round"/>
                  </svg>
                  View on Map
                </button>
              </div>
            </div>
          )}

          <div className="pdp-note">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2"/>
              <path d="M12 8h.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
              <path d="M11 12h2v4h-2z" fill="currentColor"/>
            </svg>
            <span>This is a surprise bag item. The contents may vary slightly depending on availability.</span>
          </div>
        </div>
      </section>

      {/* Fixed Bottom Button */}
      <div className="pdp-bottom">
        <div className="pdp-bottom-inner">
          <QuantityControl
            value={quantity}
            size="md"
            className="pdp-bottom-qty"
            onDecrement={() => handleQuantityChange(-1)}
            onIncrement={() => handleQuantityChange(1)}
            disableDecrement={!hasStock || quantity <= 1}
            disableIncrement={!hasStock || quantity >= maxQty || isUnavailableNow}
          />
          <button
            className={`pdp-add-btn ${addedToCart ? 'success' : ''}`}
            onClick={handleAddToCart}
            disabled={addedToCart || !hasStock || isUnavailableNow}
          >
            <span className="pdp-add-text">
              {!hasStock
                ? "Out of stock"
                : (isUnavailableNow ? "Closed" : (addedToCart ? "Added!" : "Add to Cart"))
              }
            </span>
            {hasStock && (
              <span className="pdp-add-total">
                • {formatPrice(totalPrice)} UZS
              </span>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}

export default ProductDetailPage

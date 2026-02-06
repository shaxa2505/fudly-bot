import { useState, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { useCart } from '../context/CartContext'
import { useFavorites } from '../context/FavoritesContext'
import { getUnitLabel } from '../utils/helpers'
import { calcItemsTotal } from '../utils/orderMath'
import { getOfferAvailability } from '../utils/availability'
import api from '../api/client'
import { resolveOfferImageUrl } from '../utils/imageUtils'
import QuantityControl from '../components/QuantityControl'
import './ProductDetailPage.css'

function ProductDetailPage() {
  const location = useLocation()
  const { addToCart } = useCart()
  const { isFavorite, toggleFavorite } = useFavorites()

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
  const unitLabel = offer?.unit ? getUnitLabel(offer.unit) : ''
  const displayUnitLabel = unitLabel || 'dona'
  const originalPrice = Number(offer?.original_price ?? 0)
  const discountPrice = Number(offer?.discount_price ?? offer?.price ?? 0)
  const unitPrice = discountPrice || originalPrice || 0
  const hasDiscount = originalPrice > 0 && unitPrice > 0 && originalPrice > unitPrice
  const fallbackDiscountPercent = hasDiscount
    ? Math.round((1 - unitPrice / originalPrice) * 100)
    : 0
  const discountPercent = Number(offer?.discount_percent ?? 0) || fallbackDiscountPercent
  const savingsPerUnit = hasDiscount ? Math.max(0, originalPrice - unitPrice) : 0
  const totalPrice = Math.max(0, calcItemsTotal([{ price: unitPrice, quantity }]))
  const totalSavings = calcItemsTotal([{ price: savingsPerUnit, quantity }])
  const storeName = offer?.store_name || store?.name || ''
  const storeAddress = offer?.store_address || store?.address || ''
  const deliveryEnabled = offer?.delivery_enabled ?? store?.delivery_enabled ?? false
  const deliveryPrice = Number(offer?.delivery_price ?? store?.delivery_price ?? 0)
  const minOrderAmount = Number(offer?.min_order_amount ?? store?.min_order_amount ?? 0)
  const lowStock = hasStock && stockValue <= 3
  const midStock = hasStock && stockValue > 3 && stockValue <= 10
  const stockMeterValue = !hasStock ? 0 : lowStock ? 24 : midStock ? 56 : 92
  const availability = getOfferAvailability(offer)
  const isUnavailableNow = Boolean(availability.timeRange && !availability.isAvailableNow)
  const showDiscountBadge = discountPercent > 0 && !hasDiscount
  const formatPrice = (value) => Math.round(value || 0).toLocaleString('ru-RU')

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

  const handleFavorite = (e) => {
    e.stopPropagation()
    toggleFavorite(offer)
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light')
  }

  const handleShare = () => {
    if (!offer) return
    const sharePrice = formatPrice(unitPrice)
    const shareStore = storeName || ''
    const text = `${offer.title}\nNarx: ${sharePrice} so'm\nDo'kon: ${shareStore}`
    if (navigator.share) {
      navigator.share({ title: offer.title, text }).catch(() => {})
    }
  }

  // Expiry calculation
  const getExpiryInfo = () => {
    if (!offer?.expiry_date) return null
    try {
      const days = Math.ceil((new Date(offer.expiry_date) - new Date()) / 86400000)
      if (days < 0) return { text: "Muddati o'tgan", urgent: true }
      if (days === 0) return { text: "Bugun tugaydi!", urgent: true }
      if (days === 1) return { text: "Ertaga tugaydi", urgent: true }
      if (days <= 3) return { text: `${days} kun qoldi`, urgent: true }
      if (days <= 7) return { text: `${days} kun qoldi`, urgent: false }
      return null
    } catch { return null }
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

  const expiryInfo = getExpiryInfo()
  const expiryDateLabel = offer?.expiry_date
    ? new Date(offer.expiry_date).toLocaleDateString('ru-RU')
    : ''
  const expiryMeta = expiryDateLabel
    ? `${expiryDateLabel}${expiryInfo?.text ? ` / ${expiryInfo.text}` : ''}`
    : (expiryInfo?.text || '')
  const isFav = isFavorite(offer.id || offer.offer_id)

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
          {(showDiscountBadge || expiryInfo) && (
            <div className="pdp-hero-badges">
              {showDiscountBadge && (
                <span className="pdp-badge pdp-badge-discount">-{discountPercent}%</span>
              )}
              {expiryInfo && (
                <span className={`pdp-badge pdp-badge-expiry ${expiryInfo.urgent ? 'is-urgent' : ''}`}>
                  {expiryInfo.text}
                </span>
              )}
            </div>
          )}
        </div>
      </section>

      {/* Content */}
      <section className="pdp-body">
        <div className="pdp-title-block">
          <div className="pdp-title-row">
            <div className="pdp-title-main">
              <h1 className="pdp-title">{offer.title}</h1>
              {storeName && (
                <div className="pdp-store">
                  <div className="pdp-store-line">
                    <span className="pdp-store-label">DO'KON</span>
                    <span className="pdp-store-name">{storeName}</span>
                  </div>
                  {storeAddress && <div className="pdp-store-address">{storeAddress}</div>}
                </div>
              )}
            </div>
            <div className="pdp-title-actions">
              <button
                className={`pdp-icon-btn ${isFav ? 'active' : ''}`}
                onClick={handleFavorite}
                aria-label="Sevimli"
              >
                <svg width="22" height="22" viewBox="0 0 24 24" fill={isFav ? "#FF4757" : "none"}>
                  <path
                    d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"
                    stroke={isFav ? "#FF4757" : "currentColor"}
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
              <button className="pdp-icon-btn" onClick={handleShare} aria-label="Ulashish">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                  <path
                    d="M4 12v8a2 2 0 002 2h12a2 2 0 002-2v-8M16 6l-4-4-4 4M12 2v13"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
            </div>
          </div>
          <div className="pdp-info-grid">
            <div className="pdp-info-item">
              <span className="pdp-info-label">Yaroqlilik</span>
              <span className={`pdp-info-value ${expiryInfo?.urgent ? 'is-urgent' : ''}`}>
                {expiryMeta || '?'}
              </span>
            </div>
            <div className="pdp-info-item">
              <span className="pdp-info-label">Buyurtma vaqti</span>
              <span className={`pdp-info-value ${isUnavailableNow ? 'is-urgent' : ''}`}>
                {availability.timeRange || '?'}
              </span>
            </div>
            <div className="pdp-info-item">
              <span className="pdp-info-label">Birlik</span>
              <span className="pdp-info-value">{displayUnitLabel}</span>
            </div>
            <div className="pdp-info-item">
              <span className="pdp-info-label">Qoldiq</span>
              <span className={`pdp-info-value ${lowStock ? 'is-urgent' : ''}`}>
                {hasStock ? `${stockValue} ${displayUnitLabel}` : 'Tugagan'}
              </span>
            </div>
          </div>
        </div>

        <div className="pdp-price-card">
          <div className="pdp-price-main">
            <span className="pdp-current-price">{formatPrice(unitPrice)} so'm</span>
            {showDiscountBadge && (
              <span className="pdp-price-badge">-{discountPercent}%</span>
            )}
          </div>
          <div className="pdp-price-sub">
            {hasDiscount && (
              <span className="pdp-old-price">{formatPrice(originalPrice)} so'm</span>
            )}
            {hasDiscount && savingsPerUnit > 0 && (
              <span className="pdp-savings">Tejaysiz {formatPrice(savingsPerUnit)} so'm</span>
            )}
          </div>
          <div className="pdp-price-sub">
            {hasDiscount && totalSavings > 0 && (
              <span className="pdp-total-savings">Jami tejaysiz {formatPrice(totalSavings)} so'm</span>
            )}
          </div>
          {availability.timeRange && (
            <div className={`pdp-availability ${isUnavailableNow ? 'is-closed' : ''}`}>
              <span>{isUnavailableNow ? 'Hozir yopiq' : 'Buyurtma vaqti'}</span>
              <strong>{availability.timeRange}</strong>
            </div>
          )}
          <div className="pdp-stock-meter">
            <span
              className={`pdp-stock-meter-fill ${lowStock ? 'is-low' : midStock ? 'is-mid' : ''}`}
              style={{ width: `${stockMeterValue}%` }}
            />
          </div>
        </div>

        <div className="pdp-card pdp-delivery-card">
          <div className="pdp-card-header">
            <h3 className="pdp-card-title">Yetkazib berish</h3>
          </div>
          <div className="pdp-card-row">
            <span>Holat</span>
            <span>{deliveryEnabled ? "Mavjud" : "Faqat olib ketish"}</span>
          </div>
          {deliveryEnabled && deliveryPrice > 0 && (
            <div className="pdp-card-row">
              <span>Narxi</span>
              <span>{formatPrice(deliveryPrice)} so'm</span>
            </div>
          )}
          {minOrderAmount > 0 && (
            <div className="pdp-card-row">
              <span>Minimal buyurtma</span>
              <span>{formatPrice(minOrderAmount)} so'm</span>
            </div>
          )}
        </div>

        {offer.description && offer.description.toLowerCase() !== offer.title?.toLowerCase() && (
          <div className="pdp-description">
            <h3>Tavsif</h3>
            <p>{offer.description}</p>
          </div>
        )}
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
                ? "Tugagan"
                : (isUnavailableNow ? "Hozir yopiq" : (addedToCart ? "Qo'shildi!" : "Savatga qo'shish"))
              }
            </span>
            {hasStock && (
              <span className="pdp-add-total">
                <span className="pdp-add-amount">{formatPrice(totalPrice)}</span>
                <span className="pdp-add-currency">so'm</span>
              </span>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}

export default ProductDetailPage

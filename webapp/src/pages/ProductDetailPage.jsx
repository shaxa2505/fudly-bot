import { useState, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { useCart } from '../context/CartContext'
import { useFavorites } from '../context/FavoritesContext'
import { getUnitLabel } from '../utils/helpers'
import api from '../api/client'
import { resolveOfferImageUrl } from '../utils/imageUtils'
import QuantityControl from '../components/QuantityControl'
import './ProductDetailPage.css'

function ProductDetailPage() {
  const location = useLocation()
  const { addToCart } = useCart()
  const { isFavorite, toggleFavorite } = useFavorites()

  const offer = location.state?.offer
  const [quantity, setQuantity] = useState(1)
  const [addedToCart, setAddedToCart] = useState(false)
  const [imgError, setImgError] = useState(false)

  // Track recently viewed
  useEffect(() => {
    if (offer?.id) {
      const userId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id
      if (userId) {
        api.addRecentlyViewed(offer.id).catch(() => {})
      }
    }
  }, [offer?.id])

  // Get image URL - support multiple field names and convert file_id
  const imageUrl = resolveOfferImageUrl(offer) || ''
  const hasImage = Boolean(imageUrl) && !imgError

  const handleQuantityChange = (delta) => {
    const maxQty = offer?.quantity || 99
    setQuantity(prev => Math.max(1, Math.min(prev + delta, maxQty)))
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light')
  }

  const handleAddToCart = () => {
    for (let i = 0; i < quantity; i++) {
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
    const text = `${offer.title}\nNarx: ${Math.round(offer.discount_price).toLocaleString()} so'm\nDo'kon: ${offer.store_name || ''}`
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

  if (!offer) {
    return (
      <div className="pdp">
        <div className="pdp-error">
          <span>!</span>
          <p>Mahsulot topilmadi</p>
        </div>
      </div>
    )
  }

  const expiryInfo = getExpiryInfo()
  const hasDiscount = offer.original_price > offer.discount_price
  const isFav = isFavorite(offer.id)

  return (
    <div className="pdp">
      {/* Header Actions */}
      <header className="pdp-header">
        <div className="pdp-header-actions">
          <button
            className={`pdp-action pdp-fav ${isFav ? 'active' : ''}`}
            onClick={handleFavorite}
            aria-label="Sevimli"
          >
            <svg width="26" height="26" viewBox="0 0 24 24" fill={isFav ? "#FF4757" : "none"}>
              <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"
                stroke={isFav ? "#FF4757" : "currentColor"}
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"/>
            </svg>
          </button>
          <button className="pdp-action pdp-share" onClick={handleShare} aria-label="Ulashish">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <path d="M4 12v8a2 2 0 002 2h12a2 2 0 002-2v-8M16 6l-4-4-4 4M12 2v13"
                stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
        </div>
      </header>

      {/* Hero Section */}
      <section className="pdp-hero">
        <div className={`pdp-hero-media ${hasImage ? 'has-image' : 'is-placeholder'}`}>
          {hasImage ? (
            <img
              src={imageUrl}
              alt={offer.title}
              className="pdp-image"
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
        <div className="pdp-hero-info">
          <h1 className="pdp-title">{offer.title}</h1>
          {offer.store_name && (
            <p className="pdp-store">
              <span className="pdp-store-label">Do'kon:</span>
              <span className="pdp-store-name">{offer.store_name}</span>
              {offer.store_address && <span className="pdp-store-addr"> - {offer.store_address}</span>}
            </p>
          )}
          {expiryInfo && (
            <p className={`pdp-expiry ${expiryInfo.urgent ? 'is-urgent' : ''}`}>
              Muddat: {expiryInfo.text}
            </p>
          )}
        </div>
      </section>

      {/* Content */}
      <section className="pdp-body">
        <div className="pdp-price-row">
          <div className="pdp-price-block">
            <span className="pdp-current-price">
              {Math.round(offer.discount_price).toLocaleString()} so'm
            </span>
            {hasDiscount && (
              <span className="pdp-old-price">
                {Math.round(offer.original_price).toLocaleString()} so'm
              </span>
            )}
            {offer.quantity > 0 && (
              <span className="pdp-stock">Qoldi: {offer.quantity} {getUnitLabel(offer.unit)}</span>
            )}
          </div>
          <QuantityControl
            value={quantity}
            size="sm"
            className="pdp-quantity-control"
            onDecrement={() => handleQuantityChange(-1)}
            onIncrement={() => handleQuantityChange(1)}
            disableDecrement={quantity <= 1}
            disableIncrement={quantity >= (offer.quantity || offer.stock || 99)}
          />
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
        <button
          className={`pdp-add-btn ${addedToCart ? 'success' : ''}`}
          onClick={handleAddToCart}
          disabled={addedToCart}
        >
          {addedToCart ? "Qo'shildi!" : "Savatga qo'shish"}
        </button>
      </div>
    </div>
  )
}

export default ProductDetailPage

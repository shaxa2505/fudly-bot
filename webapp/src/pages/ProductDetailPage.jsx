import { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { useCart } from '../context/CartContext'
import { useFavorites } from '../context/FavoritesContext'
import { getUnitLabel } from '../utils/helpers'
import api from '../api/client'
import { resolveOfferImageUrl } from '../utils/imageUtils'
import QuantityControl from '../components/QuantityControl'
import './ProductDetailPage.css'

function ProductDetailPage() {
  const navigate = useNavigate()
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
          <button onClick={() => navigate(-1)}>Orqaga</button>
        </div>
      </div>
    )
  }

  const expiryInfo = getExpiryInfo()
  const totalPrice = offer.discount_price * quantity
  const savings = (offer.original_price - offer.discount_price) * quantity
  const hasDiscount = offer.original_price > offer.discount_price
  // Calculate discount percent if not provided
  const discountPercent = offer.discount_percent
    ? Math.round(offer.discount_percent)
    : hasDiscount
      ? Math.round((1 - offer.discount_price / offer.original_price) * 100)
      : 0
  const isFav = isFavorite(offer.id)

  return (
    <div className="pdp">
      {/* Floating Header */}
      <header className="pdp-header">
        <button className="app-back-btn" onClick={() => navigate(-1)} aria-label="Orqaga">
          <ArrowLeft size={20} strokeWidth={2} />
        </button>

        <div className="pdp-header-actions">
          <button
            className={`pdp-fav ${isFav ? 'active' : ''}`}
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
          <button className="pdp-share" onClick={handleShare} aria-label="Ulashish">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <path d="M4 12v8a2 2 0 002 2h12a2 2 0 002-2v-8M16 6l-4-4-4 4M12 2v13"
                stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
        </div>
      </header>

      {/* Image Section */}
      <section className="pdp-image-section">
        {discountPercent > 0 && (
          <span className="pdp-discount-badge">-{discountPercent}%</span>
        )}

        {expiryInfo?.urgent && (
          <span className="pdp-expiry-badge">Muddat: {expiryInfo.text}</span>
        )}

        <div className="pdp-image-wrapper">
          {!imgError && imageUrl ? (
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
      </section>

      {/* Content */}
      <section className="pdp-content">
        {/* Title & Store */}
        <div className="pdp-title-section">
          <h1 className="pdp-title">{offer.title}</h1>
          {offer.store_name && (
            <p className="pdp-store">
              <span className="pdp-store-icon">Do'kon</span>
              <span className="pdp-store-name">{offer.store_name}</span>
              {offer.store_address && <span className="pdp-store-addr"> - {offer.store_address}</span>}
            </p>
          )}
        </div>

        {/* Price Card */}
        <div className="pdp-price-card">
          <div className="pdp-price-row">
            <div className="pdp-prices">
              <span className="pdp-current-price">
                {Math.round(offer.discount_price).toLocaleString()} so'm
              </span>
              {hasDiscount && (
                <span className="pdp-old-price">
                  {Math.round(offer.original_price).toLocaleString()}
                </span>
              )}
            </div>
            {offer.quantity > 0 && (
              <span className="pdp-stock">Qoldi: {offer.quantity} {getUnitLabel(offer.unit)}</span>
            )}
          </div>

          {savings > 0 && (
            <div className="pdp-savings">
              {Math.round(savings).toLocaleString()} so'm tejaysiz
            </div>
          )}
        </div>

        {/* Quantity Selector */}
        <div className="pdp-quantity-row">
          <span className="pdp-qty-label">Miqdor:</span>
          <QuantityControl
            value={quantity}
            size="lg"
            onDecrement={() => handleQuantityChange(-1)}
            onIncrement={() => handleQuantityChange(1)}
            disableDecrement={quantity <= 1}
            disableIncrement={quantity >= (offer.quantity || offer.stock || 99)}
          />
          <span className="pdp-total">{Math.round(totalPrice).toLocaleString()} so'm</span>
        </div>

        {/* Tags */}
        <div className="pdp-tags">
          {offer.category && (
            <span className="pdp-tag">Kategoriya: {offer.category}</span>
          )}
          {expiryInfo && !expiryInfo.urgent && (
            <span className="pdp-tag">Muddat: {expiryInfo.text}</span>
          )}
        </div>

        {/* Description */}
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
          {addedToCart ? (
            <>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
                <path d="M20 6L9 17l-5-5" stroke="white" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              Qo'shildi!
            </>
          ) : (
            <>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
                <circle cx="9" cy="21" r="1" fill="white"/>
                <circle cx="20" cy="21" r="1" fill="white"/>
                <path d="M1 1h4l2.68 13.39a2 2 0 002 1.61h9.72a2 2 0 002-1.61L23 6H6"
                  stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              Savatga qo'shish
            </>
          )}
        </button>
      </div>
    </div>
  )
}

export default ProductDetailPage

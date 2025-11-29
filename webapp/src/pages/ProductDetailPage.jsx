import { useState } from 'react'
import './ProductDetailPage.css'

function ProductDetailPage({ offer, onNavigate, onAddToCart }) {
  const [quantity, setQuantity] = useState(1)
  const [currentImageIndex, setCurrentImageIndex] = useState(0)
  const [showDetails, setShowDetails] = useState(true)
  const [addedToCart, setAddedToCart] = useState(false)
  const [touchStart, setTouchStart] = useState(null)
  const [touchEnd, setTouchEnd] = useState(null)

  // Swipe detection for image carousel
  const minSwipeDistance = 50
  const images = [offer?.photo].filter(Boolean)

  const onTouchStart = (e) => {
    setTouchEnd(null)
    setTouchStart(e.targetTouches[0].clientX)
  }

  const onTouchMove = (e) => {
    setTouchEnd(e.targetTouches[0].clientX)
  }

  const onTouchEnd = () => {
    if (!touchStart || !touchEnd) return
    const distance = touchStart - touchEnd
    const isLeftSwipe = distance > minSwipeDistance
    const isRightSwipe = distance < -minSwipeDistance
    
    if (isLeftSwipe && currentImageIndex < images.length - 1) {
      setCurrentImageIndex(prev => prev + 1)
    }
    if (isRightSwipe && currentImageIndex > 0) {
      setCurrentImageIndex(prev => prev - 1)
    }
  }

  const handleQuantityChange = (delta) => {
    const maxQty = offer?.quantity || 99
    const newQty = Math.max(1, Math.min(quantity + delta, maxQty))
    setQuantity(newQty)
  }

  const handleAddToBasket = () => {
    if (onAddToCart) {
      for (let i = 0; i < quantity; i++) {
        onAddToCart(offer)
      }
    }
    
    setAddedToCart(true)
    setTimeout(() => setAddedToCart(false), 2000)
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('medium')
  }

  const handleShare = () => {
    const shareText = `${offer.title}\n💰 ${Math.round(offer.discount_price).toLocaleString()} so'm (-${Math.round(offer.discount_percent)}%)\n🏪 ${offer.store_name || ''}`
    
    if (navigator.share) {
      navigator.share({
        title: offer.title,
        text: shareText,
        url: window.location.href
      }).catch(() => {})
    } else if (window.Telegram?.WebApp) {
      window.Telegram.WebApp.switchInlineQuery(shareText, ['users', 'groups'])
    }
  }

  // Calculate days until expiry
  const getExpiryInfo = () => {
    if (!offer?.expiry_date) return null
    
    try {
      const expiry = new Date(offer.expiry_date)
      const now = new Date()
      const diffTime = expiry - now
      const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24))
      
      if (diffDays < 0) return { text: "Muddati o'tgan", urgent: true }
      if (diffDays === 0) return { text: "Bugun tugaydi!", urgent: true }
      if (diffDays === 1) return { text: "Ertaga tugaydi", urgent: true }
      if (diffDays <= 3) return { text: `${diffDays} kundan keyin tugaydi`, urgent: true }
      if (diffDays <= 7) return { text: `${diffDays} kun qoldi`, urgent: false }
      return null
    } catch {
      return null
    }
  }

  const expiryInfo = getExpiryInfo()

  if (!offer) return null

  const totalPrice = offer.discount_price * quantity
  const savings = (offer.original_price - offer.discount_price) * quantity

  return (
    <div className="product-detail-page">
      {/* Header */}
      <div className="detail-header">
        <button className="back-btn" onClick={() => onNavigate?.('home')}>
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <path d="M15 18l-6-6 6-6" stroke="#181725" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>
        <button className="share-btn" onClick={handleShare}>
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <path d="M4 12v8a2 2 0 002 2h12a2 2 0 002-2v-8" stroke="#181725" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            <polyline points="16 6 12 2 8 6" stroke="#181725" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            <line x1="12" y1="2" x2="12" y2="15" stroke="#181725" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>
      </div>

      {/* Image Section */}
      <div 
        className="product-image-section"
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
      >
        {/* Discount Badge */}
        {offer.discount_percent > 0 && (
          <div className="discount-badge-large">
            -{Math.round(offer.discount_percent)}%
          </div>
        )}
        
        {/* Expiry Warning */}
        {expiryInfo && (
          <div className={`expiry-badge ${expiryInfo.urgent ? 'urgent' : ''}`}>
            ⏰ {expiryInfo.text}
          </div>
        )}

        <img
          src={images[currentImageIndex] || 'https://placehold.co/400x400/F5F5F5/999999?text=📷'}
          alt={offer.title}
          className="product-main-image"
          onError={(e) => { e.target.src = 'https://placehold.co/400x400/F5F5F5/999999?text=📷' }}
        />
        
        {images.length > 1 && (
          <div className="image-indicators">
            {images.map((_, idx) => (
              <span
                key={idx}
                className={`indicator ${idx === currentImageIndex ? 'active' : ''}`}
                onClick={() => setCurrentImageIndex(idx)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Product Info */}
      <div className="product-info">
        {/* Title & Store */}
        <div className="product-header-section">
          <h1 className="product-name">{offer.title}</h1>
          {offer.store_name && (
            <div className="store-info">
              <span className="store-icon">🏪</span>
              <span className="store-name-text">{offer.store_name}</span>
              {offer.store_address && (
                <span className="store-address-text"> • {offer.store_address}</span>
              )}
            </div>
          )}
        </div>

        {/* Price Section */}
        <div className="price-section">
          <div className="price-row">
            <div className="prices">
              <span className="current-price">{Math.round(offer.discount_price).toLocaleString()} so'm</span>
              {offer.original_price > offer.discount_price && (
                <span className="original-price">{Math.round(offer.original_price).toLocaleString()}</span>
              )}
            </div>
            {offer.quantity > 0 && (
              <span className="stock-badge">📦 {offer.quantity} dona</span>
            )}
          </div>
          
          {savings > 0 && (
            <div className="savings-info">
              💰 {quantity > 1 ? `Jami ${Math.round(savings).toLocaleString()} so'm tejaysiz` : `${Math.round(savings).toLocaleString()} so'm tejaysiz`}
            </div>
          )}
        </div>

        {/* Quantity & Total */}
        <div className="quantity-section">
          <div className="quantity-label">Miqdor:</div>
          <div className="quantity-controls">
            <button 
              className="qty-btn minus"
              onClick={() => handleQuantityChange(-1)}
              disabled={quantity <= 1}
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <line x1="5" y1="12" x2="19" y2="12" stroke="#B0B0B0" strokeWidth="2.5" strokeLinecap="round"/>
              </svg>
            </button>
            <span className="quantity-value">{quantity}</span>
            <button 
              className="qty-btn plus"
              onClick={() => handleQuantityChange(1)}
              disabled={quantity >= (offer.quantity || 99)}
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <line x1="12" y1="5" x2="12" y2="19" stroke="#53B175" strokeWidth="2.5" strokeLinecap="round"/>
                <line x1="5" y1="12" x2="19" y2="12" stroke="#53B175" strokeWidth="2.5" strokeLinecap="round"/>
              </svg>
            </button>
          </div>
          <div className="total-price">
            {Math.round(totalPrice).toLocaleString()} so'm
          </div>
        </div>

        {/* Description */}
        {offer.description && (
          <div className="description-section">
            <button 
              className="section-header"
              onClick={() => setShowDetails(!showDetails)}
            >
              <span className="section-title">📝 Tavsif</span>
              <svg 
                width="20" 
                height="20" 
                viewBox="0 0 24 24" 
                fill="none"
                className={`chevron ${showDetails ? 'open' : ''}`}
              >
                <path d="M6 9l6 6 6-6" stroke="#7C7C7C" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
            {showDetails && (
              <div className="description-content">
                <p>{offer.description}</p>
              </div>
            )}
          </div>
        )}

        {/* Category & Info Chips */}
        <div className="info-chips">
          {offer.category && (
            <span className="info-chip">
              🏷️ {offer.category}
            </span>
          )}
          {expiryInfo && (
            <span className={`info-chip ${expiryInfo.urgent ? 'urgent' : ''}`}>
              ⏰ {expiryInfo.text}
            </span>
          )}
        </div>

        {/* Add to Cart Button */}
        <button 
          className={`add-to-cart-btn ${addedToCart ? 'added' : ''}`} 
          onClick={handleAddToBasket}
          disabled={addedToCart}
        >
          {addedToCart ? (
            <>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <path d="M20 6L9 17l-5-5" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              Savatga qo'shildi!
            </>
          ) : (
            <>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <circle cx="9" cy="21" r="1" stroke="white" strokeWidth="2"/>
                <circle cx="20" cy="21" r="1" stroke="white" strokeWidth="2"/>
                <path d="M1 1h4l2.68 13.39a2 2 0 002 1.61h9.72a2 2 0 002-1.61L23 6H6" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              Savatga qo'shish • {Math.round(totalPrice).toLocaleString()} so'm
            </>
          )}
        </button>
      </div>
    </div>
  )
}

export default ProductDetailPage

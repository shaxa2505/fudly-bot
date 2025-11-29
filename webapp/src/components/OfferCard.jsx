import { memo } from 'react'
import './OfferCard.css'

const OfferCard = memo(function OfferCard({ offer, cartQuantity = 0, onAddToCart, onRemoveFromCart, onNavigate }) {
  
  const handleCardClick = () => {
    if (onNavigate) {
      onNavigate('product-detail', { offer, onAddToCart })
    }
  }

  const handleAddClick = (e) => {
    e.stopPropagation()
    onAddToCart?.(offer)
  }

  const handleRemoveClick = (e) => {
    e.stopPropagation()
    onRemoveFromCart?.(offer)
  }

  const discountPercent = Math.round(offer.discount_percent || 
    ((offer.original_price - offer.discount_price) / offer.original_price * 100))

  // Определяем ярлыки
  const isHit = discountPercent >= 25
  
  // Форматирование срока годности
  const formatExpiry = (date) => {
    if (!date) return null
    const d = new Date(date)
    const now = new Date()
    const diffDays = Math.ceil((d - now) / (1000 * 60 * 60 * 24))
    if (diffDays <= 0) return null
    if (diffDays <= 3) return `⚠️ ${diffDays} kun`
    if (diffDays <= 7) return `${diffDays} kun`
    return null
  }
  
  const expiryText = formatExpiry(offer.expiry_date)

  return (
    <div className="offer-card" onClick={handleCardClick}>
      <div className="card-image-container">
        <div className="card-badges">
          {discountPercent > 0 && (
            <span className="badge discount-badge">-{discountPercent}%</span>
          )}
          {isHit && <span className="badge hit-badge">🔥</span>}
        </div>
        {expiryText && (
          <span className="expiry-badge">{expiryText}</span>
        )}
        <img
          src={offer.photo || 'https://placehold.co/300x300/F5F5F5/CCCCCC?text=📷'}
          alt={offer.title}
          className="card-image"
          loading="lazy"
          onError={(e) => {
            e.target.src = 'https://placehold.co/300x300/F5F5F5/CCCCCC?text=📷'
          }}
        />
      </div>

      <div className="card-content">
        <div className="store-name">{offer.store_name}</div>
        <h3 className="offer-title">{offer.title}</h3>

        <div className="price-row">
          <div className="prices">
            <span className="current-price">
              {Math.round(offer.discount_price).toLocaleString()}
              <span className="currency">so'm</span>
            </span>
            {offer.original_price > offer.discount_price && (
              <span className="original-price">
                {Math.round(offer.original_price).toLocaleString()}
              </span>
            )}
          </div>
          
          {cartQuantity > 0 ? (
            <div className="quantity-controls">
              <button className="qty-btn minus" onClick={handleRemoveClick}>
                −
              </button>
              <span className="qty-value">{cartQuantity}</span>
              <button className="qty-btn plus" onClick={handleAddClick}>
                +
              </button>
            </div>
          ) : (
            <button className="add-btn" onClick={handleAddClick}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                <line x1="12" y1="5" x2="12" y2="19" stroke="white" strokeWidth="2.5" strokeLinecap="round"/>
                <line x1="5" y1="12" x2="19" y2="12" stroke="white" strokeWidth="2.5" strokeLinecap="round"/>
              </svg>
            </button>
          )}
        </div>
      </div>
    </div>
  )
})

export default OfferCard

import { memo, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useToast } from '../context/ToastContext'
import { PLACEHOLDER_IMAGE, resolveOfferImageUrl } from '../utils/imageUtils'
import './OfferCard.css'

const OfferCard = memo(function OfferCard({ offer, cartQuantity = 0, onAddToCart, onRemoveFromCart }) {
  const navigate = useNavigate()
  const { toast } = useToast()
  const [imageLoaded, setImageLoaded] = useState(false)
  const [imageError, setImageError] = useState(false)
  const [isAdding, setIsAdding] = useState(false)

  const handleCardClick = () => {
    navigate('/product', { state: { offer } })
  }

  // Get stock limit from offer
  const stockLimit = Number(offer.quantity ?? offer.stock ?? 0)
  const isOutOfStock = stockLimit <= 0
  const isMaxReached = !isOutOfStock && cartQuantity >= stockLimit
  const showStoreName = Boolean(offer.store_name || offer.store)
  const storeName = offer.store_name || offer.store || ''
  const metaText = stockLimit > 0 ? `Осталось: ${stockLimit}` : 'Забрать сегодня'

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
      toast?.success('Добавлено', 1800)
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

  // Get photo URL (handles Telegram file_id conversion)
  const photoUrl = resolveOfferImageUrl(offer)
  const fallbackUrl = PLACEHOLDER_IMAGE

  return (
    <div
      className={`offer-card ${cartQuantity > 0 ? 'in-cart' : ''} ${isOutOfStock ? 'out-of-stock' : ''}`}
      onClick={handleCardClick}
    >
      <div className="offer-media">
        {!imageLoaded && !imageError && (
          <div className="offer-image-skeleton shimmer" />
        )}
        <img
          src={photoUrl || fallbackUrl}
          alt={offer.title}
          className={`offer-image ${imageLoaded ? 'loaded' : ''}`}
          loading="lazy"
          decoding="async"
          onLoad={() => setImageLoaded(true)}
          onError={(e) => {
            if (!e.target.dataset.fallback) {
              e.target.dataset.fallback = 'true'
              e.target.src = fallbackUrl
              setImageError(true)
              setImageLoaded(true)
            }
          }}
        />
        <div className="offer-info">
          <h3 className="offer-title" title={offer.title}>
            {offer.title}
          </h3>
          <div className="offer-price-row">
            <span className="offer-price">
              {Math.round(priceValue).toLocaleString('ru-RU')}
              <span className="offer-currency"> so'm</span>
            </span>
            {hasOldPrice && (
              <span className="offer-old-price">
                {Math.round(originalPrice).toLocaleString('ru-RU')} so'm
              </span>
            )}
          </div>
          <div className={`offer-meta ${showStoreName ? 'has-store' : ''}`}>
            {showStoreName && (
              <span className="offer-store">{storeName}</span>
            )}
            <span className="offer-meta-text">{metaText}</span>
          </div>
        </div>
        {isOutOfStock && (
          <div className="offer-stock-overlay">Нет в наличии</div>
        )}
        <div className="offer-action">
          {cartQuantity > 0 ? (
            <div className="offer-counter" role="group" aria-label="Количество в корзине">
              <button
                type="button"
                className="offer-counter-btn"
                onClick={handleRemoveClick}
                aria-label="Уменьшить количество"
                disabled={cartQuantity <= 0}
              >
                -
              </button>
              <span className="offer-counter-value">{cartQuantity}</span>
              <button
                type="button"
                className="offer-counter-btn"
                onClick={handleAddClick}
                aria-label="Увеличить количество"
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
              aria-label="Добавить в корзину"
            >
              +
            </button>
          )}
        </div>
      </div>
    </div>
  )
})

export default OfferCard

import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/client'
import { useCart } from '../context/CartContext'
import { PLACEHOLDER_IMAGE, resolveOfferImageUrl } from '../utils/imageUtils'
import './FlashDeals.css'

// Calculate time remaining until expiry
const getTimeRemaining = (expiryDate) => {
  if (!expiryDate) return null

  const now = new Date()
  const expiry = new Date(expiryDate)
  const diff = expiry - now

  if (diff <= 0) return null

  const days = Math.floor(diff / (1000 * 60 * 60 * 24))
  const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60))

  if (days > 0) {
    return `${days} kun ${hours} soat`
  } else if (hours > 0) {
    return `${hours} soat`
  } else {
    const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60))
    return `${minutes} daqiqa`
  }
}

function FlashDeals({ city = '', region = '', district = '' }) {
  const navigate = useNavigate()
  const { addToCart, getQuantity } = useCart()
  const [deals, setDeals] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [pulseId, setPulseId] = useState(null)
  const pulseTimerRef = useRef(null)

  const loadDeals = useCallback(async () => {
    try {
      setLoading(true)
      const data = await api.getFlashDeals({ city, region, district, limit: 10 })
      setDeals(data || [])
      setError(null)
    } catch (err) {
      console.error('Error loading flash deals:', err)
      setError('Yuklab bo\'lmadi')
    } finally {
      setLoading(false)
    }
  }, [city, region, district])

  useEffect(() => {
    loadDeals()
  }, [loadDeals])

  const handleAddToCart = (e, offer) => {
    e.stopPropagation()
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('medium')
    addToCart(offer)
    if (pulseTimerRef.current) {
      clearTimeout(pulseTimerRef.current)
    }
    setPulseId(offer?.id || null)
    pulseTimerRef.current = setTimeout(() => setPulseId(null), 380)
  }

  useEffect(() => () => {
    if (pulseTimerRef.current) {
      clearTimeout(pulseTimerRef.current)
    }
  }, [])

  // Don't render if no deals or error
  if (!loading && (error || deals.length === 0)) {
    return null
  }

  return (
    <div className="flash-deals">
      <div className="flash-deals-header">
        <div className="flash-deals-title">
          <span className="flash-icon">⚡</span>
          <h3>Flash chegirmalar</h3>
          <span className="flash-badge">TEZKOR</span>
        </div>
        <button
          className="flash-deals-more"
          onClick={() => navigate('/offers?sort=discount')}
        >
          Hammasi →
        </button>
      </div>

      <div className="flash-deals-scroll">
        {loading ? (
          // Skeleton loading
          Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="flash-card skeleton">
              <div className="flash-card-image skeleton-box" />
              <div className="flash-card-info">
                <div className="skeleton-text" style={{ width: '80%' }} />
                <div className="skeleton-text" style={{ width: '60%' }} />
              </div>
            </div>
          ))
        ) : (
          deals.map((deal, index) => {
            const timeLeft = getTimeRemaining(deal.expiry_date)
            const inCart = getQuantity(deal.id) > 0
            const photoUrl = resolveOfferImageUrl(deal) || PLACEHOLDER_IMAGE
            const isPulsing = pulseId === deal.id
            const delay = `${Math.min(index, 6) * 40}ms`

            return (
              <div
                key={deal.id}
                className={`flash-card animate-in ${isPulsing ? 'just-added' : ''}`}
                style={{ animationDelay: delay }}
                onClick={() => navigate('/product', { state: { offer: deal } })}
              >
                <div className="flash-card-image">
                  <img
                    src={photoUrl}
                    alt={deal.title}
                    loading="lazy"
                    decoding="async"
                    onError={(e) => {
                      e.target.src = PLACEHOLDER_IMAGE
                    }}
                  />
                  {deal.discount_percent > 0 && (
                    <span className="flash-discount-badge">
                      -{Math.round(deal.discount_percent)}%
                    </span>
                  )}
                </div>

                <div className="flash-card-info">
                  <span className="flash-card-title">{deal.title}</span>

                  <div className="flash-card-prices">
                    <span className="flash-price-current">
                      {Math.round(deal.discount_price).toLocaleString()}
                    </span>
                    {deal.original_price > deal.discount_price && (
                      <span className="flash-price-old">
                        {Math.round(deal.original_price).toLocaleString()}
                      </span>
                    )}
                  </div>

                  {timeLeft && (
                    <div className="flash-timer">
                      <span className="flash-timer-icon">⏰</span>
                      <span className="flash-timer-text">{timeLeft}</span>
                    </div>
                  )}

                  <button
                    className={`flash-add-btn ${inCart ? 'in-cart' : ''} ${isPulsing ? 'pulse' : ''}`}
                    onClick={(e) => handleAddToCart(e, deal)}
                  >
                    {inCart ? '✓ Savatda' : '+ Qo\'shish'}
                  </button>
                </div>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}

export default FlashDeals

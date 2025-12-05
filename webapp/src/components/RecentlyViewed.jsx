import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/client'
import './RecentlyViewed.css'

function RecentlyViewed() {
  const navigate = useNavigate()
  const [offers, setOffers] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const loadRecentlyViewed = async () => {
      try {
        const userId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id
        if (userId) {
          const data = await api.getRecentlyViewed(userId, 10)
          setOffers(data || [])
        }
      } catch (error) {
        console.error('Error loading recently viewed:', error)
      } finally {
        setLoading(false)
      }
    }

    loadRecentlyViewed()
  }, [])

  if (loading || offers.length === 0) {
    return null
  }

  return (
    <div className="recently-viewed-section">
      <div className="recently-viewed-header">
        <h3 className="recently-viewed-title">⏱ So'nggi ko'rilgan</h3>
        <button
          className="recently-viewed-see-all"
          onClick={() => navigate('/recently-viewed')}
        >
          Hammasi
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
            <path d="M9 18l6-6-6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>
      </div>
      <div className="recently-viewed-scroll">
        {offers.map(offer => (
          <div
            key={`rv-${offer.id}`}
            className="recently-viewed-card"
            onClick={() => navigate(`/product/${offer.id}`, { state: { offer } })}
          >
            <div className="recently-viewed-card-image">
              <img
                src={api.getPhotoUrl(offer.photo) || offer.photo_id || 'https://placehold.co/120x120/F8F9FA/94A3B8?text=🛒'}
                alt={offer.name || offer.title}
                loading="lazy"
                onError={(e) => {
                  e.target.src = 'https://placehold.co/120x120/F8F9FA/94A3B8?text=🛒'
                }}
              />
            </div>
            <div className="recently-viewed-card-info">
              <span className="recently-viewed-card-price">
                {Math.round(offer.price || offer.discount_price || 0).toLocaleString()} so'm
              </span>
              <span className="recently-viewed-card-title">
                {offer.name || offer.title}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default RecentlyViewed

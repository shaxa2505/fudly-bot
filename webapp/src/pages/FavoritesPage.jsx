import { useNavigate } from 'react-router-dom'
import { Heart, Home, Sparkles } from 'lucide-react'
import { useFavorites } from '../context/FavoritesContext'
import { useCart } from '../context/CartContext'
import BottomNav from '../components/BottomNav'
import './FavoritesPage.css'

function FavoritesPage() {
  const navigate = useNavigate()
  const { favorites, removeFromFavorites, isEmpty, favoritesCount } = useFavorites()
  const { addToCart, getQuantity, cartCount } = useCart()

  const handleAddToCart = (offer) => {
    addToCart(offer)
  }

  if (isEmpty) {
    return (
      <div className="favorites-page">
        <header className="favorites-header">
          <button className="back-btn" onClick={() => navigate(-1)} aria-label="Orqaga">
            <-
          </button>
          <h1>Sevimlilar</h1>
          <div style={{ width: 44 }} />
        </header>

        <div className="favorites-empty empty-state">
          <div className="empty-state-icon">
            <Heart size={80} strokeWidth={1.5} color="#E53935" aria-hidden="true" />
          </div>
          <h3 className="empty-state-title">Sevimlilar bo'sh</h3>
          <p className="empty-state-description">
            Yoqtirgan mahsulotlaringizni saqlash uchun yurak belgisini bosing.
            Keyinroq ularni osongina topishingiz mumkin!
          </p>
          <button className="btn-primary" onClick={() => navigate('/')}>
            <Home size={20} strokeWidth={2} aria-hidden="true" />
            <span>Bosh sahifaga o'tish</span>
          </button>
          <button className="btn-secondary" onClick={() => navigate('/stores')}>
            <Sparkles size={20} strokeWidth={2} aria-hidden="true" />
            <span>Yangi mahsulotlar</span>
          </button>
        </div>

        <BottomNav currentPage="favorites" cartCount={cartCount} />
      </div>
    )
  }

  return (
    <div className="favorites-page">
      <header className="favorites-header">
        <button className="back-btn" onClick={() => navigate(-1)} aria-label="Orqaga">
          <-
        </button>
        <h1>Sevimlilar ({favoritesCount})</h1>
        <div style={{ width: 44 }} />
      </header>

      <div className="favorites-list">
        {favorites.map(offer => (
          <div key={offer.id} className="favorite-card">
            <img
              src={offer.photo || 'https://placehold.co/100x100/F5F5F5/CCCCCC?text=IMG'}
              alt={offer.title}
              className="favorite-image"
              onClick={() => navigate('/product', { state: { offer } })}
              onError={(e) => { e.target.src = 'https://placehold.co/100x100/F5F5F5/CCCCCC?text=IMG' }}
            />

            <div className="favorite-info" onClick={() => navigate('/product', { state: { offer } })}>
              <h3 className="favorite-title">{offer.title}</h3>
              {offer.store_name && (
                <p className="favorite-store">Do'kon: {offer.store_name}</p>
              )}
              <div className="favorite-prices">
                <span className="favorite-price">
                  {Math.round(offer.discount_price).toLocaleString()} so'm
                </span>
                {offer.original_price > offer.discount_price && (
                  <span className="favorite-original">
                    {Math.round(offer.original_price).toLocaleString()}
                  </span>
                )}
              </div>
            </div>

            <div className="favorite-actions">
              <button
                className="remove-favorite-btn"
                onClick={() => removeFromFavorites(offer.id)}
                aria-label="O'chirish"
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="#E53935">
                  <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
                </svg>
              </button>

              {getQuantity(offer.id) > 0 ? (
                <span className="in-cart-badge">
                  Savatda ({getQuantity(offer.id)})
                </span>
              ) : (
                <button
                  className="add-to-cart-btn"
                  onClick={() => handleAddToCart(offer)}
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                    <line x1="12" y1="5" x2="12" y2="19" stroke="white" strokeWidth="2.5" strokeLinecap="round"/>
                    <line x1="5" y1="12" x2="19" y2="12" stroke="white" strokeWidth="2.5" strokeLinecap="round"/>
                  </svg>
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      <BottomNav currentPage="favorites" cartCount={cartCount} />
    </div>
  )
}

export default FavoritesPage

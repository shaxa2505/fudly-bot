import { useState, useEffect } from 'react'
import api from '../api/client'
import OfferCard from '../components/OfferCard'
import BottomNav from '../components/BottomNav'
import './FavoritesPage.css'

function FavoritesPage({ onNavigate }) {
  const [favorites, setFavorites] = useState([])
  const [loading, setLoading] = useState(true)
  const [favoriteIds, setFavoriteIds] = useState(new Set())

  useEffect(() => {
    loadFavorites()
  }, [])

  const loadFavorites = async () => {
    setLoading(true)
    try {
      const data = await api.getFavorites()
      setFavorites(data)
      setFavoriteIds(new Set(data.map(o => o.id)))
    } catch (error) {
      console.error('Error loading favorites:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleRemoveFavorite = async (offerId) => {
    try {
      await api.removeFavorite(offerId)
      setFavorites(prev => prev.filter(o => o.id !== offerId))
      setFavoriteIds(prev => {
        const next = new Set(prev)
        next.delete(offerId)
        return next
      })
    } catch (error) {
      console.error('Error removing favorite:', error)
    }
  }

  const addToCart = (offer) => {
    const saved = localStorage.getItem('fudly_cart')
    const cart = saved ? new Map(Object.entries(JSON.parse(saved))) : new Map()

    const current = cart.get(String(offer.id)) || 0
    cart.set(String(offer.id), current + 1)

    localStorage.setItem('fudly_cart', JSON.stringify(Object.fromEntries(cart)))
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('medium')
    window.Telegram?.WebApp?.showAlert?.('Savatga qo\'shildi!')
  }

  if (loading) {
    return (
      <div className="favorites-page">
        <header className="page-header">
          <button className="back-btn" onClick={() => onNavigate('home')}>
            ← Orqaga
          </button>
          <h1>Saqlanganlar</h1>
          <div></div>
        </header>
        <div className="loading-state">Yuklanmoqda...</div>
        <BottomNav currentPage="favorites" onNavigate={onNavigate} favoritesCount={0} />
      </div>
    )
  }

  if (favorites.length === 0) {
    return (
      <div className="favorites-page">
        <header className="page-header">
          <button className="back-btn" onClick={() => onNavigate('home')}>
            ← Orqaga
          </button>
          <h1>Saqlanganlar</h1>
          <div></div>
        </header>

        <div className="empty-state">
          <div className="empty-icon">❤️</div>
          <h2>Saqlanganlar bo'sh</h2>
          <p>Mahsulotlarni saqlash uchun yurak belgisini bosing</p>
          <button className="primary-btn" onClick={() => onNavigate('home')}>
            Katalogga o'tish
          </button>
        </div>

        <BottomNav currentPage="favorites" onNavigate={onNavigate} favoritesCount={0} />
      </div>
    )
  }

  return (
    <div className="favorites-page">
      <header className="page-header">
        <button className="back-btn" onClick={() => onNavigate('home')}>
          ← Orqaga
        </button>
        <h1>Saqlanganlar ({favorites.length})</h1>
        <div></div>
      </header>

      <div className="favorites-grid">
        {favorites.map(offer => (
          <OfferCard
            key={offer.id}
            offer={offer}
            isFavorite={true}
            onToggleFavorite={() => handleRemoveFavorite(offer.id)}
            onAddToCart={() => addToCart(offer)}
          />
        ))}
      </div>

      <BottomNav currentPage="favorites" onNavigate={onNavigate} favoritesCount={favorites.length} />
    </div>
  )
}

export default FavoritesPage

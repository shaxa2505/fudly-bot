import './OfferCard.css'

function OfferCard({ offer, isFavorite, onToggleFavorite, onAddToCart }) {
  return (
    <div className="offer-card">
      <div className="card-image-container">
        <img
          src={offer.photo || 'https://via.placeholder.com/300x300?text=No+Image'}
          alt={offer.title}
          className="card-image"
          loading="lazy"
        />
        <div className="discount-badge">-{Math.round(offer.discount_percent)}%</div>
      </div>

      <div className="card-content">
        <div className="store-badge">{offer.store_name}</div>
        <h3 className="offer-title">{offer.title}</h3>

        <div className="price-container">
          <div className="price-row">
            <span className="current-price">
              {Math.round(offer.discount_price).toLocaleString()} <span className="currency">сум</span>
            </span>
          </div>
          <span className="original-price">
            {Math.round(offer.original_price).toLocaleString()} <span className="currency-small">сум</span>
          </span>
        </div>

        <button
          className="add-to-cart-btn"
          onClick={(e) => {
            e.stopPropagation()
            onAddToCart()
          }}
        >
          Savatga
        </button>
      </div>
    </div>
  )
}

export default OfferCard

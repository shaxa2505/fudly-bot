const PopularSection = ({ isVisible, offers, loading, onOfferClick, onScrollToList }) => {
  if (!isVisible) {
    return null
  }

  return (
    <div className="popular-section">
      <div className="popular-header">
        <h3 className="popular-title">🔥 Ommabop takliflar</h3>
        <button className="popular-see-all" onClick={onScrollToList}>
          Hammasi
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
            <path d="M9 18l6-6-6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>
      </div>
      <div className="popular-scroll">
        {loading && offers.length === 0 ? (
          Array.from({ length: 4 }).map((_, index) => (
            <div key={`pop-skeleton-${index}`} className="popular-card skeleton">
              <div className="popular-card-image skeleton-box" />
              <div className="popular-card-info">
                <div className="skeleton-text" style={{ width: '70%', height: '14px' }} />
                <div className="skeleton-text" style={{ width: '90%', height: '12px' }} />
              </div>
            </div>
          ))
        ) : (
          offers.slice(0, 8).map((offer, index) => (
            <div
              key={`pop-${offer.id}`}
              className="popular-card animate-in"
              style={{ animationDelay: `${index * 50}ms` }}
              onClick={() => onOfferClick(offer)}
            >
              <div className="popular-card-image">
                <img
                  src={offer.photo || 'https://placehold.co/300x300/F5F5F5/CCCCCC?text=📷'}
                  alt={offer.title}
                  loading="lazy"
                  decoding="async"
                  width="300"
                  height="300"
                  onError={(event) => {
                    event.target.src = 'https://placehold.co/300x300/F5F5F5/CCCCCC?text=📷'
                  }}
                />
                {offer.discount_percent > 0 && (
                  <span className="popular-card-badge">-{Math.round(offer.discount_percent)}%</span>
                )}
              </div>
              <div className="popular-card-info">
                <span className="popular-card-price">{Math.round(offer.discount_price || 0).toLocaleString()} so'm</span>
                <span className="popular-card-title">{offer.title}</span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

export default PopularSection

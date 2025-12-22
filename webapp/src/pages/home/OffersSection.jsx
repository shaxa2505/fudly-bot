import OfferCard from '../../components/OfferCard'
import OfferCardSkeleton from '../../components/OfferCardSkeleton'

const OffersSection = ({
  selectedCategory,
  categories,
  offers,
  loading,
  isFiltered,
  onResetFilters,
  showingAllCities,
  city,
  getQuantity,
  onAddToCart,
  onRemoveFromCart,
  hasMore,
  observerRef,
}) => {
  const sectionTitle = selectedCategory === 'all'
    ? 'Barcha takliflar'
    : categories.find(c => c.id === selectedCategory)?.name

  return (
    <>
      <div className="section-header">
        <h2 className="section-title">{sectionTitle}</h2>
        <span className="offers-count">{offers.length} ta</span>
      </div>

      {showingAllCities && offers.length > 0 && (
        <div className="all-cities-banner">
          <span className="all-cities-icon">🌍</span>
          <span className="all-cities-text">
            {city} da mahsulot yo'q. Barcha shaharlardan ko'rsatilmoqda
          </span>
        </div>
      )}

      <div className="offers-grid">
        {loading && offers.length === 0 ? (
          Array.from({ length: 6 }).map((_, index) => (
            <OfferCardSkeleton key={index} />
          ))
        ) : offers.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">🔍</div>
            <h3 className="empty-state-title">Hech narsa topilmadi</h3>
            <p className="empty-state-text">Boshqa so'z bilan qidiring</p>
            <p className="empty-state-hint">Maslahat: qisqa so'z ishlating yoki toifani almashtiring.</p>
            {isFiltered && (
              <div className="empty-state-actions">
                <button className="empty-state-btn" onClick={onResetFilters}>
                  Filtrlarni tozalash
                </button>
              </div>
            )}
          </div>
        ) : (
          offers.map((offer, index) => {
            const offerKey = offer.id || offer.offer_id || `${offer.store_id || 'store'}-${offer.title || 'offer'}-${index}`
            return (
              <div
                key={offerKey}
                className="offer-card-wrapper"
              >
                <OfferCard
                  offer={offer}
                  cartQuantity={getQuantity(offer.id || offer.offer_id)}
                  onAddToCart={onAddToCart}
                  onRemoveFromCart={onRemoveFromCart}
                />
              </div>
            )
          })
        )}
      </div>

      {hasMore && (
        <div ref={observerRef} className="loading-more">
          {loading && <div className="spinner" />}
        </div>
      )}
    </>
  )
}

export default OffersSection

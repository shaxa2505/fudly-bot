import './OfferCardSkeleton.css'

function OfferCardSkeleton() {
  return (
    <div className="offer-card-skeleton">
      <div className="skeleton-image shimmer" />
      <div className="skeleton-body">
        <div className="skeleton-row">
          <div className="skeleton-title-group">
            <div className="skeleton-line skeleton-title shimmer" />
            <div className="skeleton-line skeleton-location shimmer" />
          </div>
          <div className="skeleton-price-group">
            <div className="skeleton-line skeleton-price shimmer" />
            <div className="skeleton-line skeleton-old-price shimmer" />
          </div>
        </div>
        <div className="skeleton-footer">
          <div className="skeleton-line skeleton-meta shimmer" />
          <div className="skeleton-button shimmer" />
        </div>
      </div>
    </div>
  )
}

export default OfferCardSkeleton

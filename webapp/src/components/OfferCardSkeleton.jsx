import './OfferCardSkeleton.css'

function OfferCardSkeleton() {
  return (
    <div className="offer-card-skeleton">
      <div className="skeleton-image shimmer" />
      <div className="skeleton-body">
        <div className="skeleton-line skeleton-title shimmer" />
        <div className="skeleton-line skeleton-location shimmer" />
        <div className="skeleton-footer">
          <div className="skeleton-price-block">
            <div className="skeleton-line skeleton-old-price shimmer" />
            <div className="skeleton-line skeleton-price shimmer" />
          </div>
          <div className="skeleton-button shimmer" />
        </div>
      </div>
    </div>
  )
}

export default OfferCardSkeleton

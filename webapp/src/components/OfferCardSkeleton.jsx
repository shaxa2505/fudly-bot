import './OfferCardSkeleton.css'

function OfferCardSkeleton() {
  return (
    <div className="offer-card-skeleton">
      <div className="skeleton-image shimmer">
        <div className="skeleton-image-tag shimmer" />
        <div className="skeleton-image-btn shimmer" />
      </div>
      <div className="skeleton-body">
        <div className="skeleton-top-row">
          <div className="skeleton-line skeleton-store shimmer" />
          <div className="skeleton-line skeleton-time shimmer" />
        </div>
        <div className="skeleton-line skeleton-title shimmer" />
        <div className="skeleton-footer">
          <div className="skeleton-price-block">
            <div className="skeleton-line skeleton-price shimmer" />
            <div className="skeleton-line skeleton-old-price shimmer" />
          </div>
          <div className="skeleton-button shimmer" />
        </div>
      </div>
    </div>
  )
}

export default OfferCardSkeleton

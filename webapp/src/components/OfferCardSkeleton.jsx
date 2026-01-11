import './OfferCardSkeleton.css'

function OfferCardSkeleton() {
  return (
    <div className="offer-card-skeleton">
      <div className="skeleton-image shimmer" />
      <div className="skeleton-content">
        <div className="skeleton-row">
          <div className="skeleton-price shimmer" />
          <div className="skeleton-button shimmer" />
        </div>
        <div className="skeleton-title shimmer" />
        <div className="skeleton-title-short shimmer" />
      </div>
    </div>
  )
}

export default OfferCardSkeleton

import './OfferCardSkeleton.css'

function OfferCardSkeleton() {
  return (
    <div className="offer-card-skeleton">
      <div className="skeleton-image shimmer">
        <div className="skeleton-action shimmer" />
      </div>
      <div className="skeleton-content">
        <div className="skeleton-price shimmer" />
        <div className="skeleton-title shimmer" />
        <div className="skeleton-title-short shimmer" />
      </div>
    </div>
  )
}

export default OfferCardSkeleton

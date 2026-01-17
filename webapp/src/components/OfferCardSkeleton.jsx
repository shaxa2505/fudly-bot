import './OfferCardSkeleton.css'

function OfferCardSkeleton() {
  return (
    <div className="offer-card-skeleton">
      <div className="skeleton-media shimmer">
        <div className="skeleton-action shimmer" />
      </div>
      <div className="skeleton-body">
        <div className="skeleton-line skeleton-price shimmer" />
        <div className="skeleton-line skeleton-title shimmer" />
        <div className="skeleton-line skeleton-title-short shimmer" />
        <div className="skeleton-line skeleton-store shimmer" />
      </div>
    </div>
  )
}

export default OfferCardSkeleton

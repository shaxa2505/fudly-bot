/**
 * Pull-to-Refresh Component
 * Визуальный индикатор для pull-to-refresh
 */

import './PullToRefresh.css'

function PullToRefresh({ isRefreshing, pullDistance, progress }) {
  const isVisible = pullDistance > 10 || isRefreshing

  return (
    <div
      className={`ptr-container ${isVisible ? 'visible' : ''} ${isRefreshing ? 'refreshing' : ''}`}
      style={{
        height: isRefreshing ? 60 : pullDistance,
        opacity: Math.min(progress * 1.5, 1)
      }}
    >
      <div className="ptr-content">
        <div
          className={`ptr-spinner ${isRefreshing ? 'spinning' : ''}`}
          style={{
            transform: `rotate(${progress * 360}deg) scale(${0.5 + progress * 0.5})`
          }}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <path d="M23 4v6h-6" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M1 20v-6h6" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </div>
        <span className="ptr-text">
          {isRefreshing
            ? 'Yangilanmoqda...'
            : progress >= 1
              ? 'Qo\'yib yuboring'
              : 'Yangilash uchun torting'
          }
        </span>
      </div>
    </div>
  )
}

export default PullToRefresh

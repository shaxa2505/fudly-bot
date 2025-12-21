import { memo } from 'react'
import './PageLoader.css'

/**
 * Page Loader - Shown during lazy load of pages
 *
 * Features:
 * - Animated spinner
 * - Optional message
 * - Smooth fade in/out
 */
const PageLoader = memo(function PageLoader({ message }) {
  return (
    <div className="page-loader">
      <div className="page-loader-content">
        <div className="page-loader-spinner">
          <div className="spinner-ring"></div>
          <div className="spinner-icon">F</div>
        </div>
        {message && <p className="page-loader-message">{message}</p>}
      </div>
    </div>
  )
})

/**
 * Full Screen Loading - For initial app load
 */
export const LoadingScreen = memo(function LoadingScreen() {
  return (
    <div className="loading-screen">
      <div className="loading-screen-content">
        <div className="loading-logo">
          <span className="loading-logo-emoji">F</span>
          <h1 className="loading-logo-text">Fudly</h1>
        </div>
        <div className="loading-bar">
          <div className="loading-bar-fill"></div>
        </div>
        <p className="loading-hint">Yuklanmoqda...</p>
      </div>
    </div>
  )
})

/**
 * Skeleton Loader - For content placeholders
 */
export const SkeletonBox = memo(function SkeletonBox({
  width = '100%',
  height = '20px',
  borderRadius = '8px',
  className = ''
}) {
  return (
    <div
      className={`skeleton-box ${className}`}
      style={{ width, height, borderRadius }}
    />
  )
})

export default PageLoader

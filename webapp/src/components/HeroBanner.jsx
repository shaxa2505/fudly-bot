import React, { useState, useEffect, useCallback, memo, useRef } from 'react'
import './HeroBanner.css'

const BANNERS = [
  {
    id: 1,
    title: 'Yangi ichimliklar',
    subtitle: 'Har kuni yangilanadi',
    badge: 'Ichimliklar',
    cta: "Tanlash",
    image: '/images/hero/juice.jpg',
    position: 'center bottom',
    accent: '#F97316',
    category: 'drinks'
  },
  {
    id: 2,
    title: "Go'sht tanlovi",
    subtitle: 'Grill uchun',
    badge: "Go'sht",
    cta: "Ko'rish",
    image: '/images/hero/steak.jpg',
    position: 'center',
    accent: '#EF4444',
    category: 'meat'
  },
]

const HeroBanner = memo(function HeroBanner({ onCategorySelect }) {
  const [currentIndex, setCurrentIndex] = useState(0)
  const [isAutoPlaying, setIsAutoPlaying] = useState(true)
  const [touchStart, setTouchStart] = useState(null)
  const [touchEnd, setTouchEnd] = useState(null)
  const resumeTimeoutRef = useRef(null)

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (resumeTimeoutRef.current) {
        clearTimeout(resumeTimeoutRef.current)
      }
    }
  }, [])

  // Auto-play carousel
  useEffect(() => {
    if (!isAutoPlaying) return

    const interval = setInterval(() => {
      setCurrentIndex(prev => (prev + 1) % BANNERS.length)
    }, 4000)

    return () => clearInterval(interval)
  }, [isAutoPlaying])

  // Handle swipe
  const minSwipeDistance = 50

  const onTouchStart = (e) => {
    setTouchEnd(null)
    setTouchStart(e.targetTouches[0].clientX)
    setIsAutoPlaying(false)
  }

  const onTouchMove = (e) => {
    setTouchEnd(e.targetTouches[0].clientX)
  }

  const onTouchEnd = () => {
    if (!touchStart || !touchEnd) {
      setIsAutoPlaying(true)
      return
    }

    const distance = touchStart - touchEnd
    const isLeftSwipe = distance > minSwipeDistance
    const isRightSwipe = distance < -minSwipeDistance

    if (isLeftSwipe) {
      setCurrentIndex(prev => (prev + 1) % BANNERS.length)
    } else if (isRightSwipe) {
      setCurrentIndex(prev => (prev - 1 + BANNERS.length) % BANNERS.length)
    }

    // Resume auto-play after 5 seconds
    if (resumeTimeoutRef.current) clearTimeout(resumeTimeoutRef.current)
    resumeTimeoutRef.current = setTimeout(() => setIsAutoPlaying(true), 5000)
  }

  const handleBannerClick = useCallback(() => {
    const banner = BANNERS[currentIndex]
    if (onCategorySelect && banner.category) {
      // Haptic feedback
      window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light')
      onCategorySelect(banner.category)
    }
  }, [currentIndex, onCategorySelect])

  const handleDotClick = useCallback((index) => {
    setCurrentIndex(index)
    setIsAutoPlaying(false)
    // Resume auto-play after 5 seconds
    if (resumeTimeoutRef.current) clearTimeout(resumeTimeoutRef.current)
    resumeTimeoutRef.current = setTimeout(() => setIsAutoPlaying(true), 5000)
  }, [])

  const currentBanner = BANNERS[currentIndex]

  return (
    <div className="hero-banner-container">
      <div
        className="hero-banner"
        style={{
          '--banner-accent': currentBanner.accent,
          '--banner-image': `url(${currentBanner.image})`,
          '--banner-position': currentBanner.position || 'center',
        }}
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
        onClick={handleBannerClick}
      >
        <div className="hero-banner__image" aria-hidden="true" />
        <div className="hero-banner__overlay" aria-hidden="true" />
        <div className="banner-content">
          <div className="banner-kicker">
            <span className="banner-badge">{currentBanner.badge || 'Tanlov'}</span>
            <span className="banner-subtitle">{currentBanner.subtitle}</span>
          </div>
          <h2 className="banner-title">{currentBanner.title}</h2>
          <button className="banner-cta" type="button">
            {currentBanner.cta || "Ko'rish"}
            <span className="cta-arrow" aria-hidden="true">&gt;</span>
          </button>
        </div>
      </div>

      {/* Dots indicator */}
      <div className="banner-dots">
        {BANNERS.map((_, index) => (
          <button
            key={index}
            className={`banner-dot ${index === currentIndex ? 'active' : ''}`}
            onClick={() => handleDotClick(index)}
            aria-label={`Banner ${index + 1}`}
          />
        ))}
      </div>
    </div>
  )
})

export default HeroBanner

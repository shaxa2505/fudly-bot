import React, { useState, useEffect, useCallback, memo, useRef } from 'react'
import './HeroBanner.css'

const BANNERS = [
  {
    id: 1,
    title: "Ichimliklar To'plami",
    subtitle: "Siz uchun maxsus saralangan premium sharbatlar",
    badge: "Kun taklifi",
    image: '/images/hero/drinks.jpeg',
    position: 'center bottom',
    category: 'drinks'
  },
  {
    id: 2,
    title: "Pishiriqlar To'plami",
    subtitle: "Yangi pishgan mahsulotlar har kuni",
    badge: "Kun taklifi",
    image: '/images/hero/dairy.jpeg',
    position: 'center',
    category: 'bakery'
  },
  {
    id: 3,
    title: "Go'sht Mahsulotlari",
    subtitle: "Sifatli va yangi mahsulotlar",
    badge: "Kun taklifi",
    image: '/images/hero/meat.jpeg',
    position: 'center',
    category: 'meat'
  },
  {
    id: 4,
    title: 'Mevalar To\'plami',
    subtitle: "Tabiiy va foydali mahsulotlar",
    badge: "Kun taklifi",
    image: '/images/hero/produce.jpeg',
    position: 'center',
    category: 'fruits'
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
          <span className="banner-badge">{currentBanner.badge}</span>
          <h2 className="banner-title">{currentBanner.title}</h2>
          <p className="banner-subtitle">{currentBanner.subtitle}</p>
        </div>
        <div className="banner-indicators" role="tablist" aria-label="Bannerlar">
          {BANNERS.map((_, index) => (
            <button
              key={index}
              className={`banner-indicator ${index === currentIndex ? 'active' : ''}`}
              onClick={() => handleDotClick(index)}
              aria-label={`Banner ${index + 1}`}
              aria-selected={index === currentIndex}
              role="tab"
            />
          ))}
        </div>
      </div>
    </div>
  )
})

export default HeroBanner

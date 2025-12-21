import React, { useState, useEffect, useCallback, memo, useRef } from 'react'
import { Milk, Croissant, Coffee as Beverage, Apple } from 'lucide-react'
import './HeroBanner.css'

const BANNERS = [
  {
    id: 1,
    title: '50% gacha chegirma',
    subtitle: 'Sut mahsulotlari',
    icon: Milk,
    gradient: 'linear-gradient(135deg, #0F766E 0%, #0B5E57 100%)',
    category: 'dairy'
  },
  {
    id: 2,
    title: "Yangi kelgan taomlar",
    subtitle: "Eng sara mahsulotlar",
    icon: Croissant,
    gradient: 'linear-gradient(135deg, #F97316 0%, #EA580C 100%)',
    category: 'bakery'
  },
  {
    id: 3,
    title: "Ichimliklar aksiyasi",
    subtitle: "30% gacha chegirma",
    icon: Beverage,
    gradient: 'linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%)',
    category: 'drinks'
  },
  {
    id: 4,
    title: "Yangi mevalar",
    subtitle: "Har kuni yangilanadi",
    icon: Apple,
    gradient: 'linear-gradient(135deg, #22C55E 0%, #16A34A 100%)',
    category: 'fruits'
  }
]

const HeroBanner = memo(function HeroBanner({ onCategorySelect }) {
  const [currentIndex, setCurrentIndex] = useState(0)
  const [isAutoPlaying, setIsAutoPlaying] = useState(true)
  const [touchStart, setTouchStart] = useState(null)
  const [touchEnd, setTouchEnd] = useState(null)
  const resumeTimeoutRef = React.useRef(null)

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
        style={{ background: currentBanner.gradient }}
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
        onClick={handleBannerClick}
      >
        <div className="banner-content">
          <div className="banner-text">
            <h2 className="banner-title">{currentBanner.title}</h2>
            <p className="banner-subtitle">{currentBanner.subtitle}</p>
              <span className="banner-cta">Ko'rish {'->'}</span>
          </div>
          <div className="banner-icon">
            {(() => {
              const IconComponent = currentBanner.icon
              return <IconComponent size={80} strokeWidth={2} color="white" aria-hidden="true" />
            })()}
          </div>
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

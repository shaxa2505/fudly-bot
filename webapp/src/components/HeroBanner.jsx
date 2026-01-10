import React, { useState, useEffect, useCallback, memo, useRef } from 'react'
import { Milk, Croissant, Coffee as Beverage, Apple } from 'lucide-react'
import './HeroBanner.css'

const BANNERS = [
  {
    id: 1,
    title: '50% gacha chegirma',
    subtitle: 'Sut mahsulotlari',
    badge: 'Chegirma',
    cta: "Taklifni ko'rish",
    icon: Milk,
    accent: '#F97316',
    glow: 'rgba(249, 115, 22, 0.35)',
    background: 'linear-gradient(140deg, #0F766E 0%, #0A5C54 50%, #064E48 100%)',
    category: 'dairy'
  },
  {
    id: 2,
    title: 'Yangi kelgan taomlar',
    subtitle: 'Eng sara mahsulotlar',
    badge: 'Yangi',
    cta: 'Katalog',
    icon: Croissant,
    accent: '#F59E0B',
    glow: 'rgba(245, 158, 11, 0.4)',
    background: 'linear-gradient(140deg, #F97316 0%, #EA580C 55%, #C2410C 100%)',
    category: 'bakery'
  },
  {
    id: 3,
    title: 'Ichimliklar aksiyasi',
    subtitle: '30% gacha chegirma',
    badge: 'Aksiya',
    cta: "Ko'rish",
    icon: Beverage,
    accent: '#38BDF8',
    glow: 'rgba(56, 189, 248, 0.35)',
    background: 'linear-gradient(140deg, #1D4ED8 0%, #1E40AF 55%, #1E3A8A 100%)',
    category: 'drinks'
  },
  {
    id: 4,
    title: 'Yangi mevalar',
    subtitle: 'Har kuni yangilanadi',
    badge: 'Fresh',
    cta: 'Tanlash',
    icon: Apple,
    accent: '#22C55E',
    glow: 'rgba(34, 197, 94, 0.35)',
    background: 'linear-gradient(140deg, #22C55E 0%, #16A34A 55%, #166534 100%)',
    category: 'fruits'
  }
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
          '--banner-bg': currentBanner.background,
          '--banner-accent': currentBanner.accent,
          '--banner-glow': currentBanner.glow,
        }}
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
        onClick={handleBannerClick}
      >
        <div className="banner-grid">
          <div className="banner-copy">
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
          <div className="banner-art" aria-hidden="true">
            {(() => {
              const IconComponent = currentBanner.icon
              return (
                <div className="banner-orb">
                  <div className="orb-glow" />
                  <IconComponent size={68} strokeWidth={1.9} />
                </div>
              )
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

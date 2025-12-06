import { useState, useEffect, memo } from 'react';
import './BannerSlider.css';

const BANNERS = [
  {
    id: 1,
    gradient: 'gradient-green',
    badge: '🔥 Chegirma',
    title: 'Yangi Takliflar',
    subtitle: '40% gacha',
    buttonText: "Ko'rish",
    emojis: '🥬🥕🍅',
  },
  {
    id: 2,
    gradient: 'gradient-orange',
    badge: '⚡ Tezkor',
    title: 'Kunlik Mahsulot',
    subtitle: "Yaqin do'kondan",
    buttonText: 'Buyurtma',
    emojis: '🍞🥛🧀',
  },
  {
    id: 3,
    gradient: 'gradient-purple',
    badge: '🎁 Bonus',
    title: 'Meva & Sabzavot',
    subtitle: 'Har kuni yangi',
    buttonText: 'Tanlash',
    emojis: '🍎🍊🍋',
  },
];

const BannerSlider = memo(function BannerSlider({
  onBannerClick,
  autoSlideInterval = 4000
}) {
  const [currentIndex, setCurrentIndex] = useState(0);

  // Auto-slide effect
  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentIndex(prev => (prev + 1) % BANNERS.length);
    }, autoSlideInterval);

    return () => clearInterval(timer);
  }, [autoSlideInterval]);

  const handleDotClick = (index) => {
    setCurrentIndex(index);
  };

  const handleBannerClick = (banner) => {
    onBannerClick?.(banner);
  };

  return (
    <div className="banner-slider">
      <div
        className="banner-track"
        style={{ transform: `translateX(-${currentIndex * 100}%)` }}
      >
        {BANNERS.map((banner) => (
          <div
            key={banner.id}
            className={`banner-slide ${banner.gradient}`}
            onClick={() => handleBannerClick(banner)}
          >
            <div className="banner-content">
              <div className="banner-left">
                <div className="banner-badge">{banner.badge}</div>
                <h2 className="banner-title">{banner.title}</h2>
                <p className="banner-subtitle">{banner.subtitle}</p>
                <button className="banner-btn">{banner.buttonText}</button>
              </div>
              <div className="banner-emoji">{banner.emojis}</div>
            </div>
          </div>
        ))}
      </div>

      <div className="banner-dots">
        {BANNERS.map((_, index) => (
          <button
            key={index}
            className={`dot ${currentIndex === index ? 'active' : ''}`}
            onClick={() => handleDotClick(index)}
            aria-label={`Slide ${index + 1}`}
          />
        ))}
      </div>
    </div>
  );
});

export default BannerSlider;

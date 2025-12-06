import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import './FlashDealsSection.css';

/**
 * FlashDealsSection Component
 * Displays time-limited deals with countdown timer
 * Features: Auto-play carousel, horizontal scroll, discount badges
 */
const FlashDealsSection = ({ deals = [] }) => {
  const navigate = useNavigate();
  const [timeLeft, setTimeLeft] = useState(calculateTimeLeft());

  // Calculate time remaining until end of day
  function calculateTimeLeft() {
    const now = new Date();
    const endOfDay = new Date();
    endOfDay.setHours(23, 59, 59, 999);
    
    const difference = endOfDay - now;
    
    if (difference > 0) {
      return {
        hours: Math.floor(difference / (1000 * 60 * 60)),
        minutes: Math.floor((difference / (1000 * 60)) % 60),
        seconds: Math.floor((difference / 1000) % 60)
      };
    }
    
    return { hours: 0, minutes: 0, seconds: 0 };
  }

  // Update countdown every second
  useEffect(() => {
    const timer = setInterval(() => {
      setTimeLeft(calculateTimeLeft());
    }, 1000);

    return () => clearInterval(timer);
  }, []);

  // Format time with leading zeros
  const formatTime = (value) => String(value).padStart(2, '0');

  // Mock flash deals if none provided
  const flashDeals = useMemo(() => {
    if (deals.length > 0) return deals;
    
    return [
      {
        id: 1,
        name: 'Sut "Lactel" 1L',
        image: '/images/milk.jpg',
        currentPrice: 5990,
        originalPrice: 11980,
        discount: 50,
        stock: 15
      },
      {
        id: 2,
        name: 'Non "Samarqand" 500g',
        image: '/images/bread.jpg',
        currentPrice: 8500,
        originalPrice: 14000,
        discount: 40,
        stock: 8
      },
      {
        id: 3,
        name: 'Meva sharbati 1L',
        image: '/images/juice.jpg',
        currentPrice: 3200,
        originalPrice: 4570,
        discount: 30,
        stock: 25
      },
      {
        id: 4,
        name: 'Yogurt "Danone" 500g',
        image: '/images/yogurt.jpg',
        currentPrice: 7500,
        originalPrice: 15000,
        discount: 50,
        stock: 5
      }
    ];
  }, [deals]);

  const handleDealClick = (deal) => {
    navigate(`/products/${deal.id}`);
  };

  const formatPrice = (price) => {
    return new Intl.NumberFormat('uz-UZ').format(price);
  };

  if (flashDeals.length === 0) return null;

  return (
    <section className="flash-deals">
      <div className="flash-deals__header">
        <div className="flash-deals__title-wrapper">
          <span className="flash-deals__icon">🔥</span>
          <h2 className="flash-deals__title">Flash Deals</h2>
        </div>
        
        <div className="flash-deals__timer">
          <span className="flash-deals__timer-label">⏰ Tugaydi:</span>
          <div className="flash-deals__countdown">
            <span className="flash-deals__time-unit">
              {formatTime(timeLeft.hours)}
            </span>
            <span className="flash-deals__separator">:</span>
            <span className="flash-deals__time-unit">
              {formatTime(timeLeft.minutes)}
            </span>
            <span className="flash-deals__separator">:</span>
            <span className="flash-deals__time-unit">
              {formatTime(timeLeft.seconds)}
            </span>
          </div>
        </div>
      </div>

      <div className="flash-deals__scroll">
        {flashDeals.map((deal) => (
          <div
            key={deal.id}
            className="flash-deal-card"
            onClick={() => handleDealClick(deal)}
          >
            <div className="flash-deal-card__image">
              <img
                src={deal.image}
                alt={deal.name}
                onError={(e) => {
                  e.target.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="140" height="100" viewBox="0 0 140 100"%3E%3Crect fill="%23f3f4f6" width="140" height="100"/%3E%3Ctext x="50%25" y="50%25" dominant-baseline="middle" text-anchor="middle" fill="%239ca3af" font-family="sans-serif" font-size="14"%3EImage%3C/text%3E%3C/svg%3E';
                }}
              />
              <span className="flash-deal-card__badge">
                -{deal.discount}%
              </span>
            </div>

            <div className="flash-deal-card__content">
              <h3 className="flash-deal-card__title">{deal.name}</h3>
              
              <div className="flash-deal-card__price">
                <span className="flash-deal-card__current">
                  {formatPrice(deal.currentPrice)} so'm
                </span>
                <span className="flash-deal-card__original">
                  {formatPrice(deal.originalPrice)}
                </span>
              </div>

              {deal.stock <= 10 && (
                <div className="flash-deal-card__stock">
                  <div className="flash-deal-card__stock-bar">
                    <div 
                      className="flash-deal-card__stock-fill"
                      style={{ width: `${(deal.stock / 10) * 100}%` }}
                    />
                  </div>
                  <span className="flash-deal-card__stock-text">
                    {deal.stock} ta qoldi
                  </span>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
};

export default FlashDealsSection;

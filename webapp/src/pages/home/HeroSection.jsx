import HeroBanner from '../../components/HeroBanner'

const HeroSection = ({
  city,
  heroLocationLine,
  hasPreciseLocation,
  heroOfferSummary,
  heroDiscountSummary,
  cartCount,
  showingAllCities,
  onSelectAddress,
  onCategorySelect,
}) => (
  <section className="hero-shell">
    <div className="hero-content">
      <div className="hero-primary">
        <HeroBanner
          onCategorySelect={(category) => {
            onCategorySelect(category)
            setTimeout(() => {
              document.querySelector('.home-section-header')?.scrollIntoView({ behavior: 'smooth' })
            }, 100)
          }}
        />
      </div>
    </div>
  </section>
)

export default HeroSection

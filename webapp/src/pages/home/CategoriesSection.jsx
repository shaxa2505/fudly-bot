const CategoriesSection = ({ categories, selectedCategory, onSelectCategory }) => (
  <section className="section">
    <div style={{ padding: '0 var(--spacing-lg)' }}>
      <h2 className="section-title" style={{ marginBottom: 'var(--spacing-md)' }}>Kategoriyalar</h2>
      <div style={{ display: 'flex', gap: 'var(--spacing-sm)', overflowX: 'auto', paddingBottom: 'var(--spacing-xs)' }}>
        {categories.map(cat => (
          <button
            key={cat.id}
            className={`chip ${selectedCategory === cat.id ? 'chip--active' : ''}`}
            onClick={() => {
              window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light')
              onSelectCategory(cat.id)
            }}
            style={{ '--cat-color': cat.color }}
          >
            <span>{cat.icon}</span>
            <span>{cat.name}</span>
          </button>
        ))}
      </div>
    </div>
  </section>
)

export default CategoriesSection

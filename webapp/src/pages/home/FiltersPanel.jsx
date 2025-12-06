const FiltersPanel = ({
  isFiltered,
  onResetFilters,
  minDiscount,
  onMinDiscountChange,
  sortBy,
  onSortChange,
  filterSummary,
  showEmptyHighlight,
}) => {
  const handleHaptic = () => {
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged?.()
  }

  const handleDiscountSelect = (value) => {
    handleHaptic()
    if (value === null) {
      onMinDiscountChange(null)
    } else {
      onMinDiscountChange(minDiscount === value ? null : value)
    }
  }

  const handleSortChange = (event) => {
    handleHaptic()
    onSortChange(event.target.value)
  }

  return (
    <section className="section">
      <div className="section-header">
        <div>
          <p className="text-caption" style={{ color: 'var(--color-text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '8px' }}>Tez filtrlar</p>
          <h2 className="section-title">Topilmangizni aniqlang</h2>
          <p className="text-body" style={{ color: 'var(--color-text-secondary)', marginTop: '4px' }}>
            Chegirmalar va tartiblash yordamida eng mos taklifni toping.
          </p>
        </div>
        {isFiltered && (
          <button type="button" className="btn btn--ghost btn--sm" onClick={onResetFilters}>
            Filtrlarni tozalash
          </button>
        )}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--spacing-md)' }}>
        <div style={{ display: 'flex', gap: 'var(--spacing-sm)', alignItems: 'center', overflowX: 'auto' }}>
          <div className="filter-group">
            <button
              className={`chip ${minDiscount === null ? 'chip--active' : ''}`}
              onClick={() => handleDiscountSelect(null)}
            >
              Barchasi
            </button>
            <button
              className={`chip ${minDiscount === 20 ? 'chip--active' : ''}`}
              onClick={() => handleDiscountSelect(20)}
            >
              20%+ chegirma
            </button>
            <button
              className={`chip ${minDiscount === 30 ? 'chip--active' : ''}`}
              onClick={() => handleDiscountSelect(30)}
            >
              🔥 30%+
            </button>
            <button
              className={`chip ${minDiscount === 50 ? 'chip--active' : ''}`}
              onClick={() => handleDiscountSelect(50)}
            >
              💥 50%+
            </button>
          </div>

          <select className="select" value={sortBy} onChange={handleSortChange} style={{ minWidth: '140px' }}>
            <option value="default">Tartiblash</option>
            <option value="discount">Chegirma ↓</option>
            <option value="price_asc">Narx ↑</option>
            <option value="price_desc">Narx ↓</option>
          </select>
        </div>

        {isFiltered && (
          <div className="text-caption" role="status" aria-live="polite" style={{ color: 'var(--color-primary)', marginTop: 'var(--spacing-xs)' }}>
            Faol filtrlar: {filterSummary.join(', ')}
          </div>
        )}
      </div>
    </section>
  )
}

export default FiltersPanel

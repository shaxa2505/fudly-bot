import { useState } from 'react'
import './FilterPanel.css'

export const FILTER_CATEGORY_OPTIONS = [
  { id: 'eggs', name: 'Tuxum', keywords: ['egg', 'eggs', 'tuxum', 'яйц'] },
  { id: 'noodles', name: 'Makaron va Ugra', keywords: ['makaron', 'noodle', 'lapsha', 'ugra', 'pasta'] },
  { id: 'chips', name: 'Chips va Crisps', keywords: ['chip', 'chips', 'crisps', 'lays', 'snack'] },
  { id: 'fast-food', name: 'Fast Food', keywords: ['fast', 'burger', 'pizza', 'shawarma', 'sandwich'] }
]

export const FILTER_BRAND_OPTIONS = [
  { id: 'individual', name: 'Individual Collection', keywords: ['individual collection'] },
  { id: 'cocola', name: 'Cocola', keywords: ['cocola'] },
  { id: 'ifad', name: 'Ifad', keywords: ['ifad'] },
  { id: 'kazi', name: 'Kazi Farmas', keywords: ['kazi', 'farmas'] }
]

function FilterPanel({ onClose, onApply, selectedFilters }) {
  const [categories, setCategories] = useState(selectedFilters?.categories || [])
  const [brands, setBrands] = useState(selectedFilters?.brands || [])

  const toggleCategory = (categoryId) => {
    setCategories(prev =>
      prev.includes(categoryId)
        ? prev.filter(id => id !== categoryId)
        : [...prev, categoryId]
    )
  }

  const toggleBrand = (brandId) => {
    setBrands(prev =>
      prev.includes(brandId)
        ? prev.filter(id => id !== brandId)
        : [...prev, brandId]
    )
  }

  const handleApply = () => {
    onApply({ categories, brands })
  }

  return (
    <div className="filter-overlay" onClick={onClose}>
      <div className="filter-panel" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="filter-header">
          <button className="close-btn" onClick={onClose}>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <path d="M18 6L6 18M6 6l12 12" stroke="#181725" strokeWidth="2" strokeLinecap="round"/>
            </svg>
          </button>
          <h2 className="filter-title">Filtrlar</h2>
          <div style={{ width: 40 }}></div>
        </div>

        {/* Content */}
        <div className="filter-content">
          {/* Categories */}
          <div className="filter-section">
            <h3 className="section-title">Kategoriyalar</h3>
            <div className="filter-options">
              {FILTER_CATEGORY_OPTIONS.map(category => (
                <button
                  key={category.id}
                  className={`filter-option ${categories.includes(category.id) ? 'active' : ''}`}
                  onClick={() => toggleCategory(category.id)}
                >
                  <div className={`checkbox ${categories.includes(category.id) ? 'checked' : ''}`}>
                    {categories.includes(category.id) && (
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                        <path d="M20 6L9 17l-5-5" stroke="white" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    )}
                  </div>
                  <span className={`option-label ${categories.includes(category.id) ? 'active' : ''}`}>
                    {category.name}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* Brands */}
          <div className="filter-section">
            <h3 className="section-title">Brend</h3>
            <div className="filter-options">
              {FILTER_BRAND_OPTIONS.map(brand => (
                <button
                  key={brand.id}
                  className={`filter-option ${brands.includes(brand.id) ? 'active' : ''}`}
                  onClick={() => toggleBrand(brand.id)}
                >
                  <div className={`checkbox ${brands.includes(brand.id) ? 'checked' : ''}`}>
                    {brands.includes(brand.id) && (
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                        <path d="M20 6L9 17l-5-5" stroke="white" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    )}
                  </div>
                  <span className={`option-label ${brands.includes(brand.id) ? 'active' : ''}`}>
                    {brand.name}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Apply Button */}
        <div className="filter-footer">
          <button className="apply-filter-btn" onClick={handleApply}>
            Filtrni qo'llash
          </button>
        </div>
      </div>
    </div>
  )
}

export default FilterPanel

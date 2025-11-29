import { useState } from 'react'
import BottomNav from '../components/BottomNav'
import './ExplorePage.css'

const CATEGORIES = [
  {
    id: 'fruits-vegetables',
    name: "Mevalar va Sabzavotlar",
    nameEn: "Frash Fruits\n& Vegetable",
    image: '🥬🍅🥕',
    color: 'linear-gradient(135deg, #E8F5E9 0%, #C8E6C9 100%)',
    borderColor: '#53B175'
  },
  {
    id: 'cooking-oil',
    name: "Yog' va Ghee",
    nameEn: "Cooking Oil\n& Ghee",
    image: '🛢️',
    color: 'linear-gradient(135deg, #FFF8E1 0%, #FFECB3 100%)',
    borderColor: '#F8A825'
  },
  {
    id: 'meat-fish',
    name: "Go'sht va Baliq",
    nameEn: "Meat & Fish",
    image: '🥩🐟',
    color: 'linear-gradient(135deg, #FCE4EC 0%, #F8BBD0 100%)',
    borderColor: '#F06292'
  },
  {
    id: 'bakery',
    name: "Nonvoyxona va Shirinliklar",
    nameEn: "Bakery & Snacks",
    image: '🍞🥖',
    color: 'linear-gradient(135deg, #F3E5F5 0%, #E1BEE7 100%)',
    borderColor: '#BA68C8'
  },
  {
    id: 'dairy',
    name: "Sut va Tuxum",
    nameEn: "Dairy & Eggs",
    image: '🥛🧀',
    color: 'linear-gradient(135deg, #FFF9C4 0%, #FFF59D 100%)',
    borderColor: '#FDD835'
  },
  {
    id: 'beverages',
    name: "Ichimliklar",
    nameEn: "Beverages",
    image: '🥤🧃',
    color: 'linear-gradient(135deg, #E1F5FE 0%, #B3E5FC 100%)',
    borderColor: '#29B6F6'
  }
]

function ExplorePage({ onNavigate }) {
  const [searchQuery, setSearchQuery] = useState('')
  const [cart] = useState(() => {
    const saved = localStorage.getItem('fudly_cart')
    return saved ? new Map(Object.entries(JSON.parse(saved))) : new Map()
  })

  const cartCount = Array.from(cart.values()).reduce((sum, qty) => sum + qty, 0)

  const filteredCategories = CATEGORIES.filter(cat =>
    cat.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    cat.nameEn.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const handleCategoryClick = (category) => {
    onNavigate?.('category-products', { categoryId: category.id, categoryName: category.name })
  }

  const handleClearSearch = () => {
    setSearchQuery('')
  }

  return (
    <div className="explore-page">
      {/* Header */}
      <header className="explore-header">
        <h1 className="page-title">Mahsulotlarni Topish</h1>
      </header>

      {/* Search */}
      <div className="search-section">
        <div className="search-box">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" className="search-icon">
            <circle cx="11" cy="11" r="8" stroke="#7C7C7C" strokeWidth="2"/>
            <path d="M21 21l-4.35-4.35" stroke="#7C7C7C" strokeWidth="2" strokeLinecap="round"/>
          </svg>
          <input
            type="text"
            className="search-input"
            placeholder="Do'kon qidirish"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
      </div>

      {/* Categories Grid */}
      <div className="categories-grid">
        {filteredCategories.map(category => (
          <button
            key={category.id}
            className="category-card"
            style={{
              background: category.color,
              borderColor: category.borderColor
            }}
            onClick={() => handleCategoryClick(category)}
          >
            <div className="category-image">
              <span className="category-emoji">{category.image}</span>
            </div>
            <h3 className="category-name">{category.name}</h3>
          </button>
        ))}
      </div>

      {/* Bottom Navigation */}
      <BottomNav
        currentPage="stores"
        onNavigate={onNavigate}
        cartCount={cartCount}
      />
    </div>
  )
}

export default ExplorePage

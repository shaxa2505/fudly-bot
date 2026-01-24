import { useState } from 'react'
import { Apple, Droplet, Beef, Croissant, Milk, Coffee, Search } from 'lucide-react'
import BottomNav from '../components/BottomNav'
import { blurOnEnter } from '../utils/helpers'
import './ExplorePage.css'

const CATEGORIES = [
  {
    id: 'fruits-vegetables',
    name: "Mevalar va Sabzavotlar",
    nameEn: "Frash Fruits\n& Vegetable",
    icon: Apple,
    color: 'linear-gradient(135deg, #E8F5E9 0%, #C8E6C9 100%)',
    borderColor: '#53B175'
  },
  {
    id: 'cooking-oil',
    name: "Yog' va Ghee",
    nameEn: "Cooking Oil\n& Ghee",
    icon: Droplet,
    color: 'linear-gradient(135deg, #FFF8E1 0%, #FFECB3 100%)',
    borderColor: '#F8A825'
  },
  {
    id: 'meat-fish',
    name: "Go'sht va Baliq",
    nameEn: "Meat & Fish",
    icon: Beef,
    color: 'linear-gradient(135deg, #FCE4EC 0%, #F8BBD0 100%)',
    borderColor: '#F06292'
  },
  {
    id: 'bakery',
    name: "Nonvoyxona va Shirinliklar",
    nameEn: "Bakery & Snacks",
    icon: Croissant,
    color: 'linear-gradient(135deg, #F3E5F5 0%, #E1BEE7 100%)',
    borderColor: '#BA68C8'
  },
  {
    id: 'dairy',
    name: "Sut va Tuxum",
    nameEn: "Dairy & Eggs",
    icon: Milk,
    color: 'linear-gradient(135deg, #FFF9C4 0%, #FFF59D 100%)',
    borderColor: '#FDD835'
  },
  {
    id: 'beverages',
    name: "Ichimliklar",
    nameEn: "Beverages",
    icon: Coffee,
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
        <div className="topbar-card explore-header-inner">
          <h1 className="explore-title">Mahsulotlarni Topish</h1>
        </div>
      </header>

      {/* Search */}
      <div className="explore-search-section">
        <div className="explore-search-box">
          <Search size={20} className="explore-search-icon" color="#7C7C7C" strokeWidth={2} />
          <input
            type="text"
            className="explore-search-input"
            placeholder="Do'kon qidirish"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={blurOnEnter}
          />
        </div>
      </div>

      {/* Categories Grid */}
      <div className="explore-categories-grid">
        {filteredCategories.map(category => {
          const IconComponent = category.icon
          return (
            <button
              key={category.id}
              className="explore-category-card"
              style={{
                background: category.color,
                borderColor: category.borderColor
              }}
              onClick={() => handleCategoryClick(category)}
            >
              <div className="explore-category-image">
                <IconComponent
                  size={48}
                  color={category.borderColor}
                  strokeWidth={2}
                  aria-hidden="true"
                />
              </div>
              <h3 className="explore-category-name">{category.name}</h3>
            </button>
          )
        })}
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

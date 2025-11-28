import './BottomNav.css'

function BottomNav({ currentPage, onNavigate, cartCount, favoritesCount }) {
  const menuItems = [
    { id: 'home', icon: '🏠', label: 'Menyu' },
    { id: 'stores', icon: '🏪', label: "Do'konlar" },
    { id: 'favorites', icon: '❤️', label: 'Saqlangan', badge: favoritesCount },
    { id: 'cart', icon: '🛒', label: 'Savat', badge: cartCount },
  ]

  return (
    <nav className="bottom-nav">
      <div className="bottom-nav-content">
        {menuItems.map(item => (
          <button
            key={item.id}
            className={`nav-item ${currentPage === item.id ? 'active' : ''}`}
            onClick={() => onNavigate(item.id)}
          >
            <div className="nav-icon-container">
              <span className="nav-icon">{item.icon}</span>
              {item.badge > 0 && (
                <span className="nav-badge">{item.badge > 99 ? '99+' : item.badge}</span>
              )}
            </div>
            <span className="nav-label">{item.label}</span>
          </button>
        ))}
      </div>
    </nav>
  )
}

export default BottomNav

import './BottomNav.css'

function BottomNav({ currentPage, onNavigate, cartCount, favoritesCount }) {
  const getIcon = (id, isActive) => {
    const color = isActive ? '#00866e' : '#999'
    
    switch(id) {
      case 'home':
        return (
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M9 22V12h6v10" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        )
      case 'stores':
        return (
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <path d="M3 9h18v10a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" stroke={color} strokeWidth="2"/>
            <path d="M3 9l2-4h14l2 4M3 9v10a2 2 0 002 2h14a2 2 0 002-2V9" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        )
      case 'favorites':
        return (
          <svg width="24" height="24" viewBox="0 0 24 24" fill={isActive ? color : 'none'}>
            <path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        )
      case 'cart':
        return (
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <circle cx="9" cy="21" r="1" stroke={color} strokeWidth="2"/>
            <circle cx="20" cy="21" r="1" stroke={color} strokeWidth="2"/>
            <path d="M1 1h4l2.68 13.39a2 2 0 002 1.61h9.72a2 2 0 002-1.61L23 6H6" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        )
      default:
        return null
    }
  }

  const menuItems = [
    { id: 'home', label: 'Menyu' },
    { id: 'stores', label: "Do'konlar" },
    { id: 'favorites', label: 'Saqlangan', badge: favoritesCount },
    { id: 'cart', label: 'Savat', badge: cartCount },
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
              <span className="nav-icon">{getIcon(item.id, currentPage === item.id)}</span>
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

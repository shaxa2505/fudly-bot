import './BottomNav.css'

function BottomNav({ currentPage, onNavigate, cartCount }) {
  const getIcon = (id, isActive) => {
    const color = isActive ? '#2c473a' : '#6C757D'
    
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
      case 'cart':
        return (
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <circle cx="9" cy="21" r="1" stroke={color} strokeWidth="2"/>
            <circle cx="20" cy="21" r="1" stroke={color} strokeWidth="2"/>
            <path d="M1 1h4l2.68 13.39a2 2 0 002 1.61h9.72a2 2 0 002-1.61L23 6H6" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        )
      case 'profile':
        return (
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            <circle cx="12" cy="7" r="4" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        )
      default:
        return null
    }
  }

  const menuItems = [
    { id: 'home', label: 'Menyu' },
    { id: 'stores', label: "Do'konlar" },
    { id: 'cart', label: 'Savat', badge: cartCount },
    { id: 'profile', label: 'Yana' },
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

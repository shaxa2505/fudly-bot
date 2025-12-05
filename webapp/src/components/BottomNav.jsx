import { useNavigate, useLocation } from 'react-router-dom'
import './BottomNav.css'

// Map page IDs to routes
const PAGE_ROUTES = {
  'home': '/',
  'stores': '/stores',
  'cart': '/cart',
  'profile': '/profile',
}

function BottomNav({ currentPage, cartCount }) {
  const navigate = useNavigate()
  const location = useLocation()

  // Determine current page from route if not explicitly passed
  const activePage = currentPage || (() => {
    const path = location.pathname
    if (path === '/') return 'home'
    if (path === '/stores') return 'stores'
    if (path === '/cart') return 'cart'
    if (path === '/profile' || path === '/yana') return 'profile'
    return 'home'
  })()
  const getIcon = (id, isActive) => {
    const color = isActive ? '#53B175' : '#7C7C7C'
    const strokeW = isActive ? '2.5' : '2'

    switch(id) {
      case 'home':
        return (
          <svg width="24" height="24" viewBox="0 0 24 24" fill={isActive ? color : 'none'}>
            <path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z" stroke={color} strokeWidth={strokeW} strokeLinecap="round" strokeLinejoin="round" fill={isActive ? 'rgba(83,177,117,0.15)' : 'none'}/>
            <path d="M9 22V12h6v10" stroke={color} strokeWidth={strokeW} strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        )
      case 'stores':
        return (
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <path d="M3 9h18v10a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" stroke={color} strokeWidth={strokeW} fill={isActive ? 'rgba(83,177,117,0.15)' : 'none'}/>
            <path d="M3 9l2-4h14l2 4" stroke={color} strokeWidth={strokeW} strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        )
      case 'cart':
        return (
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <circle cx="9" cy="21" r="1.5" fill={color}/>
            <circle cx="18" cy="21" r="1.5" fill={color}/>
            <path d="M1 1h4l2.68 13.39a2 2 0 002 1.61h8.72a2 2 0 002-1.61L22 6H6" stroke={color} strokeWidth={strokeW} strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        )
      case 'profile':
        return (
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" stroke={color} strokeWidth={strokeW} strokeLinecap="round" strokeLinejoin="round"/>
            <circle cx="12" cy="7" r="4" stroke={color} strokeWidth={strokeW} fill={isActive ? 'rgba(83,177,117,0.15)' : 'none'}/>
          </svg>
        )
      default:
        return null
    }
  }

  const menuItems = [
    { id: 'home', label: 'Bosh sahifa' },
    { id: 'stores', label: "Do'konlar" },
    { id: 'cart', label: 'Savat', badge: cartCount },
    { id: 'profile', label: 'Yana' },
  ]

  const handleNavigate = (pageId) => {
    // Haptic feedback
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light')

    const route = PAGE_ROUTES[pageId] || '/'
    navigate(route)
  }

  return (
    <nav className="bottom-nav">
      <div className="bottom-nav-content">
        {menuItems.map(item => (
          <button
            key={item.id}
            type="button"
            className={`nav-item ${activePage === item.id ? 'active' : ''}`}
            onClick={() => handleNavigate(item.id)}
            aria-current={activePage === item.id ? 'page' : undefined}
            aria-label={item.label}
          >
            <div className="nav-icon-container">
              <span className="nav-icon">{getIcon(item.id, activePage === item.id)}</span>
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

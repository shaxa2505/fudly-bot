import { useEffect, useRef, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import './BottomNav.css'

// Map page IDs to routes
const PAGE_ROUTES = {
  'home': '/',
  'stores': '/stores',
  'cart': '/cart',
  'orders': '/orders',
  'profile': '/profile',
}

function BottomNav({ currentPage, cartCount }) {
  const navigate = useNavigate()
  const location = useLocation()
  const [cartPulse, setCartPulse] = useState(false)
  const [cartIconPulse, setCartIconPulse] = useState(false)
  const prevCountRef = useRef(cartCount)

  // Determine current page from route if not explicitly passed
  const activePage = currentPage || (() => {
    const path = location.pathname
    if (path === '/') return 'home'
    if (path === '/stores') return 'stores'
    if (path === '/cart') return 'cart'
    if (path.startsWith('/order')) return 'orders'
    if (path === '/profile' || path === '/yana') return 'profile'
    return 'home'
  })()
  const getIcon = (id, isActive) => {
    const strokeW = isActive ? '2.5' : '2'

    switch(id) {
      case 'home':
        return (
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z" stroke="currentColor" strokeWidth={strokeW} strokeLinecap="round" strokeLinejoin="round" fill="currentColor" fillOpacity={isActive ? 0.12 : 0}/>
            <path d="M9 22V12h6v10" stroke="currentColor" strokeWidth={strokeW} strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        )
      case 'stores':
        return (
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <path d="M3 9h18v10a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" stroke="currentColor" strokeWidth={strokeW} fill="none"/>
            <path d="M3 9l2-4h14l2 4" stroke="currentColor" strokeWidth={strokeW} strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        )
      case 'cart':
        return (
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <circle cx="9" cy="21" r="1.5" fill="currentColor"/>
            <circle cx="18" cy="21" r="1.5" fill="currentColor"/>
            <path d="M1 1h4l2.68 13.39a2 2 0 002 1.61h8.72a2 2 0 002-1.61L22 6H6" stroke="currentColor" strokeWidth={strokeW} strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        )
      case 'orders':
        return (
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <circle cx="4" cy="7" r="1.5" fill="currentColor" />
            <circle cx="4" cy="12" r="1.5" fill="currentColor" />
            <circle cx="4" cy="17" r="1.5" fill="currentColor" />
            <path d="M8 7h12" stroke="currentColor" strokeWidth={strokeW} strokeLinecap="round" />
            <path d="M8 12h12" stroke="currentColor" strokeWidth={strokeW} strokeLinecap="round" />
            <path d="M8 17h12" stroke="currentColor" strokeWidth={strokeW} strokeLinecap="round" />
          </svg>
        )
      case 'profile':
        return (
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" stroke="currentColor" strokeWidth={strokeW} strokeLinecap="round" strokeLinejoin="round"/>
            <circle cx="12" cy="7" r="4" stroke="currentColor" strokeWidth={strokeW} fill="currentColor" fillOpacity={isActive ? 0.12 : 0}/>
          </svg>
        )
      default:
        return null
    }
  }

  const menuItems = [
    { id: 'home', label: 'Asosiy' },
    { id: 'stores', label: "Do'konlar" },
    { id: 'cart', label: 'Savat', badge: cartCount },
    { id: 'orders', label: 'Buyurtmalar' },
    { id: 'profile', label: 'Profil' },
  ]

  const handleNavigate = (pageId) => {
    // Haptic feedback
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light')

    const route = PAGE_ROUTES[pageId] || '/'
    navigate(route)
  }

  useEffect(() => {
    const prev = prevCountRef.current
    if (typeof prev === 'number' && cartCount > prev) {
      setCartPulse(true)
      setCartIconPulse(true)
      const badgeTimer = setTimeout(() => setCartPulse(false), 360)
      const iconTimer = setTimeout(() => setCartIconPulse(false), 420)
      prevCountRef.current = cartCount
      return () => {
        clearTimeout(badgeTimer)
        clearTimeout(iconTimer)
      }
    }
    prevCountRef.current = cartCount
    return undefined
  }, [cartCount])

  return (
    <nav className="bottom-nav">
      <div className="bottom-nav-content">
        {menuItems.map(item => {
          const isCart = item.id === 'cart'
          const shouldPulse = isCart && cartPulse
          const shouldPop = isCart && cartIconPulse
          return (
          <button
            key={item.id}
            className={`nav-item ${activePage === item.id ? 'active' : ''}`}
            onClick={() => handleNavigate(item.id)}
          >
            <div className="nav-icon-container">
              <span className={`nav-icon ${shouldPop ? 'pop' : ''}`}>
                {getIcon(item.id, activePage === item.id)}
              </span>
              {item.badge > 0 && (
                <span className={`nav-badge ${shouldPulse ? 'pulse' : ''}`}>
                  {item.badge > 99 ? '99+' : item.badge}
                </span>
              )}
            </div>
            <span className="nav-label">{item.label}</span>
          </button>
        )})}
      </div>
    </nav>
  )
}

export default BottomNav

import { useState, useEffect } from 'react'
import HomePage from './pages/HomePage'
import CartPage from './pages/CartPage'
import ProfilePage from './pages/ProfilePage'
import { initializeTelegramAuth, isAuthenticated } from './utils/auth'
import './App.css'

function App() {
  const [currentPage, setCurrentPage] = useState('home')
  const [tg, setTg] = useState(null)
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Initialize Telegram WebApp and Auth
    const initApp = async () => {
      if (window.Telegram?.WebApp) {
        const webapp = window.Telegram.WebApp
        webapp.ready()
        webapp.expand()
        setTg(webapp)

        // Set theme colors
        document.documentElement.style.setProperty('--tg-theme-bg-color', webapp.themeParams.bg_color || '#ffffff')
        document.documentElement.style.setProperty('--tg-theme-text-color', webapp.themeParams.text_color || '#000000')
        document.documentElement.style.setProperty('--tg-theme-hint-color', webapp.themeParams.hint_color || '#999999')
        document.documentElement.style.setProperty('--tg-theme-button-color', webapp.themeParams.button_color || '#2D5F3F')
        document.documentElement.style.setProperty('--tg-theme-button-text-color', webapp.themeParams.button_text_color || '#ffffff')

        // Validate auth
        try {
          const profile = await initializeTelegramAuth()
          if (profile) {
            setUser(profile)
          }
        } catch (error) {
          console.error('Auth failed:', error)
        }
      }
      setLoading(false)
    }

    initApp()
  }, [])

  const renderPage = () => {
    if (loading) {
      return (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '32px', marginBottom: '16px' }}>🍽️</div>
            <div style={{ color: '#999' }}>Yuklanmoqda...</div>
          </div>
        </div>
      )
    }

    switch (currentPage) {
      case 'cart':
        return <CartPage onNavigate={setCurrentPage} user={user} />
      case 'profile':
        return <ProfilePage onNavigate={setCurrentPage} user={user} />
      case 'stores':
        return <HomePage onNavigate={setCurrentPage} tg={tg} user={user} />
      default:
        return <HomePage onNavigate={setCurrentPage} tg={tg} user={user} />
    }
  }

  return (
    <div className="app">
      {renderPage()}
    </div>
  )
}

export default App

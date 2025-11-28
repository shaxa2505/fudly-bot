import { useState, useEffect } from 'react'
import HomePage from './pages/HomePage'
import CartPage from './pages/CartPage'
import FavoritesPage from './pages/FavoritesPage'
import './App.css'

function App() {
  const [currentPage, setCurrentPage] = useState('home')
  const [tg, setTg] = useState(null)

  useEffect(() => {
    // Initialize Telegram WebApp
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
    }
  }, [])

  const renderPage = () => {
    switch (currentPage) {
      case 'cart':
        return <CartPage onNavigate={setCurrentPage} />
      case 'favorites':
        return <FavoritesPage onNavigate={setCurrentPage} />
      default:
        return <HomePage onNavigate={setCurrentPage} tg={tg} />
    }
  }

  return (
    <div className="app">
      {renderPage()}
    </div>
  )
}

export default App

import { useState, useEffect } from 'react'
import HomePage from './pages/HomePage'
import CartPage from './pages/CartPage'
import YanaPage from './pages/YanaPage'
import OrderTrackingPage from './pages/OrderTrackingPage'
import CheckoutPage from './pages/CheckoutPage'
import ProductDetailPage from './pages/ProductDetailPage'
import StoresPage from './pages/StoresPage'
import CategoryProductsPage from './pages/CategoryProductsPage'
import './App.css'
import './styles/animations.css'

function App() {
  const [currentPage, setCurrentPage] = useState('home')
  const [pageParams, setPageParams] = useState({})
  const [user, setUser] = useState({ id: 1, first_name: 'Guest', username: 'guest' })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Initialize Telegram WebApp
    const tg = window.Telegram?.WebApp

    if (tg) {
      // Expand to full height
      tg.expand()
      tg.ready()

      // Get user from Telegram
      const tgUser = tg.initDataUnsafe?.user
      if (tgUser) {
        setUser({
          id: tgUser.id,
          first_name: tgUser.first_name || 'User',
          last_name: tgUser.last_name || '',
          username: tgUser.username || '',
          photo_url: tgUser.photo_url,
          language_code: tgUser.language_code || 'uz',
        })
      }

      // Theme colors
      document.documentElement.style.setProperty('--tg-theme-bg-color', tg.themeParams.bg_color || '#ffffff')
      document.documentElement.style.setProperty('--tg-theme-text-color', tg.themeParams.text_color || '#000000')
      document.documentElement.style.setProperty('--tg-theme-button-color', tg.themeParams.button_color || '#53B175')

      // Handle back button
      tg.BackButton.onClick(() => {
        if (currentPage !== 'home') {
          setCurrentPage('home')
        } else {
          tg.close()
        }
      })
    }

    setLoading(false)
  }, [currentPage])

  // Update Telegram back button visibility
  useEffect(() => {
    const tg = window.Telegram?.WebApp
    if (tg) {
      if (currentPage === 'home') {
        tg.BackButton.hide()
      } else {
        tg.BackButton.show()
      }
    }
  }, [currentPage])

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

    const navigate = (page, params = {}) => {
      setCurrentPage(page)
      setPageParams(params)
    }

    switch (currentPage) {
      case 'cart':
        return <CartPage onNavigate={navigate} user={user} />
      case 'profile':
        return <YanaPage onNavigate={navigate} user={user} />
      case 'checkout':
        return <CheckoutPage onNavigate={navigate} user={user} />
      case 'order-tracking':
        return <OrderTrackingPage onNavigate={navigate} user={user} bookingId={pageParams.bookingId} />
      case 'product-detail':
        return <ProductDetailPage onNavigate={navigate} offer={pageParams.offer} onAddToCart={pageParams.onAddToCart} />
      case 'category-products':
        return <CategoryProductsPage categoryId={pageParams.categoryId} categoryName={pageParams.categoryName} onNavigate={navigate} onBack={() => navigate('stores')} />
      case 'stores':
        return <StoresPage onNavigate={navigate} user={user} />
      default:
        return <HomePage onNavigate={navigate} user={user} />
    }
  }

  return (
    <div className="app">
      {renderPage()}
    </div>
  )
}

export default App

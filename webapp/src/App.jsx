import { useState, useEffect } from 'react'
import { MemoryRouter, Routes, Route, useNavigate, useLocation } from 'react-router-dom'
import { FavoritesProvider } from './context/FavoritesContext'
import api from './api/client'
import HomePage from './pages/HomePage'
import CartPage from './pages/CartPage'
import YanaPage from './pages/YanaPage'
import OrderTrackingPage from './pages/OrderTrackingPage'
import CheckoutPage from './pages/CheckoutPage'
import ProductDetailPage from './pages/ProductDetailPage'
import StoresPage from './pages/StoresPage'
import CategoryProductsPage from './pages/CategoryProductsPage'
import FavoritesPage from './pages/FavoritesPage'
import './App.css'
import './styles/animations.css'

// Loading screen component
function LoadingScreen() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: '32px', marginBottom: '16px' }}>🍽️</div>
        <div style={{ color: '#999' }}>Yuklanmoqda...</div>
      </div>
    </div>
  )
}

// Main app content with routing
function AppContent() {
  const navigate = useNavigate()
  const location = useLocation()
  const [user, setUser] = useState({ id: 1, first_name: 'Guest', username: 'guest' })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    initializeApp()
  }, [])

  const initializeApp = async () => {
    // Initialize Telegram WebApp
    const tg = window.Telegram?.WebApp

    if (tg) {
      // Expand to full height
      tg.expand()
      tg.ready()

      // Get user from Telegram
      const tgUser = tg.initDataUnsafe?.user
      if (tgUser) {
        const userData = {
          id: tgUser.id,
          first_name: tgUser.first_name || 'User',
          last_name: tgUser.last_name || '',
          username: tgUser.username || '',
          photo_url: tgUser.photo_url,
          language_code: tgUser.language_code || 'uz',
        }
        setUser(userData)

        // Sync with backend to get full profile (phone, city from bot registration)
        try {
          const profile = await api.getProfile(tgUser.id)
          if (profile) {
            const fullUser = {
              ...userData,
              phone: profile.phone,
              city: profile.city,
              language: profile.language,
              registered: profile.registered,
            }
            setUser(fullUser)
            // Save to localStorage for other components
            localStorage.setItem('fudly_user', JSON.stringify(fullUser))
            if (profile.phone) {
              localStorage.setItem('fudly_phone', profile.phone)
            }
            if (profile.city) {
              localStorage.setItem('fudly_location', JSON.stringify({ city: profile.city }))
            }
          }
        } catch (error) {
          console.log('Profile sync:', error.message)
          // User not registered yet - that's ok
        }
      }

      // Theme colors
      document.documentElement.style.setProperty('--tg-theme-bg-color', tg.themeParams.bg_color || '#ffffff')
      document.documentElement.style.setProperty('--tg-theme-text-color', tg.themeParams.text_color || '#000000')
      document.documentElement.style.setProperty('--tg-theme-button-color', tg.themeParams.button_color || '#53B175')
    }

    setLoading(false)
  }

  // Handle Telegram back button
  useEffect(() => {
    const tg = window.Telegram?.WebApp
    if (!tg) return

    const isHome = location.pathname === '/'

    if (isHome) {
      tg.BackButton.hide()
    } else {
      tg.BackButton.show()
    }

    const handleBack = () => {
      if (!isHome) {
        navigate(-1)
      } else {
        tg.close()
      }
    }

    tg.BackButton.onClick(handleBack)

    return () => {
      tg.BackButton.offClick(handleBack)
    }
  }, [location.pathname, navigate])

  if (loading) {
    return <LoadingScreen />
  }

  return (
    <div className="app">
      <Routes>
        <Route
          path="/"
          element={<HomePage user={user} />}
        />
        <Route
          path="/cart"
          element={<CartPage user={user} />}
        />
        <Route
          path="/profile"
          element={<YanaPage user={user} />}
        />
        <Route
          path="/checkout"
          element={<CheckoutPage user={user} />}
        />
        <Route
          path="/stores"
          element={<StoresPage user={user} />}
        />
        <Route
          path="/favorites"
          element={<FavoritesPage />}
        />
        <Route
          path="/order/:bookingId"
          element={<OrderTrackingPage user={user} />}
        />
        <Route
          path="/product"
          element={<ProductDetailPage />}
        />
        <Route
          path="/category/:categoryId"
          element={<CategoryProductsPage />}
        />
        {/* Fallback to home */}
        <Route path="*" element={<HomePage user={user} />} />
      </Routes>
    </div>
  )
}

function App() {
  return (
    <MemoryRouter>
      <FavoritesProvider>
        <AppContent />
      </FavoritesProvider>
    </MemoryRouter>
  )
}

export default App

import { useState, useEffect, lazy, Suspense } from 'react'
import { HashRouter, Routes, Route, useNavigate, useLocation } from 'react-router-dom'
import { FavoritesProvider } from './context/FavoritesContext'
import api from './api/client'
import HomePage from './pages/HomePage'
import './App.css'
import './styles/animations.css'

// Lazy load pages for better initial load
const CartPage = lazy(() => import('./pages/CartPage'))
const YanaPage = lazy(() => import('./pages/YanaPage'))
const OrderTrackingPage = lazy(() => import('./pages/OrderTrackingPage'))
const ProductDetailPage = lazy(() => import('./pages/ProductDetailPage'))
const StoresPage = lazy(() => import('./pages/StoresPage'))
const CategoryProductsPage = lazy(() => import('./pages/CategoryProductsPage'))
const FavoritesPage = lazy(() => import('./pages/FavoritesPage'))

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

// Page loading fallback (smaller)
function PageLoader() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '50vh' }}>
      <div className="spinner" style={{ width: '32px', height: '32px', border: '3px solid #f0f0f0', borderTopColor: '#53B175', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
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
    // Initialize Telegram WebApp immediately
    const tg = window.Telegram?.WebApp

    if (tg) {
      // Expand to full height - do this FIRST for perceived speed
      tg.expand()
      tg.ready()

      // Set theme colors immediately
      document.documentElement.style.setProperty('--tg-theme-bg-color', tg.themeParams.bg_color || '#ffffff')
      document.documentElement.style.setProperty('--tg-theme-text-color', tg.themeParams.text_color || '#000000')
      document.documentElement.style.setProperty('--tg-theme-button-color', tg.themeParams.button_color || '#53B175')

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

        // Show UI immediately, load profile in background
        setLoading(false)

        // Sync with backend in background (non-blocking)
        api.getProfile(tgUser.id).then(profile => {
          if (profile) {
            const fullUser = {
              ...userData,
              phone: profile.phone,
              city: profile.city,
              language: profile.language,
              registered: profile.registered,
            }
            setUser(fullUser)
            localStorage.setItem('fudly_user', JSON.stringify(fullUser))
            if (profile.phone) localStorage.setItem('fudly_phone', profile.phone)
            if (profile.city) localStorage.setItem('fudly_location', JSON.stringify({ city: profile.city }))
          }
        }).catch(() => {
          // User not registered - that's ok
        })
        return
      }
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
      <Suspense fallback={<PageLoader />}>
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
            element={<CartPage user={user} />}
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
            path="/product/:id"
            element={<ProductDetailPage />}
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
      </Suspense>
    </div>
  )
}

function App() {
  return (
    <HashRouter>
      <FavoritesProvider>
        <AppContent />
      </FavoritesProvider>
    </HashRouter>
  )
}

export default App

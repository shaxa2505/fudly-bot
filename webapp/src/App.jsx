import { useState, useEffect, lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, useNavigate, useLocation } from 'react-router-dom'
import { FavoritesProvider } from './context/FavoritesContext'
import { ToastProvider } from './context/ToastContext'
import api from './api/client'
import HomePage from './pages/HomePage'
import PageLoader, { LoadingScreen } from './components/PageLoader'
import './App.css'
import './styles/animations.css'

// Lazy load pages for better initial load
const CartPage = lazy(() => import('./pages/CartPage'))
const YanaPage = lazy(() => import('./pages/YanaPage'))
const OrderDetailsPage = lazy(() => import('./pages/OrderDetailsPage'))
const ProductDetailPage = lazy(() => import('./pages/ProductDetailPage'))
const StoresPage = lazy(() => import('./pages/StoresPage'))
const CategoryProductsPage = lazy(() => import('./pages/CategoryProductsPage'))
const FavoritesPage = lazy(() => import('./pages/FavoritesPage'))

// LoadingScreen and PageLoader are now imported from components/PageLoader

// Main app content with routing
function AppContent() {
  const navigate = useNavigate()
  const location = useLocation()
  const [user, setUser] = useState({ id: 1, first_name: 'Guest', username: 'guest' })
  const [loading, setLoading] = useState(true)

  // In Telegram WebApp on mobile, pressing "Enter/Done" often doesn't dismiss the keyboard.
  // Blurring the focused input/textarea fixes it without needing per-input wiring everywhere.
  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.key !== 'Enter' || event.shiftKey) {
        return
      }

      const target = event.target
      if (!target || typeof target.blur !== 'function') {
        return
      }

      const tagName = target.tagName
      if (tagName === 'INPUT' || tagName === 'TEXTAREA') {
        target.blur()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [])

  useEffect(() => {
    const tg = window.Telegram?.WebApp
    if (!tg) return

    const root = document.documentElement
    const toPx = (value) => `${Math.max(0, Number(value) || 0)}px`
    const isMobile = tg.platform === 'android' || tg.platform === 'ios'

    const applyInsets = (insets) => {
      if (!insets) return
      root.style.setProperty('--safe-area-top', toPx(insets.top))
      root.style.setProperty('--safe-area-right', toPx(insets.right))
      root.style.setProperty('--safe-area-bottom', toPx(insets.bottom))
      root.style.setProperty('--safe-area-left', toPx(insets.left))
    }

    const readInset = (insets, key) => Number(insets?.[key]) || 0

    const updateSafeArea = () => {
      const contentInsets = tg.contentSafeAreaInset
      const safeInsets = tg.safeAreaInset
      const minTop = isMobile ? 24 : 0

      const safeTop = Math.max(readInset(safeInsets, 'top'), minTop)
      const safeRight = Math.max(readInset(safeInsets, 'right'), 0)
      const safeBottom = Math.max(readInset(safeInsets, 'bottom'), 0)
      const safeLeft = Math.max(readInset(safeInsets, 'left'), 0)

      applyInsets({
        top: Math.max(readInset(contentInsets, 'top'), safeTop),
        right: Math.max(readInset(contentInsets, 'right'), safeRight),
        bottom: Math.max(readInset(contentInsets, 'bottom'), safeBottom),
        left: Math.max(readInset(contentInsets, 'left'), safeLeft),
      })
      root.style.setProperty('--safe-area-top-raw', toPx(safeTop))
    }

    updateSafeArea()
    root.style.setProperty('--tg-cap-gap', isMobile ? '8px' : '0px')

    const handleViewportChange = () => updateSafeArea()
    tg.onEvent?.('viewportChanged', handleViewportChange)
    tg.onEvent?.('safeAreaChanged', handleViewportChange)
    tg.onEvent?.('contentSafeAreaChanged', handleViewportChange)

    return () => {
      tg.offEvent?.('viewportChanged', handleViewportChange)
      tg.offEvent?.('safeAreaChanged', handleViewportChange)
      tg.offEvent?.('contentSafeAreaChanged', handleViewportChange)
    }
  }, [])

  useEffect(() => {
    initializeApp()
  }, [])

  const initializeApp = async () => {
    // Initialize Telegram WebApp immediately
    const tg = window.Telegram?.WebApp

    if (tg) {
      // Prevent swipe-to-close in Telegram webview (iOS) and signal readiness early.
      tg.disableVerticalSwipes?.()
      tg.ready()

      const isMobile = tg.platform === 'android' || tg.platform === 'ios'
      if (isMobile && typeof tg.requestFullscreen === 'function' && !tg.isFullscreen) {
        tg.requestFullscreen()
      }

      if (!tg.isExpanded) {
        tg.expand()
      }

      // Set theme colors immediately
      document.documentElement.style.setProperty('--tg-theme-bg-color', tg.themeParams.bg_color || '#ffffff')
      document.documentElement.style.setProperty('--tg-theme-text-color', tg.themeParams.text_color || '#000000')
      document.documentElement.style.setProperty('--tg-theme-button-color', tg.themeParams.button_color || '#53B175')

      // Get user from Telegram
      const tgUser = tg.initDataUnsafe?.user
      if (tg.initData) {
        localStorage.setItem('fudly_init_data', tg.initData)
        if (tgUser?.id) {
          const userKey = `fudly_init_data_${tgUser.id}`
          localStorage.setItem(userKey, tg.initData)
          localStorage.setItem('fudly_last_user_id', String(tgUser.id))
        }
      }
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
        api.getProfile().then(profile => {
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
      <div className="app-surface">
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
              path="/order/:orderId"
              element={<OrderDetailsPage user={user} />}
            />
            <Route
              path="/order/:orderId/details"
              element={<OrderDetailsPage user={user} />}
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
    </div>
  )
}

function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <FavoritesProvider>
          <AppContent />
        </FavoritesProvider>
      </ToastProvider>
    </BrowserRouter>
  )
}

export default App

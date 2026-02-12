import { useState, useEffect, lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, useNavigate, useLocation } from 'react-router-dom'
import { FavoritesProvider } from './context/FavoritesContext'
import { ToastProvider } from './context/ToastContext'
import api, { saveTelegramInitData } from './api/client'
import { setStoredUser } from './utils/auth'
import { getSavedLocation, saveLocation, buildLocationFromReverseGeocode } from './utils/cityUtils'
import { getPreferredLocation } from './utils/geolocation'
import { getScrollContainer } from './utils/scrollContainer'
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
const OrdersPage = lazy(() => import('./pages/OrdersPage'))

// LoadingScreen and PageLoader are now imported from components/PageLoader
const GEO_ATTEMPT_KEY = 'fudly_geo_attempt_ts'
const GEO_STATUS_KEY = 'fudly_geo_status'
const GEO_COOLDOWN_MS = 24 * 60 * 60 * 1000
const GEO_ACCURACY_METERS = 200

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
      const minTop = isMobile ? 28 : 0

      const safeTop = Math.max(readInset(safeInsets, 'top'), minTop)
      const safeRight = Math.max(readInset(safeInsets, 'right'), 0)
      const safeBottom = Math.max(readInset(safeInsets, 'bottom'), 0)
      const safeLeft = Math.max(readInset(safeInsets, 'left'), 0)
      const contentTop = Math.max(readInset(contentInsets, 'top'), safeTop)
      const contentRight = Math.max(readInset(contentInsets, 'right'), safeRight)
      const contentBottom = Math.max(readInset(contentInsets, 'bottom'), safeBottom)
      const contentLeft = Math.max(readInset(contentInsets, 'left'), safeLeft)

      applyInsets({
        top: contentTop,
        right: contentRight,
        bottom: contentBottom,
        left: contentLeft,
      })
      root.style.setProperty('--tg-top-inset', toPx(contentTop))
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
    const root = document.documentElement
    const isTouch =
      window.matchMedia?.('(pointer: coarse)')?.matches ||
      ['android', 'ios'].includes(window.Telegram?.WebApp?.platform)
    if (!isTouch) return undefined

    const isInputLike = (el) => {
      if (!el) return false
      const tag = el.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return true
      return Boolean(el.isContentEditable)
    }

    let baseline = window.visualViewport?.height || window.innerHeight
    let lastState = false
    let rafId = 0

    const setKeyboardOpen = (open) => {
      if (open === lastState) return
      lastState = open
      root.classList.toggle('keyboard-open', open)
    }

    const updateFromViewport = () => {
      const viewport = window.visualViewport
      if (!viewport) return
      const diff = Math.max(0, baseline - viewport.height)
      const activeInput = isInputLike(document.activeElement)
      const nextOpen = activeInput && diff > 120
      setKeyboardOpen(nextOpen)
      if (!activeInput && diff < 60) {
        baseline = Math.max(baseline, viewport.height)
      }
    }

    const scheduleUpdate = () => {
      if (rafId) cancelAnimationFrame(rafId)
      rafId = requestAnimationFrame(updateFromViewport)
    }

    const handleFocusIn = (event) => {
      if (!isInputLike(event.target)) return
      if (!window.visualViewport) {
        setKeyboardOpen(true)
        return
      }
      scheduleUpdate()
    }

    const handleFocusOut = () => {
      setTimeout(() => {
        if (!isInputLike(document.activeElement)) {
          setKeyboardOpen(false)
        }
      }, 80)
    }

    window.visualViewport?.addEventListener('resize', scheduleUpdate)
    window.visualViewport?.addEventListener('scroll', scheduleUpdate)
    document.addEventListener('focusin', handleFocusIn)
    document.addEventListener('focusout', handleFocusOut)

    return () => {
      if (rafId) cancelAnimationFrame(rafId)
      window.visualViewport?.removeEventListener('resize', scheduleUpdate)
      window.visualViewport?.removeEventListener('scroll', scheduleUpdate)
      document.removeEventListener('focusin', handleFocusIn)
      document.removeEventListener('focusout', handleFocusOut)
      root.classList.remove('keyboard-open')
    }
  }, [])

  useEffect(() => {
    const container = getScrollContainer()
    if (!container) return
    if (
      container === document.body ||
      container === document.documentElement ||
      container === document.scrollingElement
    ) {
      window.scrollTo(0, 0)
    } else {
      container.scrollTop = 0
    }
  }, [location.pathname])

  useEffect(() => {
    const stored = getSavedLocation()
    if (stored.address || stored.coordinates) return
    if (stored.source === 'manual') return

    const storedAttempt = localStorage.getItem(GEO_ATTEMPT_KEY)
    const attemptTs = storedAttempt ? Number(storedAttempt) : 0
    if (attemptTs && Date.now() - attemptTs < GEO_COOLDOWN_MS) {
      return
    }

    if (!navigator.geolocation && !window.Telegram?.WebApp?.requestLocation) {
      return
    }

    const markAttempt = (status = '') => {
      localStorage.setItem(GEO_ATTEMPT_KEY, String(Date.now()))
      if (status) {
        localStorage.setItem(GEO_STATUS_KEY, status)
      }
    }

    markAttempt('start')
    const resolveAutoLocation = async () => {
      try {
        const coords = await getPreferredLocation({
          preferTelegram: true,
          enableHighAccuracy: true,
          timeout: 10000,
          maximumAge: 300000,
          minAccuracy: GEO_ACCURACY_METERS,
          retryOnLowAccuracy: true,
          highAccuracyTimeout: 15000,
          highAccuracyMaximumAge: 0,
        })
        const data = await api.reverseGeocode(coords.latitude, coords.longitude, 'uz')
        if (data) {
          const resolved = buildLocationFromReverseGeocode(data, coords.latitude, coords.longitude)
          saveLocation(resolved)
          markAttempt('ok')
        } else {
          markAttempt('fail')
        }
      } catch (error) {
        markAttempt(error?.code === error.PERMISSION_DENIED ? 'denied' : 'fail')
      }
    }

    resolveAutoLocation()
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
      document.documentElement.style.setProperty('--tg-theme-bg-color', tg.themeParams.bg_color || '#F9F9F9')
      document.documentElement.style.setProperty('--tg-theme-text-color', tg.themeParams.text_color || '#2D2D2D')
      document.documentElement.style.setProperty('--tg-theme-button-color', tg.themeParams.button_color || '#3A5A40')

      // Get user from Telegram
      const tgUser = tg.initDataUnsafe?.user
      if (tg.initData) {
        saveTelegramInitData(tg.initData)
        if (tgUser?.id) {
          saveTelegramInitData(tg.initData, tgUser.id)
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

        const syncProfile = async () => {
          let profile = null
          try {
            profile = await api.getProfile()
            if ((!profile?.phone || !profile?.registered) && tg.initData) {
              try {
                const validated = await api.validateAuth(tg.initData)
                if (validated) {
                  profile = validated
                }
              } catch (error) {
                console.warn('Auth validate fallback failed:', error)
              }
            }
          } catch (error) {
            if (tg.initData) {
              try {
                profile = await api.validateAuth(tg.initData)
              } catch (fallbackError) {
                console.warn('Profile sync failed:', fallbackError)
              }
            }
          }

          if (!profile) return

          const fullUser = {
            ...userData,
            phone: profile.phone,
            city: profile.city,
            language: profile.language,
            registered: profile.registered,
          }
          setUser(fullUser)
          setStoredUser(fullUser)
          if (profile.city) {
            try {
              const savedRaw = localStorage.getItem('fudly_location')
              if (!savedRaw) {
                localStorage.setItem(
                  'fudly_location',
                  JSON.stringify({ city: profile.city, source: 'profile' })
                )
              } else {
                const saved = JSON.parse(savedRaw)
                const hasCity = saved?.city && String(saved.city).trim()
                const hasCoords = saved?.coordinates?.lat != null && saved?.coordinates?.lon != null
                if (!hasCity && !hasCoords) {
                  localStorage.setItem(
                    'fudly_location',
                    JSON.stringify({ ...saved, city: profile.city, source: saved?.source || 'profile' })
                  )
                }
              }
            } catch {
              localStorage.setItem(
                'fudly_location',
                JSON.stringify({ city: profile.city, source: 'profile' })
              )
            }
          }
        }

        // Sync with backend in background (non-blocking)
        syncProfile()
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
      if (location.pathname === '/checkout') {
        navigate('/cart')
        return
      }
      if (!isHome) {
        navigate(-1)
        return
      }
      tg.close()
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
        <div className="app-surface-content">
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
                path="/orders"
                element={<OrdersPage user={user} />}
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

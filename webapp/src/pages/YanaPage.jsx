import { useState, useEffect, useRef } from 'react'
import {
  Bell,
  ChevronRight,
  CreditCard,
  Globe,
  Leaf,
  LifeBuoy,
  LogOut,
  MapPin,
  Pencil,
} from 'lucide-react'
import api, { API_BASE_URL, getTelegramInitData } from '../api/client'
import { useCart } from '../context/CartContext'
import { useToast } from '../context/ToastContext'
import BottomNav from '../components/BottomNav'
import PullToRefresh from '../components/PullToRefresh'
import { usePullToRefresh } from '../hooks/usePullToRefresh'
import { getUserId, getUserLanguage, getCurrentUser } from '../utils/auth'
import { resolveImageUrl } from '../utils/imageUtils'
import { calcQuantity } from '../utils/orderMath'
import { normalizeOrderStatus } from '../utils/orderStatus'
import './YanaPage.css'

const COMPLETED_STATUSES = new Set(['completed', 'cancelled', 'rejected'])

const toText = (value, fallback = '') => {
  if (value == null) return fallback
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean' || typeof value === 'bigint') {
    return String(value)
  }
  if (typeof value === 'object') {
    const candidate =
      value.city ??
      value.name ??
      value.title ??
      value.label ??
      value.value ??
      value.text
    if (typeof candidate === 'string') return candidate
    if (typeof candidate === 'number' || typeof candidate === 'boolean') {
      return String(candidate)
    }
    return fallback
  }
  try {
    return String(value)
  } catch {
    return fallback
  }
}

function YanaPage({ user }) {
  const { toast } = useToast()
  const lang = getUserLanguage()

  const cachedUser = getCurrentUser()
  const telegramUser = window.Telegram?.WebApp?.initDataUnsafe?.user
  const resolvedPhone = toText(
    user?.phone ||
      cachedUser?.phone ||
      ''
  ).trim()
  const resolvedCity = toText((() => {
    if (user?.city) return user.city
    if (cachedUser?.city) return cachedUser.city
    try {
      const stored = JSON.parse(localStorage.getItem('fudly_location') || '{}')
      return stored?.city || ''
    } catch {
      return ''
    }
  })()).trim()
  const [notifications, setNotifications] = useState(true)
  const [notificationsOpen, setNotificationsOpen] = useState(false)
  const [notificationsList, setNotificationsList] = useState([])
  const [notificationsLoading, setNotificationsLoading] = useState(true)
  const notificationsRef = useRef([])
  const [savedMetric, setSavedMetric] = useState({ value: 0, unit: 'ta' })
  const [showClearCartModal, setShowClearCartModal] = useState(false)
  const profileName = toText(
    user?.full_name ||
      user?.name ||
      [user?.first_name, user?.last_name].filter(Boolean).join(' ') ||
      [telegramUser?.first_name, telegramUser?.last_name].filter(Boolean).join(' ') ||
      telegramUser?.username ||
      'Foydalanuvchi',
    'Foydalanuvchi'
  ).trim() || 'Foydalanuvchi'
  const profileHandle = toText(user?.username || telegramUser?.username || '').trim()
  const avatarUrl = resolveImageUrl(
    user?.photo_url,
    user?.photo,
    user?.avatar,
    telegramUser?.photo_url
  )
  const profileInitial = profileName ? profileName.slice(0, 1).toUpperCase() : 'F'

  const { cartCount, clearCart } = useCart()
  const userId = getUserId()
  const notificationsStorageKey = userId ? `fudly_notifications_${userId}` : 'fudly_notifications'

  const getWsUrl = () => {
    const envBase = import.meta.env.VITE_WS_URL
    const baseSource = (envBase || API_BASE_URL || '').trim()
    if (!baseSource) return ''

    let base = baseSource
    // Ensure ws:// or wss:// scheme
    if (!base.startsWith('ws://') && !base.startsWith('wss://')) {
      base = base.replace(/^http/, 'ws')
    }
    // Strip API suffix if present
    base = base.replace(/\/api\/v1\/?$/, '')
    base = base.replace(/\/+$/, '')

    let wsEndpoint = ''
    if (base.endsWith('/ws/notifications')) {
      wsEndpoint = base
    } else if (base.endsWith('/ws')) {
      wsEndpoint = `${base}/notifications`
    } else {
      wsEndpoint = `${base}/ws/notifications`
    }

    const params = new URLSearchParams()
    if (userId) {
      params.set('user_id', userId)
    }
    const initData = getTelegramInitData()
    if (initData) {
      params.set('init_data', initData)
    }
    const query = params.toString()
    return `${wsEndpoint}${query ? `?${query}` : ''}`
  }

  const getOrderQuantity = (order) => {
    const items = Array.isArray(order.items) ? order.items : []
    const explicitQty = Number(order.quantity || 0)
    if (explicitQty) return explicitQty
    const itemsQty = calcQuantity(items, item => Number(item?.quantity || 0))
    return itemsQty || 1
  }

  const calculateSavedMetric = (ordersList) => {
    const completedOrders = ordersList.filter((order) => {
      const status = normalizeOrderStatus(order?.status || order?.order_status)
      return COMPLETED_STATUSES.has(status)
    })
    const totalWeight = completedOrders.reduce((sum, order) => (
      sum + Number(order.saved_weight_kg || order.saved_weight || order.saved_kg || 0)
    ), 0)
    const totalQuantity = completedOrders.reduce((sum, order) => (
      sum + getOrderQuantity(order)
    ), 0)
    if (totalWeight > 0) {
      const formatted = Number.isInteger(totalWeight)
        ? totalWeight.toFixed(0)
        : totalWeight.toFixed(1)
      return { value: formatted, unit: 'kg' }
    }
    return { value: totalQuantity, unit: 'ta' }
  }

  const loadSavedMetric = async (force = false) => {
    try {
      const response = await api.getOrders({ force })
      const allOrders = [
        ...(response.orders || []),
        ...(response.bookings || []),
      ]
      setSavedMetric(calculateSavedMetric(allOrders))
    } catch (error) {
      console.warn('Failed to load saved metric:', error)
      setSavedMetric({ value: 0, unit: 'ta' })
    }
  }

  const loadNotificationSettings = async () => {
    if (!userId) return
    try {
      const data = await api.getNotificationSettings()
      setNotifications(Boolean(data.enabled))
    } catch (error) {
      console.warn('Failed to load notification settings:', error)
    }
  }

  const loadNotificationsCache = () => {
    if (!userId) {
      setNotificationsLoading(false)
      return
    }
    try {
      const raw = localStorage.getItem(notificationsStorageKey)
      const parsed = raw ? JSON.parse(raw) : []
      const next = Array.isArray(parsed) ? parsed : []
      setNotificationsList(next)
      notificationsRef.current = next
    } catch (error) {
      console.warn('Failed to load notifications cache:', error)
      setNotificationsList([])
    } finally {
      setNotificationsLoading(false)
    }
  }

  const persistNotifications = (items) => {
    if (!userId) return
    const trimmed = items.slice(0, 50)
    localStorage.setItem(notificationsStorageKey, JSON.stringify(trimmed))
  }

  const handleToggleNotifications = async () => {
    if (!userId) return
    const nextValue = !notifications
    try {
      const data = await api.setNotificationEnabled(nextValue)
      setNotifications(Boolean(data.enabled))
      toast.success(data.enabled ? 'Bildirishnomalar yoqildi' : "Bildirishnomalar o'chirildi")
    } catch (error) {
      console.error('Failed to update notifications:', error)
      toast.error("Bildirishnomalarni yangilab bo'lmadi")
    }
  }

  const handleClearNotifications = () => {
    setNotificationsList([])
    notificationsRef.current = []
    if (userId) {
      localStorage.removeItem(notificationsStorageKey)
    }
  }

  useEffect(() => {
    loadSavedMetric()
  }, [])

  useEffect(() => {
    loadNotificationSettings()
    loadNotificationsCache()
  }, [])

  useEffect(() => {
    if (!userId || !notifications) return

    let ws
    try {
      ws = new WebSocket(getWsUrl())
    } catch (error) {
      console.warn('WebSocket init failed:', error)
      return
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'order_status_changed' || data.type === 'order_created') {
          loadSavedMetric(true)
          return
        }

        if (data.type !== 'notification' || !data.payload) return

        const newItem = {
          id: `${Date.now()}_${Math.random().toString(16).slice(2)}`,
          title: data.payload.title || 'Bildirishnoma',
          message: data.payload.message || '',
          type: data.payload.type || 'system',
          created_at: data.payload.created_at || new Date().toISOString(),
          data: data.payload.data || {},
        }

        setNotificationsList((prev) => {
          const next = [newItem, ...prev]
          notificationsRef.current = next
          persistNotifications(next)
          return next
        })

        if (data.payload.data?.order_id || data.payload.data?.booking_id) {
          loadSavedMetric(true)
        }
      } catch (error) {
        console.warn('Failed to parse notification:', error)
      }
    }

    return () => {
      if (ws) {
        ws.close()
      }
    }
  }, [userId, notifications])

  const handleRefresh = async () => {
    await loadSavedMetric(true)
    await loadNotificationSettings()
    loadNotificationsCache()
  }

  const { containerRef, isRefreshing, pullDistance, progress } = usePullToRefresh(handleRefresh)

  const handleChangePhone = () => {
    const botUsername =
      window.Telegram?.WebApp?.initDataUnsafe?.bot?.username ||
      import.meta.env.VITE_BOT_USERNAME ||
      'fudlyuzbot'
    const link = `https://t.me/${botUsername}`
    if (window.Telegram?.WebApp?.openTelegramLink) {
      window.Telegram?.WebApp?.openTelegramLink?.(link)
      return
    }
    window.open(link, '_blank', 'noopener,noreferrer')
  }

  const handleEditProfile = () => {
    handleChangePhone()
  }

  const handleClearCart = () => {
    setShowClearCartModal(true)
  }

  const handleConfirmClearCart = () => {
    clearCart()
    setShowClearCartModal(false)
    window.Telegram?.WebApp?.showAlert?.('Savat tozalandi')
  }

  const handleDismissClearCart = () => {
    setShowClearCartModal(false)
  }

  const handleLogout = () => {
    if (window.Telegram?.WebApp?.close) {
      window.Telegram?.WebApp?.close?.()
      return
    }
    toast.info('Chiqish uchun Telegram oynasini yoping')
  }

  const handleSupport = () => {
    const link = 'https://t.me/fudly_support'
    if (window.Telegram?.WebApp?.openTelegramLink) {
      window.Telegram?.WebApp?.openTelegramLink?.(link)
      return
    }
    window.open(link, '_blank', 'noopener,noreferrer')
  }

  const formatDate = (dateStr) => {
    if (!dateStr) return ''
    try {
      const date = new Date(dateStr)
      if (Number.isNaN(date.getTime())) return toText(dateStr)
      const now = new Date()
      const diffDays = Math.floor((now - date) / (1000 * 60 * 60 * 24))

      if (diffDays === 0) return 'Bugun'
      if (diffDays === 1) return 'Kecha'
      if (diffDays < 7) return `${diffDays} kun oldin`

      return date.toLocaleDateString('uz-UZ', {
        day: 'numeric',
        month: 'short'
      })
    } catch {
      return toText(dateStr)
    }
  }

  const languageLabel = lang === 'ru'
    ? 'Русский'
    : (lang === 'en' ? 'English' : "O'zbekcha")

  const settingsItems = [
    {
      id: 'payments',
      label: "To'lov usullari",
      icon: CreditCard,
      tone: 'blue',
      onClick: () => toast.info("To'lov usullari tez orada")
    },
    {
      id: 'addresses',
      label: 'Manzillarim',
      icon: MapPin,
      tone: 'orange',
      onClick: () => toast.info("Manzillar ro'yxati tez orada")
    },
    {
      id: 'language',
      label: 'Ilova tili',
      icon: Globe,
      tone: 'purple',
      value: languageLabel,
      onClick: () => toast.info('Til sozlamalari tez orada')
    },
    {
      id: 'support',
      label: "Qo'llab-quvvatlash",
      icon: LifeBuoy,
      tone: 'green',
      onClick: handleSupport
    },
  ]

  return (
    <div ref={containerRef} className="yana-page">
      <PullToRefresh
        isRefreshing={isRefreshing}
        pullDistance={pullDistance}
        progress={progress}
      />

      <header className="profile-topbar">
        <div className="profile-topbar-inner">
          <div className="profile-topbar-center">
            <h1 className="profile-title">Profil</h1>
            <button
              type="button"
              className="profile-topbar-action"
              onClick={handleEditProfile}
              aria-label="Tahrirlash"
              title="Tahrirlash"
            >
              <Pencil size={16} strokeWidth={2.2} />
            </button>
          </div>
        </div>
      </header>

      <section className="profile-header" aria-label="Profil">
        <div className="profile-avatar-wrap">
          <div className={`profile-avatar ${avatarUrl ? 'has-photo' : ''}`}>
            {avatarUrl ? (
              <img
                src={avatarUrl}
                alt={profileName}
                loading="eager"
                decoding="async"
              />
            ) : (
              <span className="profile-initial">{profileInitial}</span>
            )}
          </div>
          {resolvedPhone && (
            <div className="profile-verify" title="Tasdiqlangan">
              <Leaf size={14} strokeWidth={2.2} />
            </div>
          )}
        </div>
        <h2 className="profile-name">{profileName}</h2>
        {profileHandle && <div className="profile-handle">@{profileHandle}</div>}
        <div className="profile-stat-pill">
          <span className="profile-stat-icon"><Leaf size={16} /></span>
          <span>
            <strong>{savedMetric.value}{savedMetric.unit}</strong> ovqat qutqarildi
          </span>
        </div>
        {(resolvedPhone || resolvedCity) && (
          <div className="profile-meta-row">
            {resolvedPhone && <span className="profile-meta-chip">{resolvedPhone}</span>}
            {resolvedCity && <span className="profile-meta-chip muted">{resolvedCity}</span>}
          </div>
        )}
      </section>


      <section className="profile-section notifications-section">
        <button
          type="button"
          className="notifications-accordion"
          onClick={() => setNotificationsOpen((prev) => !prev)}
          aria-expanded={notificationsOpen}
        >
          <div className="notifications-accordion-left">
            <div className="settings-icon tone-blue">
              <Bell size={18} strokeWidth={2} />
            </div>
            <div className="notifications-accordion-text">
              <span className="notifications-accordion-title">Bildirishnomalar</span>
              <span className="notifications-accordion-subtitle">
                {notifications ? 'Yoqilgan' : "O'chirilgan"}
              </span>
            </div>
          </div>
          <ChevronRight
            size={18}
            className={`notifications-accordion-chevron ${notificationsOpen ? 'open' : ''}`}
          />
        </button>

        {notificationsOpen && (
          <div className="notifications-body">
            <div className="notifications-card">
              <div className="notifications-toggle-row">
                <span className="notifications-label">Yangiliklar va statuslar</span>
                <button
                  className={`toggle ${notifications ? 'on' : ''}`}
                  onClick={handleToggleNotifications}
                >
                  <span className="toggle-knob"></span>
                </button>
              </div>
            </div>

            <div className="notifications-header">
              <h4 className="notifications-title">So'nggi bildirishnomalar</h4>
              <button className="clear-notifications-btn" onClick={handleClearNotifications}>
                Tozalash
              </button>
            </div>

            {notificationsLoading ? (
              <div className="profile-section-loading">
                <div className="profile-spinner"></div>
                <p>Yuklanmoqda...</p>
              </div>
            ) : notificationsList.length === 0 ? (
              <div className="profile-empty-state">
                <div className="profile-empty-icon">!</div>
                <h3>Bildirishnomalar yo'q</h3>
                <p>Yangi xabarlar shu yerda paydo bo'ladi.</p>
              </div>
            ) : (
              <div className="notifications-list">
                {notificationsList.map((item) => (
                  <div
                    key={item.id}
                    className={`notification-card notification-${item.type || 'system'}`}
                  >
                    <div className="notification-header">
                      <span className="notification-title">{item.title}</span>
                      <span className="notification-date">{formatDate(item.created_at)}</span>
                    </div>
                    <p className="notification-message">{item.message}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </section>

      <section className="profile-section settings-section">
        <h3 className="profile-section-label">Sozlamalar</h3>
        <div className="settings-list">
          {settingsItems.map((item) => {
            const Icon = item.icon
            return (
              <button
                key={item.id}
                type="button"
                className="settings-item"
                onClick={item.onClick}
              >
                <div className="settings-item-left">
                  <div className={`settings-icon tone-${item.tone}`}>
                    <Icon size={18} strokeWidth={2} />
                  </div>
                  <span className="settings-text">{item.label}</span>
                </div>
                <div className="settings-item-right">
                  {item.value && <span className="settings-value">{item.value}</span>}
                  <ChevronRight size={18} className="settings-chevron" />
                </div>
              </button>
            )
          })}
        </div>
      </section>

      <section className="profile-section danger-zone">
        <h3 className="danger-title">Xavfli amallar</h3>
        <p className="danger-note">
          Savatdagi barcha mahsulotlar o'chiriladi. Bu amalni qaytarib bo'lmaydi.
        </p>
        <button className="danger-btn" onClick={handleClearCart}>
          Savatni tozalash
        </button>
      </section>

      <div className="profile-logout">
        <button type="button" className="logout-btn" onClick={handleLogout}>
          <LogOut size={18} strokeWidth={2.2} />
          Chiqish
        </button>
        <p className="profile-version">Versiya 2.4.0</p>
      </div>

      {showClearCartModal && (
        <div className="confirm-modal-overlay" onClick={handleDismissClearCart}>
          <div
            className="confirm-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="clear-cart-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="confirm-modal-header">
              <h3 id="clear-cart-title">Savatni tozalash</h3>
            </div>
            <p className="confirm-modal-text">
              Savatdagi barcha mahsulotlar o'chiriladi. Davom etasizmi?
            </p>
            <div className="confirm-modal-actions">
              <button
                type="button"
                className="confirm-modal-btn secondary"
                onClick={handleDismissClearCart}
              >
                Bekor qilish
              </button>
              <button
                type="button"
                className="confirm-modal-btn danger"
                onClick={handleConfirmClearCart}
              >
                Tozalash
              </button>
            </div>
          </div>
        </div>
      )}

      <BottomNav currentPage="profile" cartCount={cartCount} />
    </div>
  )
}

export default YanaPage



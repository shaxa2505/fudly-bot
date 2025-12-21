import { useState } from 'react'
import { Package, Settings, Info } from 'lucide-react'
import { useCart } from '../context/CartContext'
import BottomNav from '../components/BottomNav'
import { getCurrentUser } from '../utils/auth'
import OrdersSection from './yana/OrdersSection'
import SettingsSection from './yana/SettingsSection'
import AboutSection from './yana/AboutSection'
import { useOrders } from './yana/useOrders'
import './YanaPage.css'

function YanaPage() {
  const [activeSection, setActiveSection] = useState('orders') // orders, settings, about
  const { orders, loading, orderFilter, setOrderFilter } = useOrders(activeSection)

  // Settings state - load from user profile first, then localStorage
  const [phone, setPhone] = useState(() => {
    const user = getCurrentUser()
    if (user?.phone) return user.phone
    // Try Telegram WebApp contact
    const tgPhone = window.Telegram?.WebApp?.initDataUnsafe?.user?.phone_number
    if (tgPhone) return tgPhone
    return localStorage.getItem('fudly_phone') || ''
  })
  const [location, setLocation] = useState(() => {
    try {
      const user = getCurrentUser()
      if (user?.city) return { city: user.city }
      return JSON.parse(localStorage.getItem('fudly_location') || '{}')
    } catch { return {} }
  })
  const [notifications, setNotifications] = useState(true)

  // Get cart count from context
  const { cartCount, clearCart } = useCart()
  const saveSettings = () => {
    localStorage.setItem('fudly_phone', phone)
    window.Telegram?.WebApp?.showAlert?.('Sozlamalar saqlandi!')
  }
  const handleClearCart = () => {
    if (window.confirm('Savatni tozalashni xohlaysizmi?')) {
      clearCart()
      window.Telegram?.WebApp?.showAlert?.('Savat tozalandi')
    }
  }

  const menuItems = [
    { id: 'orders', icon: Package, label: 'Buyurtmalarim' },
    { id: 'settings', icon: Settings, label: 'Sozlamalar' },
    { id: 'about', icon: Info, label: "Ilova haqida" },
  ]

  return (
    <div className="yana-page">
      {/* Header with menu */}
      <header className="yana-header">
        <h1 className="yana-title">Yana</h1>
        <div className="yana-menu">
          {menuItems.map(item => {
            const IconComponent = item.icon
            return (
              <button
                key={item.id}
                className={`yana-menu-item ${activeSection === item.id ? 'active' : ''}`}
                onClick={() => setActiveSection(item.id)}
              >
                <IconComponent size={20} strokeWidth={2} className="menu-icon" aria-hidden="true" />
                <span className="menu-label">{item.label}</span>
              </button>
            )
          })}
        </div>
      </header>
      {/* Orders Section */}
      {activeSection === 'orders' && (
        <OrdersSection
          orders={orders}
          loading={loading}
          orderFilter={orderFilter}
          onFilterChange={setOrderFilter}
        />
      )}
      {/* Settings Section */}
      {activeSection === 'settings' && (
        <SettingsSection
          phone={phone}
          setPhone={setPhone}
          location={location}
          notifications={notifications}
          setNotifications={setNotifications}
          onSave={saveSettings}
          onClearCart={handleClearCart}
        />
      )}
      {/* About Section */}
      {activeSection === 'about' && (
        <AboutSection />
      )}

      <BottomNav currentPage="profile" cartCount={cartCount} />
    </div>
  )
}

export default YanaPage

import { useState, useEffect } from 'react'
import api from '../api/client'
import BottomNav from '../components/BottomNav'
import './CartPage.css'

function CartPage({ onNavigate }) {
  const [cart, setCart] = useState(() => {
    const saved = localStorage.getItem('fudly_cart')
    return saved ? new Map(Object.entries(JSON.parse(saved))) : new Map()
  })
  const [cartData, setCartData] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (cart.size === 0) {
      setCartData(null)
      return
    }

    const loadCartData = async () => {
      try {
        const items = Array.from(cart.entries()).map(([id, qty]) => ({
          offerId: parseInt(id),
          quantity: qty,
        }))

        const data = await api.calculateCart(items)
        setCartData(data)
      } catch (error) {
        console.error('Error loading cart:', error)
      }
    }

    loadCartData()
  }, [cart])

  useEffect(() => {
    localStorage.setItem('fudly_cart', JSON.stringify(Object.fromEntries(cart)))
  }, [cart])

  const updateQuantity = (offerId, delta) => {
    setCart(prev => {
      const next = new Map(prev)
      const current = next.get(String(offerId)) || 0
      const newQty = current + delta

      if (newQty <= 0) {
        next.delete(String(offerId))
      } else {
        next.set(String(offerId), newQty)
      }

      return next
    })
  }

  const clearCart = () => {
    if (window.Telegram?.WebApp?.showConfirm) {
      window.Telegram.WebApp.showConfirm('Savatni tozalashni xohlaysizmi?', (confirmed) => {
        if (confirmed) {
          setCart(new Map())
          setCartData(null)
        }
      })
    } else {
      if (confirm('Savatni tozalashni xohlaysizmi?')) {
        setCart(new Map())
        setCartData(null)
      }
    }
  }

  const placeOrder = async () => {
    if (!cartData || cartData.items.length === 0) return

    setLoading(true)
    try {
      const userId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id || 0

      const orderData = {
        items: cartData.items.map(item => ({
          offer_id: item.offer_id,
          quantity: item.quantity,
        })),
        user_id: userId,
      }

      const result = await api.createOrder(orderData)

      window.Telegram?.WebApp?.showAlert?.(
        `Buyurtma #${result.order_id} qabul qilindi!\n\nSumma: ${Math.round(result.total).toLocaleString()} so'm\nMahsulotlar: ${result.items_count} ta`,
        () => {
          setCart(new Map())
          setCartData(null)
          onNavigate('home')
        }
      )
    } catch (error) {
      console.error('Error placing order:', error)
      window.Telegram?.WebApp?.showAlert?.('Xatolik yuz berdi')
    } finally {
      setLoading(false)
    }
  }

  if (!cartData || cartData.items.length === 0) {
    return (
      <div className="cart-page">
        <header className="page-header">
          <button className="back-btn" onClick={() => onNavigate('home')}>
            ← Orqaga
          </button>
          <h1>Savat</h1>
          <div></div>
        </header>

        <div className="empty-state">
          <div className="empty-icon">🛒</div>
          <h2>Savat bo'sh</h2>
          <p>Katalogdan mahsulotlar qo'shing</p>
          <button className="primary-btn" onClick={() => onNavigate('home')}>
            Katalogga o'tish
          </button>
        </div>

        <BottomNav currentPage="cart" onNavigate={onNavigate} cartCount={0} />
      </div>
    )
  }

  return (
    <div className="cart-page">
      <header className="page-header">
        <button className="back-btn" onClick={() => onNavigate('home')}>
          ← Orqaga
        </button>
        <h1>Savat ({cartData.items_count})</h1>
        <button className="clear-btn" onClick={clearCart}>
          Tozalash
        </button>
      </header>

      <div className="cart-content">
        <div className="cart-items">
          {cartData.items.map(item => (
            <div key={item.offer_id} className="cart-item">
              <img
                src={item.photo || 'https://via.placeholder.com/80'}
                alt={item.title}
                className="item-image"
              />

              <div className="item-info">
                <h3 className="item-title">{item.title}</h3>
                <p className="item-price">{Math.round(item.price).toLocaleString()} so'm</p>
              </div>

              <div className="item-controls">
                <button
                  className="qty-btn"
                  onClick={() => updateQuantity(item.offer_id, -1)}
                >
                  −
                </button>
                <span className="qty">{item.quantity}</span>
                <button
                  className="qty-btn"
                  onClick={() => updateQuantity(item.offer_id, 1)}
                >
                  +
                </button>
              </div>
            </div>
          ))}
        </div>

        <div className="cart-footer">
          <div className="total-section">
            <div className="total-row">
              <span>Mahsulotlar ({cartData.items_count} ta)</span>
              <span>{Math.round(cartData.total).toLocaleString()} so'm</span>
            </div>
            <div className="total-row">
              <span>Yetkazib berish</span>
              <span className="free">Bepul</span>
            </div>
            <div className="total-row final">
              <span>Jami</span>
              <span>{Math.round(cartData.total).toLocaleString()} so'm</span>
            </div>
          </div>

          <button
            className="checkout-btn"
            onClick={placeOrder}
            disabled={loading}
          >
            {loading ? 'Yuborilmoqda...' : 'Buyurtma berish'}
          </button>
        </div>
      </div>

      <BottomNav currentPage="cart" onNavigate={onNavigate} cartCount={cartData.items_count} />
    </div>
  )
}

export default CartPage

import { useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useCart } from '../../context/CartContext'
import BottomNav from '../../components/BottomNav'
import CartItem from './CartItem'
import CheckoutForm from './CheckoutForm'
import OrderSummary from './OrderSummary'
import PaymentUpload from './PaymentUpload'
import { useCheckout } from './useCheckout'
import '../CartPage.css'

/**
 * Refactored CartPage component
 * Now ~150 lines instead of 770 lines
 * Uses modular components and custom hook
 */
function CartPageRefactored({ user }) {
  const navigate = useNavigate()
  const { cartItems, isEmpty, updateQuantity, removeItem } = useCart()

  const checkout = useCheckout()

  // Handle quantity changes
  const handleIncrement = useCallback((offerId) => {
    const item = cartItems.find(i => i.offer.id === offerId)
    if (item) {
      updateQuantity(offerId, item.quantity + 1)
    }
  }, [cartItems, updateQuantity])

  const handleDecrement = useCallback((offerId) => {
    const item = cartItems.find(i => i.offer.id === offerId)
    if (item) {
      const newQty = item.quantity - 1
      if (newQty <= 0) {
        removeItem(offerId)
      } else {
        updateQuantity(offerId, newQty)
      }
    }
  }, [cartItems, updateQuantity, removeItem])

  // Handle checkout button
  const handleCheckout = useCallback(() => {
    if (isEmpty) return
    checkout.setCheckoutStep('details')
    checkout.setShowCheckout(true)
  }, [isEmpty, checkout])

  // Handle checkout form submission
  const handleCheckoutSubmit = useCallback(async () => {
    const shouldPlaceOrder = await checkout.proceedToPayment()

    if (shouldPlaceOrder) {
      // Pickup order - place immediately
      const result = await checkout.placeOrder()

      if (result) {
        // Navigate to order tracking
        navigate(`/order/${result.order_id || result.id}`)
      }
    }
    // Delivery order - show payment step (handled in useCheckout)
  }, [checkout, navigate])

  // Handle payment upload submission
  const handlePaymentSubmit = useCallback(async () => {
    // First create order if not created
    if (!checkout.createdOrderId) {
      const result = await checkout.placeOrder()
      if (!result) return
    }

    // Upload payment proof
    const success = await checkout.uploadPaymentProof()

    if (success) {
      // Navigate to order tracking
      navigate(`/order/${checkout.createdOrderId}`)
    }
  }, [checkout, navigate])

  // Empty cart UI
  if (isEmpty && !checkout.showCheckout) {
    return (
      <div className="cart-page">
        <div className="cart-header">
          <button className="back-btn" onClick={() => navigate(-1)}>
            ← Orqaga
          </button>
          <h1>🛒 Savat</h1>
        </div>

        <div className="empty-cart">
          <div className="empty-icon">🛒</div>
          <h2>Savat bo'sh</h2>
          <p>Mahsulot qo'shish uchun do'konlarni ko'ring</p>
          <button className="btn-primary" onClick={() => navigate('/')}>
            Bosh sahifa
          </button>
        </div>

        <BottomNav currentPage="cart" />
      </div>
    )
  }

  return (
    <div className="cart-page">
      {/* Header */}
      <div className="cart-header">
        <button className="back-btn" onClick={() => navigate(-1)}>
          ← Orqaga
        </button>
        <h1>🛒 Savat ({checkout.itemsCount})</h1>
      </div>

      {/* Cart Items */}
      {!checkout.showCheckout && (
        <div className="cart-content">
          <div className="cart-items">
            {cartItems.map((item) => (
              <CartItem
                key={item.offer.id}
                item={item}
                onIncrement={handleIncrement}
                onDecrement={handleDecrement}
                onRemove={removeItem}
              />
            ))}
          </div>

          {/* Summary */}
          <OrderSummary
            subtotal={checkout.subtotal}
            deliveryFee={checkout.deliveryFee}
            total={checkout.total}
            itemsCount={checkout.itemsCount}
            orderType={checkout.orderType}
          />

          {/* Checkout Button */}
          <div className="cart-actions">
            <button
              className="btn-primary btn-large"
              onClick={handleCheckout}
              disabled={isEmpty}
            >
              Rasmiylashtirish 🎯
            </button>
          </div>
        </div>
      )}

      {/* Checkout Modal */}
      {checkout.showCheckout && (
        <div className="checkout-modal">
          <div className="checkout-modal-content">
            {/* Step 1: Details */}
            {checkout.checkoutStep === 'details' && (
              <CheckoutForm
                phone={checkout.phone}
                setPhone={checkout.setPhone}
                address={checkout.address}
                setAddress={checkout.setAddress}
                comment={checkout.comment}
                setComment={checkout.setComment}
                orderType={checkout.orderType}
                setOrderType={checkout.setOrderType}
                storeDeliveryEnabled={checkout.storeDeliveryEnabled}
                deliveryReason={checkout.deliveryReason}
                canDelivery={checkout.canDelivery}
                minOrderAmount={checkout.minOrderAmount}
                onSubmit={handleCheckoutSubmit}
                onCancel={() => checkout.setShowCheckout(false)}
                loading={checkout.orderLoading}
              />
            )}

            {/* Step 2: Payment (for delivery) */}
            {checkout.checkoutStep === 'payment' && (
              <PaymentUpload
                paymentCard={checkout.paymentCard}
                paymentProof={checkout.paymentProof}
                paymentProofPreview={checkout.paymentProofPreview}
                onFileSelect={checkout.handleFileSelect}
                onSubmit={handlePaymentSubmit}
                onCancel={() => checkout.setCheckoutStep('details')}
                loading={checkout.orderLoading}
              />
            )}

            {/* Order Summary in sidebar */}
            <OrderSummary
              subtotal={checkout.subtotal}
              deliveryFee={checkout.deliveryFee}
              total={checkout.total}
              itemsCount={checkout.itemsCount}
              orderType={checkout.orderType}
            />
          </div>
        </div>
      )}

      {/* Success/Error Result */}
      {checkout.orderResult && (
        <div className="order-result-modal">
          <div className="order-result-content">
            {checkout.orderResult.success ? (
              <>
                <div className="result-icon success">✅</div>
                <h2>Buyurtma qabul qilindi!</h2>
                <p>Tez orada operator siz bilan bog'lanadi</p>
                <button
                  className="btn-primary"
                  onClick={() => navigate('/')}
                >
                  Bosh sahifa
                </button>
              </>
            ) : (
              <>
                <div className="result-icon error">❌</div>
                <h2>Xatolik yuz berdi</h2>
                <p>{checkout.orderResult.error}</p>
                <button
                  className="btn-primary"
                  onClick={() => checkout.setOrderResult(null)}
                >
                  Qayta urinish
                </button>
              </>
            )}
          </div>
        </div>
      )}

      <BottomNav currentPage="cart" />
    </div>
  )
}

export default CartPageRefactored

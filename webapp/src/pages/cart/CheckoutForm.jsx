import { memo } from 'react'

/**
 * Checkout form component
 * Handles user input for phone, address, comment
 */
const CheckoutForm = memo(function CheckoutForm({
  phone,
  setPhone,
  address,
  setAddress,
  comment,
  setComment,
  orderType,
  setOrderType,
  storeDeliveryEnabled,
  deliveryReason,
  canDelivery,
  minOrderAmount,
  onSubmit,
  onCancel,
  loading,
}) {
  const formatPrice = (price) => {
    return price.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' ')
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    onSubmit()
  }

  return (
    <form className="checkout-form" onSubmit={handleSubmit}>
      <h3 className="checkout-title">📝 Ma'lumotlarni kiriting</h3>

      {/* Phone Input */}
      <div className="form-group">
        <label htmlFor="phone">📞 Telefon raqam *</label>
        <input
          type="tel"
          id="phone"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          placeholder="+998 90 123 45 67"
          required
          className="form-input"
        />
      </div>

      {/* Delivery Type Selection */}
      <div className="form-group">
        <label>🚚 Olish usuli *</label>
        <div className="delivery-type-options">
          <button
            type="button"
            className={`delivery-option ${orderType === 'pickup' ? 'active' : ''}`}
            onClick={() => setOrderType('pickup')}
          >
            <span className="option-icon">🏪</span>
            <div className="option-content">
              <strong>Do'kondan olish</strong>
              <small>Bepul</small>
            </div>
          </button>

          <button
            type="button"
            className={`delivery-option ${orderType === 'delivery' ? 'active' : ''} ${!storeDeliveryEnabled ? 'disabled' : ''}`}
            onClick={() => storeDeliveryEnabled && setOrderType('delivery')}
            disabled={!storeDeliveryEnabled}
          >
            <span className="option-icon">🚚</span>
            <div className="option-content">
              <strong>Yetkazib berish</strong>
              <small>
                {storeDeliveryEnabled
                  ? 'Mavjud'
                  : deliveryReason || 'Mavjud emas'}
              </small>
            </div>
          </button>
        </div>

        {orderType === 'delivery' && !canDelivery && (
          <div className="form-hint warning">
            ⚠️ Minimal buyurtma summasi: {formatPrice(minOrderAmount)} so'm
          </div>
        )}
      </div>

      {/* Address Input (only for delivery) */}
      {orderType === 'delivery' && (
        <div className="form-group">
          <label htmlFor="address">📍 Yetkazib berish manzili *</label>
          <textarea
            id="address"
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            placeholder="Manzilni kiriting: Ko'cha, uy raqami, kvartira..."
            required
            className="form-textarea"
            rows={3}
          />
        </div>
      )}

      {/* Comment (optional) */}
      <div className="form-group">
        <label htmlFor="comment">💬 Izoh (ixtiyoriy)</label>
        <textarea
          id="comment"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="Qo'shimcha ma'lumot..."
          className="form-textarea"
          rows={2}
        />
      </div>

      {/* Actions */}
      <div className="form-actions">
        <button
          type="button"
          className="btn-secondary"
          onClick={onCancel}
          disabled={loading}
        >
          Bekor qilish
        </button>
        <button
          type="submit"
          className="btn-primary"
          disabled={loading || (orderType === 'delivery' && !canDelivery)}
        >
          {loading ? 'Yuklanmoqda...' : 'Davom etish'}
        </button>
      </div>
    </form>
  )
})

export default CheckoutForm

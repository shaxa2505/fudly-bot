import { memo } from 'react'

/**
 * Payment upload component
 * Handles payment proof upload for delivery orders
 */
const PaymentUpload = memo(function PaymentUpload({
  paymentCard,
  paymentProof,
  paymentProofPreview,
  onFileSelect,
  onSubmit,
  onCancel,
  loading,
}) {
  const handleSubmit = (e) => {
    e.preventDefault()
    onSubmit()
  }

  return (
    <div className="payment-upload">
      <h3 className="payment-title">💳 To'lov ma'lumotlari</h3>

      {/* Payment Card Info */}
      {paymentCard && (
        <div className="payment-card-info">
          <div className="card-number">
            <label>Karta raqami:</label>
            <div className="card-number-value">
              {paymentCard.card_number || 'Ma\'lumot yo\'q'}
            </div>
          </div>

          <div className="card-owner">
            <label>Karta egasi:</label>
            <div className="card-owner-value">
              {paymentCard.card_holder || 'Ma\'lumot yo\'q'}
            </div>
          </div>

          <div className="payment-instruction">
            <p>1️⃣ Yuqoridagi kartaga pul o'tkazing</p>
            <p>2️⃣ To'lov chekini rasmga oling</p>
            <p>3️⃣ Chek rasmini yuklang</p>
          </div>
        </div>
      )}

      {/* File Upload */}
      <div className="file-upload-container">
        <label htmlFor="payment-proof-input" className="file-upload-label">
          {paymentProofPreview ? (
            <div className="preview-container">
              <img src={paymentProofPreview} alt="Payment proof" className="payment-preview" />
              <div className="preview-overlay">
                <span>📷 Yangi rasm tanlash</span>
              </div>
            </div>
          ) : (
            <div className="upload-placeholder">
              <span className="upload-icon">📤</span>
              <span className="upload-text">To'lov chekini yuklang</span>
              <span className="upload-hint">JPG, PNG (max 5MB)</span>
            </div>
          )}
        </label>
        <input
          type="file"
          id="payment-proof-input"
          accept="image/*"
          onChange={onFileSelect}
          className="file-input-hidden"
        />
      </div>

      {/* Actions */}
      <form onSubmit={handleSubmit}>
        <div className="form-actions">
          <button
            type="button"
            className="btn-secondary"
            onClick={onCancel}
            disabled={loading}
          >
            Orqaga
          </button>
          <button
            type="submit"
            className="btn-primary"
            disabled={!paymentProof || loading}
          >
            {loading ? 'Yuklanmoqda...' : 'Buyurtmani tasdiqlash'}
          </button>
        </div>
      </form>
    </div>
  )
})

export default PaymentUpload

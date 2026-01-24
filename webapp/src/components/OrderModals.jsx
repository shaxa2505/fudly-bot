import './OrderModals.css'

export function OrderFailedModal({ onClose, onRetry }) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close-btn" onClick={onClose}>
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <path d="M18 6L6 18M6 6l12 12" stroke="#181725" strokeWidth="2" strokeLinecap="round"/>
          </svg>
        </button>

        <div className="modal-illustration">
          <div className="illustration-circle error">
            <div className="grocery-bag">
              ORDER
            </div>
          </div>
        </div>

        <h2 className="modal-title">Xatolik! Buyurtma Bajarilmadi</h2>
        <p className="modal-description">
          Nimadir noto'g'ri ketdi
        </p>

        <button className="modal-primary-btn" onClick={onRetry}>
          Yana Urinib Ko'ring
        </button>
        <button className="modal-secondary-btn" onClick={onClose}>
          Bosh sahifaga qaytish
        </button>
      </div>
    </div>
  )
}

export function OrderSuccessModal({ onClose, onTrack }) {
  return (
    <div className="modal-overlay success-bg">
      <div className="modal-content success-content">
        <div className="modal-illustration">
          <div className="illustration-circle success">
            <svg width="80" height="80" viewBox="0 0 24 24" fill="none">
              <path d="M20 6L9 17l-5-5" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </div>
          <div className="success-confetti">
            <span className="confetti" style={{top: '20%', left: '10%'}}>*</span>
            <span className="confetti" style={{top: '30%', right: '15%'}}>*</span>
            <span className="confetti" style={{top: '60%', left: '20%'}}>*</span>
            <span className="confetti" style={{bottom: '20%', right: '10%'}}>*</span>
            <span className="confetti-line" style={{top: '15%', left: '25%', rotate: '45deg'}}>~</span>
            <span className="confetti-line" style={{top: '25%', right: '20%', rotate: '-45deg'}}>~</span>
          </div>
        </div>

        <h2 className="modal-title">Buyurtmangiz Qabul Qilindi</h2>
        <p className="modal-description">
          Mahsulotlaringiz joylashtirildi va qayta ishlanmoqda
        </p>

        <button className="modal-primary-btn" onClick={onTrack}>
          Buyurtmani Kuzatish
        </button>
        <button className="modal-secondary-btn" onClick={onClose}>
          Bosh sahifaga qaytish
        </button>
      </div>
    </div>
  )
}

export function CheckoutModal({ onClose, onPlaceOrder, totalCost, loading }) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="checkout-modal" onClick={(e) => e.stopPropagation()}>
        <div className="checkout-header">
          <h2 className="checkout-title">To'lov</h2>
          <button className="modal-close-btn" onClick={onClose}>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <path d="M18 6L6 18M6 6l12 12" stroke="#181725" strokeWidth="2" strokeLinecap="round"/>
            </svg>
          </button>
        </div>

        <div className="checkout-options">
          <div className="checkout-row">
            <span className="checkout-label">Yetkazish</span>
            <button className="checkout-value">
              Usulni Tanlang
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <path d="M9 18l6-6-6-6" stroke="#181725" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
          </div>

          <div className="checkout-row">
            <span className="checkout-label">To'lov</span>
            <button className="checkout-value">
              <span className="payment-icon">CLICK</span>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <path d="M9 18l6-6-6-6" stroke="#181725" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
          </div>

          <div className="checkout-row">
            <span className="checkout-label">Promo Kod</span>
            <button className="checkout-value">
              Chegirmani Tanlang
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <path d="M9 18l6-6-6-6" stroke="#181725" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
          </div>

          <div className="checkout-row total-row">
            <span className="checkout-label">Jami Summa</span>
            <button className="checkout-value total-value">
              {totalCost.toLocaleString()} so'm
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <path d="M9 18l6-6-6-6" stroke="#181725" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
          </div>
        </div>

        <div className="checkout-footer">
          <p className="checkout-terms">
            Buyurtma berib, siz bizning{' '}
            <button className="terms-link">Shartlar</button> va{' '}
            <button className="terms-link">Qoidalar</button>ga rozilik bildirasiz
          </p>
          <button
            className="place-order-btn"
            onClick={onPlaceOrder}
            disabled={loading}
            style={{ opacity: loading ? 0.7 : 1, cursor: loading ? 'wait' : 'pointer' }}
          >
            {loading ? 'Yuklanmoqda...' : 'Buyurtma Berish'}
          </button>
        </div>
      </div>
    </div>
  )
}

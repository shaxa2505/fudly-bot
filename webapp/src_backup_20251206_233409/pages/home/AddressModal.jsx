const AddressModal = ({
  isOpen,
  onClose,
  manualCity,
  onCityChange,
  manualAddress,
  onAddressChange,
  onSave,
  onDetectLocation,
  isLocating,
  locationError,
}) => {
  if (!isOpen) {
    return null
  }

  return (
    <div className="address-modal-overlay" onClick={onClose}>
      <div className="address-modal" onClick={(event) => event.stopPropagation()}>
        <div className="address-modal-header">
          <h3>Manzilni kiriting</h3>
          <button className="address-modal-close" onClick={onClose} aria-label="Yopish">
            ×
          </button>
        </div>

        <button className="address-detect-btn" onClick={onDetectLocation} disabled={isLocating}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="2"/>
            <path d="M12 2v4M12 18v4M2 12h4M18 12h4" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
          </svg>
          {isLocating ? "Aniqlanmoqda..." : "Joylashuvni aniqlash"}
        </button>

        {locationError && (
          <div className="address-error">{locationError}</div>
        )}

        <div className="address-divider">
          <span>yoki</span>
        </div>

        <label className="address-label">
          Shahar yoki hudud
          <input
            type="text"
            value={manualCity}
            onChange={(event) => onCityChange(event.target.value)}
            className="address-input"
            placeholder="Masalan, Toshkent, O'zbekiston"
          />
        </label>
        <label className="address-label">
          Aniq manzil
          <textarea
            value={manualAddress}
            onChange={(event) => onAddressChange(event.target.value)}
            className="address-textarea"
            placeholder="Ko'cha, uy, blok, mo'ljal"
          />
        </label>
        <div className="address-modal-actions">
          <button className="address-btn secondary" onClick={onClose}>
            Bekor qilish
          </button>
          <button className="address-btn" onClick={onSave}>
            Saqlash
          </button>
        </div>
      </div>
    </div>
  )
}

export default AddressModal

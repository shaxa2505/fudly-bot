import { blurOnEnter } from '../../utils/helpers'

function SettingsSection({
  phone,
  setPhone,
  location,
  notifications,
  setNotifications,
  onSave,
  onClearCart,
}) {
  return (
    <div className="yana-section settings-section">
      <div className="settings-group">
        <h3 className="group-title">👤 Shaxsiy ma'lumotlar</h3>

        <label className="setting-item">
          <span className="setting-label">📱 Telefon raqam</span>
          <input
            type="tel"
            className="setting-input"
            placeholder="+998 90 123 45 67"
            value={phone}
            onChange={e => setPhone(e.target.value)}
            onKeyDown={blurOnEnter}
          />
        </label>

        <label className="setting-item">
          <span className="setting-label">📍 Shahar</span>
          <input
            type="text"
            className="setting-input"
            value={location.city || ''}
            readOnly
            placeholder="Joylashuvni aniqlang"
          />
        </label>

        <button className="save-btn" onClick={onSave}>
          💾 Saqlash
        </button>
      </div>

      <div className="settings-group">
        <h3 className="group-title">🔔 Bildirishnomalar</h3>

        <div className="setting-item toggle-item">
          <span className="setting-label">Yangi takliflar</span>
          <button
            className={`toggle ${notifications ? 'on' : ''}`}
            onClick={() => setNotifications(!notifications)}
          >
            <span className="toggle-knob"></span>
          </button>
        </div>
      </div>

      <div className="settings-group">
        <h3 className="group-title">🗑️ Ma'lumotlarni tozalash</h3>

        <button
          className="danger-btn"
          onClick={onClearCart}
        >
          🛒 Savatni tozalash
        </button>
      </div>
    </div>
  )
}

export default SettingsSection

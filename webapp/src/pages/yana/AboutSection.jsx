function AboutSection() {
  return (
    <div className="yana-section about-section">
      <div className="about-logo">
        <span className="logo-icon">🍽️</span>
        <h2>Fudly</h2>
        <p className="version">v2.0.0</p>
      </div>

      <div className="about-description">
        <p>
          Fudly - oziq-ovqat mahsulotlarini chegirmali narxlarda sotib olish uchun ilova.
        </p>
        <p>
          Muddati o'tayotgan yoki ortiqcha mahsulotlarni arzon narxda oling va isrofgarchilikni kamaytiring! 🌱
        </p>
      </div>

      <div className="about-features">
        <div className="feature-item">
          <span className="feature-icon">💰</span>
          <div>
            <h4>70% gacha chegirma</h4>
            <p>Eng yaxshi takliflar</p>
          </div>
        </div>
        <div className="feature-item">
          <span className="feature-icon">🏪</span>
          <div>
            <h4>Do'konlar tarmog'i</h4>
            <p>Yaqin atrofdagi do'konlar</p>
          </div>
        </div>
        <div className="feature-item">
          <span className="feature-icon">🚚</span>
          <div>
            <h4>Yetkazib berish</h4>
            <p>Tez va qulay</p>
          </div>
        </div>
      </div>

      <div className="about-links">
        <a href="https://t.me/fudly_support" className="link-item">
          💬 Qo'llab-quvvatlash
        </a>
        <a href="https://t.me/fudly_channel" className="link-item">
          📣 Telegram kanal
        </a>
      </div>

      <p className="copyright">© 2024 Fudly. Barcha huquqlar himoyalangan.</p>
    </div>
  )
}

export default AboutSection

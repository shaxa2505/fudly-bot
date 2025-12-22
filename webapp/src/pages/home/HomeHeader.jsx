import { blurOnEnter } from '../../utils/helpers'

const HomeHeader = ({
  city,
  isScrolled,
  onSelectAddress,
  onNavigateFavorites,
  onNavigateProfile,
  searchQuery,
  onSearchChange,
  onSubmitSearch,
  searchInputRef,
  showSearchHistory,
  searchHistory,
  onHistoryClick,
  onClearHistory,
  setShowSearchHistory,
  loading,
  loadError,
  onRetryLoad,
}) => {
  const handleSearchKeyDown = (event) => {
    blurOnEnter(event, onSubmitSearch)
  }

  return (
    <header className={`header ${isScrolled ? 'scrolled' : ''}`}>
      <div className="header-top">
        <button className="header-location" onClick={onSelectAddress}>
          <div className="header-location-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
              <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" stroke="var(--color-primary)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <circle cx="12" cy="10" r="3" stroke="var(--color-primary)" strokeWidth="2"/>
            </svg>
          </div>
          <div className="header-location-text">
            <span className="header-location-label">Yetkazish</span>
            <span className="header-location-city">
              {city}
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none">
                <path d="M6 9l6 6 6-6" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </span>
          </div>
        </button>
        <div className="header-actions">
          <button className="header-action-btn" onClick={onNavigateFavorites} aria-label="Sevimlilar">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
          <button className="header-action-btn" onClick={onNavigateProfile} aria-label="Profil">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="8" r="4" stroke="currentColor" strokeWidth="2"/>
              <path d="M6 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            </svg>
          </button>
        </div>
      </div>
      <div className="header-search">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" className="search-icon">
          <circle cx="11" cy="11" r="8" stroke="currentColor" strokeWidth="2"/>
          <path d="M21 21l-4.35-4.35" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
        </svg>
        <input
          ref={searchInputRef}
          type="text"
          className="search-input"
          placeholder="Mahsulot qidirish..."
          value={searchQuery}
          onChange={(event) => onSearchChange(event.target.value)}
          onFocus={() => setShowSearchHistory(true)}
          onBlur={() => setTimeout(() => setShowSearchHistory(false), 200)}
          onKeyDown={handleSearchKeyDown}
        />
        {loading && (
          <span className="search-spinner" role="status" aria-label="Yuklanmoqda" />
        )}
        {searchQuery && (
          <button className="search-clear" onClick={() => onSearchChange('')}>
            x
          </button>
        )}

        {showSearchHistory && searchHistory.length > 0 && !searchQuery && (
          <div className="search-history-dropdown">
            <div className="search-history-header">
              <span>So'nggi qidiruvlar</span>
              <button className="search-history-clear" onClick={onClearHistory}>
                Tozalash
              </button>
            </div>
            {searchHistory.map((query, index) => (
              <button
                key={index}
                className="search-history-item"
                onMouseDown={() => onHistoryClick(query)}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2"/>
                  <path d="M12 6v6l4 2" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                </svg>
                <span>{query}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {loading && (
        <div className="search-status" role="status" aria-live="polite">
          Qidirilmoqda...
        </div>
      )}

      {loadError && (
        <div className="load-error" role="alert">
          <span>{loadError}</span>
          <button onClick={onRetryLoad}>Qayta yuklash</button>
        </div>
      )}
    </header>
  )
}

export default HomeHeader

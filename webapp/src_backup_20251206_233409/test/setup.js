import '@testing-library/jest-dom'

// Mock Telegram WebApp
window.Telegram = {
  WebApp: {
    ready: () => {},
    expand: () => {},
    close: () => {},
    initData: 'mock_init_data',
    initDataUnsafe: {
      user: {
        id: 123456789,
        first_name: 'Test',
        last_name: 'User',
        username: 'testuser',
        language_code: 'uz',
      },
    },
    themeParams: {
      bg_color: '#ffffff',
      text_color: '#000000',
      button_color: '#53B175',
    },
    HapticFeedback: {
      impactOccurred: () => {},
      notificationOccurred: () => {},
    },
    MainButton: {
      show: () => {},
      hide: () => {},
      setText: () => {},
      onClick: () => {},
      offClick: () => {},
    },
    BackButton: {
      show: () => {},
      hide: () => {},
      onClick: () => {},
      offClick: () => {},
    },
  },
}

// Mock IntersectionObserver
class MockIntersectionObserver {
  constructor(callback) {
    this.callback = callback
  }
  observe() {}
  unobserve() {}
  disconnect() {}
}
window.IntersectionObserver = MockIntersectionObserver

// Mock ResizeObserver
class MockResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
window.ResizeObserver = MockResizeObserver

// Suppress console errors in tests
const originalError = console.error
console.error = (...args) => {
  if (args[0]?.includes?.('Warning:')) return
  originalError.call(console, ...args)
}

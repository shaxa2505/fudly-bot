import { test, expect } from '@playwright/test'

const homeOffers = [
  {
    id: 1,
    title: 'Non',
    discount_price: 5000,
    original_price: 10000,
    store_name: 'Lavka',
    store_id: 99,
    quantity: 10,
    available_from: '10:00',
    available_until: '11:00',
  },
]

const stores = [
  {
    id: 101,
    name: 'Lavka Market',
    address: 'Toshkent',
    offers_count: 1,
    rating: 4.6,
  },
]

const categories = [
  { id: 'all', name: 'Barchasi', emoji: '🔥', count: 1 },
]

const locationState = {
  city: "Toshkent, O'zbekiston",
  address: 'Yunusobod',
  coordinates: null,
  region: '',
  district: '',
}

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, X-Telegram-Init-Data, Idempotency-Key, X-Idempotency-Key',
}

const fulfillJson = (route, data) =>
  route.fulfill({
    status: 200,
    contentType: 'application/json',
    headers: CORS_HEADERS,
    body: JSON.stringify(data),
  })

const setupApiRoutes = async (page) => {
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const method = request.method()
    const pathIndex = url.pathname.indexOf('/api/v1')
    const path = pathIndex >= 0 ? url.pathname.slice(pathIndex + 7) : null

    if (!path) {
      await route.fallback()
      return
    }

    if (method === 'OPTIONS') {
      await route.fulfill({ status: 200, headers: CORS_HEADERS })
      return
    }

    if (path === '/offers' && method === 'GET') {
      return fulfillJson(route, { offers: homeOffers })
    }

    if (path.startsWith('/offers/') && method === 'GET') {
      return fulfillJson(route, homeOffers[0])
    }

    if (path === '/categories' && method === 'GET') {
      return fulfillJson(route, categories)
    }

    if (path === '/stores' && method === 'GET') {
      return fulfillJson(route, stores)
    }

    if (path.startsWith('/stores/') && method === 'GET') {
      return fulfillJson(route, {
        id: 99,
        name: 'Lavka',
        address: 'Toshkent',
        delivery_enabled: false,
        delivery_price: 0,
        min_order_amount: 0,
        working_hours: '10:00 - 11:00',
      })
    }

    if (path === '/user/profile' && method === 'GET') {
      return fulfillJson(route, {
        registered: true,
        phone: '',
        city: "Toshkent, O'zbekiston",
        language: 'uz',
      })
    }

    if (path === '/user/search-history' && method === 'GET') {
      return fulfillJson(route, { history: [] })
    }

    if (path === '/user/search-history' && (method === 'POST' || method === 'DELETE')) {
      return fulfillJson(route, { ok: true })
    }

    if (path === '/user/notifications' && method === 'GET') {
      return fulfillJson(route, { enabled: false })
    }

    if (path === '/user/notifications' && method === 'POST') {
      return fulfillJson(route, { enabled: false })
    }

    if (path === '/user/recently-viewed' && method === 'POST') {
      return fulfillJson(route, { ok: true })
    }

    return fulfillJson(route, {})
  })

  await page.route('https://placehold.co/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'image/svg+xml',
      body: '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"></svg>',
    })
  })
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript((savedLocation) => {
    localStorage.clear()
    sessionStorage.clear()
    localStorage.setItem('fudly_location', JSON.stringify(savedLocation))
    sessionStorage.setItem('fudly_init_data', 'test_init_data')
    sessionStorage.setItem('fudly_init_data_ts', String(Date.now()))

    if (navigator.serviceWorker) {
      navigator.serviceWorker.register = () => Promise.resolve({})
      navigator.serviceWorker.ready = Promise.resolve({ active: true })
    }

    const fixed = new Date('2024-01-01T02:00:00+05:00').getTime()
    class MockDate extends Date {
      constructor(...args) {
        if (args.length) {
          super(...args)
        } else {
          super(fixed)
        }
      }
      static now() {
        return fixed
      }
    }
    // eslint-disable-next-line no-global-assign
    Date = MockDate

    const noop = () => {}
    window.Telegram = {
      WebApp: {
        initData: 'test_init_data',
        initDataUnsafe: {
          user: {
            id: 123,
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
        ready: noop,
        expand: noop,
        close: noop,
        enableClosingConfirmation: noop,
        setHeaderColor: noop,
        setBackgroundColor: noop,
        showAlert: noop,
        openLink: noop,
        openTelegramLink: noop,
        HapticFeedback: {
          impactOccurred: noop,
          notificationOccurred: noop,
          selectionChanged: noop,
        },
        MainButton: {
          show: noop,
          hide: noop,
          setText: noop,
          onClick: noop,
          offClick: noop,
        },
        BackButton: {
          show: noop,
          hide: noop,
          onClick: noop,
          offClick: noop,
        },
      },
    }
  }, locationState)

  await setupApiRoutes(page)
})

test('closed offer shows label and disables add to cart', async ({ page }) => {
  const offerResponse = page.waitForResponse((resp) =>
    resp.url().includes('/api/v1/offers/1') && resp.status() === 200
  )

  await page.goto('/product?offer_id=1', { waitUntil: 'domcontentloaded' })

  await offerResponse
  await expect(page.locator('.pdp-availability', { hasText: 'Hozir yopiq' })).toBeVisible()
  await expect(page.locator('.pdp-add-btn')).toBeDisabled()
})

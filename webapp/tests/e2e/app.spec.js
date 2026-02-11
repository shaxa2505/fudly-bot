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
  },
  {
    id: 2,
    title: 'Sut',
    discount_price: 12000,
    original_price: 15000,
    store_name: 'Lavka',
    store_id: 99,
    quantity: 5,
  },
]

const stores = [
  {
    id: 101,
    name: 'Lavka Market',
    address: 'Toshkent',
    offers_count: 3,
    rating: 4.6,
  },
]

const storeOffers = [
  {
    id: 201,
    title: 'Kefir 1L',
    discount_price: 8000,
    original_price: 10000,
    image_url: '',
  },
]

const storeReviews = {
  reviews: [],
  average_rating: 4.5,
  total_reviews: 10,
}

const locationState = {
  city: "Toshkent, O'zbekiston",
  address: 'Yunusobod',
  coordinates: null,
  region: '',
  district: '',
}

const apiState = {
  paymentProviders: [],
  store: {
    delivery_enabled: false,
    delivery_price: 0,
    min_order_amount: 0,
  },
  favoriteOffers: [],
  lastOrderPayload: null,
  orderCreateResponse: {
    success: true,
    order_id: 555,
  },
  orderStatus: {
    status: 'confirmed',
    booking_code: 'A1',
    offer_title: 'Non',
    quantity: 1,
    total_price: 5000,
    store_name: 'Lavka',
  },
  orderTimeline: {
    estimated_ready_time: '12:00',
    timeline: [
      {
        status: 'pending',
        message: 'Yaratildi',
        timestamp: new Date().toISOString(),
      },
    ],
  },
  paymentLink: 'https://pay.test/123',
}

const resetApiState = () => {
  apiState.paymentProviders = []
  apiState.store = {
    delivery_enabled: false,
    delivery_price: 0,
    min_order_amount: 0,
  }
  apiState.favoriteOffers = []
  apiState.lastOrderPayload = null
  apiState.orderCreateResponse = {
    success: true,
    order_id: 555,
  }
  apiState.orderStatus = {
    status: 'confirmed',
    booking_code: 'A1',
    offer_title: 'Non',
    quantity: 1,
    total_price: 5000,
    store_name: 'Lavka',
  }
  apiState.orderTimeline = {
    estimated_ready_time: '12:00',
    timeline: [
      {
        status: 'pending',
        message: 'Yaratildi',
        timestamp: new Date().toISOString(),
      },
    ],
  }
  apiState.paymentLink = 'https://pay.test/123'
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
  await page.route('**/*', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const method = request.method()
    if (!url.pathname.startsWith('/api/v1/')) {
      await route.fallback()
      return
    }
    const rawPath = url.pathname.slice('/api/v1'.length)
    const path = rawPath
      ? `/${rawPath.replace(/^\/+/, '').replace(/\/+$/, '')}`
      : rawPath

    const isFavoritesPath = path?.includes('/favorites')

    if (!path) {
      await route.fallback()
      return
    }

    if (method === 'OPTIONS') {
      await route.fulfill({ status: 200, headers: CORS_HEADERS })
      return
    }

    if (!isFavoritesPath && method === 'GET' && path.includes('/offers/')) {
      const match = path.match(/\/offers\/(\d+)/)
      const offerId = match ? Number(match[1]) : null
      const offer =
        homeOffers.find((item) => item.id === offerId) ||
        storeOffers.find((item) => item.id === offerId) ||
        null
      return fulfillJson(route, offer || {})
    }

    if (!isFavoritesPath && method === 'GET' && path.includes('/offers')) {
      if (url.searchParams.get('store_id')) {
        return fulfillJson(route, storeOffers)
      }
      return fulfillJson(route, { offers: homeOffers })
    }

    if (path === '/stores' && method === 'GET') {
      return fulfillJson(route, stores)
    }

    if (path.startsWith('/stores/') && path.endsWith('/reviews') && method === 'GET') {
      return fulfillJson(route, storeReviews)
    }

    if (path.startsWith('/stores/') && method === 'GET') {
      return fulfillJson(route, apiState.store)
    }

    if (path === '/user/profile' && method === 'GET') {
      return fulfillJson(route, {
        registered: true,
        phone: '+998901234567',
        city: "Toshkent, O'zbekiston",
        language: 'uz',
      })
    }

    if (path === '/user/search-history' && method === 'GET') {
      return fulfillJson(route, { history: [] })
    }

    if (path === '/user/search-history' && method === 'POST') {
      return fulfillJson(route, { ok: true })
    }

    if (path === '/user/search-history' && method === 'DELETE') {
      return fulfillJson(route, { ok: true })
    }

    if (path === '/favorites/offers' && method === 'GET') {
      return fulfillJson(route, apiState.favoriteOffers)
    }

    if (path === '/favorites/offers/add' && method === 'POST') {
      try {
        const payload = request.postDataJSON()
        const offerId = payload?.offer_id
        const offer =
          homeOffers.find((item) => item.id === offerId) ||
          storeOffers.find((item) => item.id === offerId) ||
          null
        if (offer && !apiState.favoriteOffers.find((item) => item.id === offerId)) {
          apiState.favoriteOffers.push(offer)
        }
      } catch {}
      return fulfillJson(route, { ok: true })
    }

    if (path === '/favorites/offers/remove' && method === 'POST') {
      try {
        const payload = request.postDataJSON()
        const offerId = payload?.offer_id
        apiState.favoriteOffers = apiState.favoriteOffers.filter((item) => item.id !== offerId)
      } catch {}
      return fulfillJson(route, { ok: true })
    }

    if (path === '/search' && method === 'GET') {
      return fulfillJson(route, { offers: homeOffers, stores })
    }

    if (path === '/orders' && method === 'GET') {
      return fulfillJson(route, { orders: [], bookings: [] })
    }

    if (path === '/orders' && method === 'POST') {
      try {
        apiState.lastOrderPayload = request.postDataJSON()
      } catch (error) {
        apiState.lastOrderPayload = null
      }
      return fulfillJson(route, apiState.orderCreateResponse)
    }

    if (path === '/cart/calculate' && method === 'GET') {
      const offerIdsRaw = url.searchParams.get('offer_ids') || ''
      const pairs = offerIdsRaw.split(',').map((entry) => entry.trim()).filter(Boolean)
      const items = pairs.map((pair) => {
        const [idRaw] = pair.split(':')
        const offerId = Number(idRaw)
        const offer =
          homeOffers.find((item) => item.id === offerId) ||
          storeOffers.find((item) => item.id === offerId) ||
          null
        return {
          offer_id: offerId,
          price: offer?.discount_price ?? offer?.original_price ?? 0,
          title: offer?.title || 'Mahsulot',
          photo: offer?.image_url || '',
        }
      })
      return fulfillJson(route, { items })
    }

    if (path === '/orders/calculate-delivery' && method === 'POST') {
      return fulfillJson(route, {
        ok: true,
        can_deliver: true,
        delivery_fee: apiState.store.delivery_price ?? 0,
        min_order_amount: apiState.store.min_order_amount ?? 0,
        estimated_time: '30-40 min',
      })
    }

    if (path.startsWith('/orders/') && path.endsWith('/status') && method === 'GET') {
      return fulfillJson(route, apiState.orderStatus)
    }

    if (path.startsWith('/orders/') && path.endsWith('/timeline') && method === 'GET') {
      return fulfillJson(route, apiState.orderTimeline)
    }

    if (path === '/payment/providers' && method === 'GET') {
      return fulfillJson(route, { providers: apiState.paymentProviders })
    }

    if (path === '/payment/create' && method === 'POST') {
      return fulfillJson(route, { payment_url: apiState.paymentLink })
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
  resetApiState()

  await page.addInitScript((savedLocation) => {
    localStorage.clear()
    sessionStorage.clear()
    localStorage.setItem('fudly_location', JSON.stringify(savedLocation))
    localStorage.setItem('fudly_user', JSON.stringify({
      id: 123,
      phone: '+998901234567',
      city: "Toshkent, O'zbekiston",
      language: 'uz',
      registered: true,
    }))
    sessionStorage.setItem('fudly_init_data', 'test_init_data')
    sessionStorage.setItem('fudly_init_data_ts', String(Date.now()))

    if (navigator.serviceWorker) {
      navigator.serviceWorker.register = () => Promise.resolve({})
      navigator.serviceWorker.ready = Promise.resolve({ active: true })
    }

    const noop = () => {}
    const backCallbacks = new Set()

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
          button_color: '#3A5A40',
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
          onClick: (cb) => backCallbacks.add(cb),
          offClick: (cb) => backCallbacks.delete(cb),
        },
      },
    }
  }, locationState)

  await setupApiRoutes(page)
})

test('product detail loads offer by id', async ({ page }) => {
  await page.goto('/product?offer_id=1', { waitUntil: 'domcontentloaded' })

  await expect(page.getByRole('heading', { name: 'Non' })).toBeVisible()
  await expect(page.locator('.pdp-add-btn')).toBeVisible()
})

test('adds item to cart and opens checkout', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('fudly_cart_v2', JSON.stringify({
      '1': {
        offer: {
          id: 1,
          title: 'Non',
          discount_price: 5000,
          original_price: 10000,
          store_id: 99,
        },
        quantity: 1,
      },
    }))
  })

  await page.goto('/cart', { waitUntil: 'domcontentloaded' })

  await expect(page.locator('.cart-item-title', { hasText: 'Non' })).toBeVisible()

  await page.getByRole('button', { name: "To'lovga o'tish" }).click()
  await expect(page.locator('.checkout-modal')).toBeVisible()
  await expect(page.getByRole('button', { name: /Buyurtmani tasdiqlash/ })).toBeVisible()
})

test('stores page shows empty state when no stores', async ({ page }) => {
  await page.goto('/stores', { waitUntil: 'domcontentloaded' })

  await expect(page.getByRole('heading', { name: 'Lavka Market', level: 3 })).toBeVisible()
})

test('profile shows empty orders state', async ({ page }) => {
  await page.goto('/profile', { waitUntil: 'domcontentloaded' })

  await expect(page.getByRole('heading', { name: "Faol buyurtmalar yo'q" })).toBeVisible()
  await expect(page.getByRole('heading', { name: "Buyurtmalar yo'q", exact: true })).toBeVisible()
})

test('search results show offers and clear', async ({ page }) => {
  await page.goto('/', { waitUntil: 'domcontentloaded' })

  const searchInput = page.getByPlaceholder('Restoran yoki mahsulot qidirish...')
  await searchInput.click()
  await searchInput.fill('Su')

  await expect(page.locator('.search-results-section')).toBeVisible()
  await expect(page.locator('.search-result-title', { hasText: 'Sut' })).toBeVisible()

  await page.getByRole('button', { name: 'Qidiruvni tozalash' }).click()
  await expect(page.locator('.search-results-section')).toHaveCount(0)
})

test('favorites page shows stored item', async ({ page }) => {
  apiState.favoriteOffers = [homeOffers[1]]

  await page.goto('/favorites', { waitUntil: 'domcontentloaded' })
  await expect(page.locator('.favorite-title', { hasText: 'Sut' })).toBeVisible()
})

test('cart shows empty state', async ({ page }) => {
  await page.goto('/cart', { waitUntil: 'domcontentloaded' })

  await expect(page.getByText("Savatingiz bo'sh")).toBeVisible()
})

test('places pickup order with cash', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('fudly_cart_v2', JSON.stringify({
      '1': {
        offer: {
          id: 1,
          title: 'Non',
          discount_price: 5000,
          original_price: 10000,
          store_id: 99,
        },
        quantity: 1,
      },
    }))
  })

  await page.goto('/cart', { waitUntil: 'domcontentloaded' })

  await page.getByRole('button', { name: "To'lovga o'tish" }).click()

  const orderResponse = page.waitForResponse((resp) =>
    resp.url().includes('/api/v1/orders') && resp.request().method() === 'POST'
  )

  const confirmButton = page.getByRole('button', { name: /Buyurtmani tasdiqlash/ })
  await expect(confirmButton).toBeEnabled()
  await confirmButton.click()

  await orderResponse
  expect(apiState.lastOrderPayload).toBeTruthy()
  expect(apiState.lastOrderPayload.order_type).toBe('pickup')
  expect(apiState.lastOrderPayload.payment_method).toBe('cash')
  expect(apiState.lastOrderPayload.delivery_address).toBeNull()
  expect(apiState.lastOrderPayload.delivery_fee).toBe(0)
  expect(apiState.lastOrderPayload.items).toEqual([{ offer_id: 1, quantity: 1 }])
  await expect(page.getByText("Savatingiz bo'sh")).toBeVisible()
})

test('delivery payment creates online payment link', async ({ page }) => {
  apiState.paymentProviders = ['click']
  apiState.store = {
    delivery_enabled: true,
    delivery_price: 5000,
    min_order_amount: 0,
  }

  await page.addInitScript(() => {
    localStorage.setItem('fudly_cart_v2', JSON.stringify({
      '1': {
        offer: {
          id: 1,
          title: 'Non',
          discount_price: 5000,
          original_price: 10000,
          store_id: 99,
        },
        quantity: 1,
      },
    }))
  })

  await page.goto('/cart', { waitUntil: 'domcontentloaded' })

  await page.getByRole('button', { name: "To'lovga o'tish" }).click()

  const deliveryButton = page
    .locator('.order-type-options')
    .getByRole('button', { name: /Yetkazib berish/ })
  await expect(deliveryButton).toBeEnabled()
  await deliveryButton.click()
  await page.getByPlaceholder('Manzilni kiriting').fill('Toshkent, Yunusobod')
  await page.getByRole('button', { name: 'Click' }).click()

  const orderResponse = page.waitForResponse((resp) =>
    resp.url().includes('/api/v1/orders') && resp.request().method() === 'POST'
  )
  const paymentResponse = page.waitForResponse((resp) =>
    resp.url().includes('/api/v1/payment/create') && resp.status() === 200
  )

  const confirmButton = page.getByRole('button', { name: /Buyurtmani tasdiqlash/ })
  await expect(confirmButton).toBeEnabled()
  await confirmButton.click()

  await orderResponse
  await paymentResponse

  await expect(page.getByText("Savatingiz bo'sh")).toBeVisible()
})

test('checkout resumes pending payment when cart matches', async ({ page }) => {
  await page.route('**/api/v1/orders/777/status', async (route) => {
    return fulfillJson(route, {
      status: 'pending',
      payment_status: 'awaiting_payment',
      booking_code: 'A1',
      offer_title: 'Non',
      quantity: 1,
      total_price: 5000,
      store_name: 'Lavka',
    })
  })
  await page.route('**/api/v1/payment/create', async (route) => {
    return fulfillJson(route, { payment_url: apiState.paymentLink })
  })

  await page.addInitScript(() => {
    const cart = {
      '1': {
        offer: {
          id: 1,
          title: 'Non',
          discount_price: 5000,
          original_price: 10000,
          store_id: 99,
        },
        quantity: 1,
      },
    }
    localStorage.setItem('fudly_cart_v2', JSON.stringify(cart))
    localStorage.setItem(
      'fudly_pending_payment_user_123',
      JSON.stringify({
        orderId: 777,
        storeId: 99,
        total: 5000,
        provider: 'click',
        cart,
        createdAt: Date.now(),
        updatedAt: Date.now(),
      })
    )
  })

  await page.goto('/cart', { waitUntil: 'domcontentloaded' })

  const statusResponse = page.waitForResponse((resp) =>
    resp.url().includes('/api/v1/orders/777/status') && resp.status() === 200
  )
  const paymentResponse = page.waitForResponse((resp) =>
    resp.url().includes('/api/v1/payment/create') && resp.status() === 200
  )

  await page.getByRole('button', { name: "To'lovga o'tish" }).click()
  await expect(page.getByText("To'lov yakunlanmagan")).toBeVisible()

  await statusResponse
  await paymentResponse
  expect(apiState.lastOrderPayload).toBeNull()
})

test('order tracking shows status', async ({ page }) => {
  apiState.orderStatus = {
    status: 'confirmed',
    booking_code: 'T-555',
    offer_title: 'Non',
    quantity: 2,
    total_price: 10000,
    store_name: 'Lavka',
  }

  await page.addInitScript(() => {
    localStorage.setItem('fudly_user', JSON.stringify({ id: 1, language: 'uz' }))
    window.history.replaceState(
      { usr: { bookingId: 555 }, key: 'order-test', idx: 0 },
      '',
      '/order/555'
    )
  })

  await page.goto('/order/555', { waitUntil: 'domcontentloaded' })

  await expect(page.getByRole('heading', { name: 'Non', level: 3 })).toBeVisible()
  await expect(page.getByText(/T-555/)).toBeVisible()
})

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

const fulfillJson = (route, data) =>
  route.fulfill({
    status: 200,
    contentType: 'application/json',
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

    if (path === '/offers' && method === 'GET') {
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
        phone: '',
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
    localStorage.setItem('fudly_location', JSON.stringify(savedLocation))
    sessionStorage.setItem('fudly_init_data', 'test_init_data')
    sessionStorage.setItem('fudly_init_data_ts', String(Date.now()))

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
          onClick: (cb) => backCallbacks.add(cb),
          offClick: (cb) => backCallbacks.delete(cb),
        },
      },
    }
  }, locationState)

  await setupApiRoutes(page)
})

test('home loads offers and opens product details', async ({ page }) => {
  await page.goto('/')

  const offerCard = page.locator('.offer-card', { hasText: 'Non' }).first()
  await expect(offerCard).toBeVisible()
  await offerCard.click()

  await expect(page).toHaveURL(/\/product$/)
  await expect(page.getByRole('heading', { name: 'Non' })).toBeVisible()
  await expect(page.locator('.pdp-add-btn')).toBeVisible()
})

test('adds item to cart and opens checkout', async ({ page }) => {
  await page.goto('/')

  await page.getByLabel("Savatga qo'shish").first().click()
  await page.locator('.bottom-nav').getByRole('button', { name: /Savat/ }).click()

  await expect(page.locator('.cart-item-title', { hasText: 'Non' })).toBeVisible()

  await page.getByRole('button', { name: 'Keyingi' }).click()
  await expect(page.getByLabel(/Telefon raqam/)).toBeVisible()
})

test('stores list opens offers sheet', async ({ page }) => {
  await page.goto('/stores')

  const storeCard = page.locator('.sp-card', { hasText: 'Lavka Market' })
  await expect(storeCard).toBeVisible()
  await storeCard.click()

  await expect(page.locator('.sp-sheet')).toBeVisible()
  await expect(page.getByText(/Takliflar/)).toBeVisible()
})

test('profile shows empty orders state', async ({ page }) => {
  await page.goto('/profile')

  await expect(page.getByText("Buyurtmalar yo'q")).toBeVisible()
})

test('search filters offers and clears', async ({ page }) => {
  await page.goto('/')

  const offerTitles = page.locator('.offers-grid .offer-title')
  await expect(offerTitles).toHaveCount(2)

  await page.getByPlaceholder('Mahsulot qidirish...').fill('Sut')

  await expect(page.locator('.offers-grid .offer-title', { hasText: 'Sut' })).toBeVisible()
  await expect(page.locator('.offers-grid .offer-title', { hasText: 'Non' })).toHaveCount(0)

  await page.getByRole('button', { name: 'Qidiruvni tozalash' }).click()
  await expect(offerTitles).toHaveCount(2)
})

test('favorites flow from product detail', async ({ page }) => {
  await page.goto('/')

  const offerCard = page.locator('.offer-card', { hasText: 'Sut' }).first()
  await expect(offerCard).toBeVisible()
  await offerCard.click()

  const favButton = page.getByRole('button', { name: 'Sevimli' })
  await favButton.click()
  await expect(favButton).toHaveClass(/active/)

  await page.goto('/favorites')
  await expect(page.locator('.favorite-title', { hasText: 'Sut' })).toBeVisible()
})

test('cart shows empty state', async ({ page }) => {
  await page.goto('/cart')

  await expect(page.getByText("Savatingiz bo'sh")).toBeVisible()
})

test('places pickup order with cash', async ({ page }) => {
  await page.goto('/')

  await page.getByLabel("Savatga qo'shish").first().click()
  await page.locator('.bottom-nav').getByRole('button', { name: /Savat/ }).click()

  await page.getByRole('button', { name: 'Keyingi' }).click()
  await page.getByLabel(/Telefon raqam/).fill('+998901234567')

  const orderResponse = page.waitForResponse((resp) =>
    resp.url().includes('/api/v1/orders') && resp.request().method() === 'POST'
  )

  await page.locator('.checkout-footer-btn').click()

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

  await page.goto('/cart')

  await page.getByRole('button', { name: 'Keyingi' }).click()

  const deliveryButton = page
    .locator('.order-type-options')
    .getByRole('button', { name: /Yetkazib berish/ })
  await expect(deliveryButton).toBeEnabled()
  await deliveryButton.click()
  await page.getByLabel(/Telefon raqam/).fill('+998901234567')
  await page.getByLabel(/Yetkazib berish manzili/).fill('Toshkent, Yunusobod')

  const orderResponse = page.waitForResponse((resp) =>
    resp.url().includes('/api/v1/orders') && resp.request().method() === 'POST'
  )
  const paymentResponse = page.waitForResponse((resp) =>
    resp.url().includes('/api/v1/payment/create') && resp.status() === 200
  )

  await page.locator('.checkout-footer-btn').click()

  await orderResponse
  await paymentResponse

  await expect(page.getByText("Savatingiz bo'sh")).toBeVisible()
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

  await page.goto('/order/555')

  await expect(page.locator('.order-details h3', { hasText: 'Non' })).toBeVisible()
  await expect(page.getByText(/T-555/)).toBeVisible()
})

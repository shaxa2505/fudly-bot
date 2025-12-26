import { test, expect } from '@playwright/test'

const homeOffers = [
  {
    id: 1,
    title: 'Non',
    discount_price: 5000,
    original_price: 10000,
    store_name: 'Lavka',
    quantity: 10,
  },
  {
    id: 2,
    title: 'Sut',
    discount_price: 12000,
    original_price: 15000,
    store_name: 'Lavka',
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
      return fulfillJson(route, {
        delivery_enabled: false,
        delivery_price: 0,
        min_order_amount: 0,
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

    if (path === '/user/search-history' && method === 'POST') {
      return fulfillJson(route, { ok: true })
    }

    if (path === '/user/search-history' && method === 'DELETE') {
      return fulfillJson(route, { ok: true })
    }

    if (path === '/orders' && method === 'GET') {
      return fulfillJson(route, { orders: [], bookings: [] })
    }

    if (path === '/payment/providers' && method === 'GET') {
      return fulfillJson(route, { providers: [] })
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
    localStorage.setItem('fudly_location', JSON.stringify(savedLocation))
    localStorage.setItem('fudly_init_data', 'test_init_data')

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

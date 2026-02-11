// Service Worker для кэширования и оффлайн режима
const CACHE_VERSION = 'v4'
const CACHE_NAME = `fudly-${CACHE_VERSION}`
const STATIC_CACHE = `fudly-static-${CACHE_VERSION}`
const DYNAMIC_CACHE = `fudly-dynamic-${CACHE_VERSION}`
const API_CACHE = `fudly-api-${CACHE_VERSION}`

// Статические ресурсы для предзагрузки
const STATIC_ASSETS = [
  '/',
  '/manifest.json',
  '/images/placeholder.svg',
]

// Паттерны для кэширования
const CACHE_STRATEGIES = {
  static: /\.(js|css|woff2|woff|ttf)$/,
  images: /\.(png|jpg|jpeg|gif|svg|webp|ico)$/,
  api: /\/api\//,
  telegram: /api\.telegram\.org/,
}

// Install - предзагрузка статических ресурсов
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => cache.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting())
  )
})

// Activate - очистка старых кэшей
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((cacheNames) => {
        return Promise.all(
          cacheNames
            .filter(name => name.startsWith('fudly-') && !name.includes(CACHE_VERSION))
            .map(name => caches.delete(name))
        )
      })
      .then(() => self.clients.claim())
  )
})

// Fetch - стратегии кэширования
self.addEventListener('fetch', (event) => {
  const { request } = event
  const url = new URL(request.url)

  // Пропускаем не GET запросы
  if (request.method !== 'GET') return

  // Пропускаем chrome-extension и других внешних
  if (!url.protocol.startsWith('http')) return

  // Do not cache authenticated requests (avoid leaking user data)
  const hasAuthHeaders =
    request.headers.get('X-Telegram-Init-Data') ||
    request.headers.get('Authorization') ||
    request.headers.get('Idempotency-Key') ||
    request.headers.get('X-Idempotency-Key')
  if (hasAuthHeaders) return

  // Telegram API images - кэшируем агрессивно
  if (CACHE_STRATEGIES.telegram.test(url.href)) {
    event.respondWith(cacheFirst(request, DYNAMIC_CACHE, 86400000)) // 24 hours
    return
  }

  // API запросы: Stale-While-Revalidate (быстро из кэша, обновляем в фоне)
  // API requests: do not cache (may contain user data)
  if (CACHE_STRATEGIES.api.test(url.pathname)) return

  // Навигация (HTML): Network First, чтобы не залипать на старых index.html
  if (request.mode === 'navigate') {
    event.respondWith(networkFirst(request, STATIC_CACHE))
    return
  }

  // Статические ресурсы: Cache First
  if (CACHE_STRATEGIES.static.test(url.pathname)) {
    event.respondWith(cacheFirst(request, STATIC_CACHE))
    return
  }

  // Изображения: Stale While Revalidate
  if (CACHE_STRATEGIES.images.test(url.pathname)) {
    event.respondWith(staleWhileRevalidate(request, DYNAMIC_CACHE))
    return
  }

  // По умолчанию: Network First
  event.respondWith(networkFirst(request, DYNAMIC_CACHE))
})

// Cache First - сначала кэш, потом сеть (с опциональным TTL)
async function cacheFirst(request, cacheName, maxAge = null) {
  const cached = await caches.match(request)
  if (cached) {
    // Check cache freshness if maxAge specified
    if (maxAge) {
      const cachedDate = cached.headers.get('sw-cached-at')
      if (cachedDate && Date.now() - parseInt(cachedDate) > maxAge) {
        // Cache expired, fetch new
        return fetchAndCache(request, cacheName)
      }
    }
    return cached
  }
  return fetchAndCache(request, cacheName)
}

async function fetchAndCache(request, cacheName) {
  try {
    const response = await fetch(request)
    if (response.ok) {
      const cache = await caches.open(cacheName)
      // Clone and add timestamp header
      const clonedResponse = response.clone()
      const headers = new Headers(clonedResponse.headers)
      headers.set('sw-cached-at', Date.now().toString())
      const cachedResponse = new Response(await clonedResponse.blob(), {
        status: clonedResponse.status,
        statusText: clonedResponse.statusText,
        headers
      })
      cache.put(request, cachedResponse)
    }
    return response
  } catch {
    return offlineFallback()
  }
}

// Network First - сначала сеть, потом кэш
async function networkFirst(request, cacheName) {
  try {
    const response = await fetch(request)
    if (response.ok) {
      const cache = await caches.open(cacheName)
      cache.put(request, response.clone())
    }
    return response
  } catch {
    const cached = await caches.match(request)
    if (cached) return cached
    return offlineFallback()
  }
}

// Stale While Revalidate - кэш сразу, обновление в фоне
async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName)
  const cached = await cache.match(request)

  const fetchPromise = fetch(request)
    .then(response => {
      if (response.ok) {
        cache.put(request, response.clone())
      }
      return response
    })
    .catch(() => null)

  return cached || await fetchPromise || offlineFallback()
}

// Оффлайн fallback
async function offlineFallback() {
  const offlinePage = await caches.match('/offline.html')
  if (offlinePage) return offlinePage

  return new Response(
    `<!DOCTYPE html>
    <html lang="uz">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Офлайн - Fudly</title>
      <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
          background: #f5f5f5;
          min-height: 100vh;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 20px;
        }
        .container {
          text-align: center;
          max-width: 320px;
        }
        .icon { font-size: 64px; margin-bottom: 20px; }
        h1 { font-size: 24px; color: #181725; margin-bottom: 12px; }
        p { color: #7C7C7C; margin-bottom: 24px; line-height: 1.5; }
        button {
          background: #3A5A40;
          color: white;
          border: none;
          padding: 16px 32px;
          border-radius: 16px;
          font-size: 16px;
          font-weight: 600;
          cursor: pointer;
        }
        button:active { transform: scale(0.95); }
      </style>
    </head>
    <body>
      <div class="container">
        <div class="icon">📴</div>
        <h1>Internet yo'q</h1>
        <p>Internet aloqasini tekshiring va qaytadan urinib ko'ring</p>
        <button onclick="location.reload()">Qayta yuklash</button>
      </div>
    </body>
    </html>`,
    { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
  )
}

// Background Sync для отложенных действий
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-cart') {
    event.waitUntil(syncCart())
  }
})

async function syncCart() {
  // Синхронизация корзины когда появится интернет
  console.log('[SW] Синхронизация корзины')
}

// Push уведомления (для будущего)
self.addEventListener('push', (event) => {
  if (!event.data) return

  const data = event.data.json()
  const options = {
    body: data.body,
    icon: '/icon-192.png',
    badge: '/icon-192.png',
    vibrate: [100, 50, 100],
    data: data.url,
    actions: [
      { action: 'open', title: "Ko'rish" },
      { action: 'close', title: 'Yopish' }
    ]
  }

  event.waitUntil(
    self.registration.showNotification(data.title, options)
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()

  if (event.action === 'open' || !event.action) {
    event.waitUntil(
      clients.openWindow(event.notification.data || '/')
    )
  }
})

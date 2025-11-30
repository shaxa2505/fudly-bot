// Service Worker для кэширования и оффлайн режима
const CACHE_NAME = 'fudly-v2'
const STATIC_CACHE = 'fudly-static-v2'
const DYNAMIC_CACHE = 'fudly-dynamic-v2'
const API_CACHE = 'fudly-api-v2'

// Статические ресурсы для предзагрузки
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/manifest.json',
  '/offline.html'
]

// Паттерны для кэширования
const CACHE_STRATEGIES = {
  static: /\.(js|css|png|jpg|jpeg|gif|svg|woff2|woff|ttf|ico)$/,
  api: /\/api\//,
  images: /\.(png|jpg|jpeg|gif|svg|webp)$/
}

// Install - предзагрузка статических ресурсов
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => {
        console.log('[SW] Кэширование статических ресурсов')
        return cache.addAll(STATIC_ASSETS)
      })
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
            .filter(name => name.startsWith('fudly-') &&
                          !name.includes('-v2'))
            .map(name => {
              console.log('[SW] Удаление старого кэша:', name)
              return caches.delete(name)
            })
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

  // Стратегия для API запросов: Network First
  if (CACHE_STRATEGIES.api.test(url.pathname)) {
    event.respondWith(networkFirst(request, API_CACHE))
    return
  }

  // Стратегия для статических ресурсов: Cache First
  if (CACHE_STRATEGIES.static.test(url.pathname)) {
    event.respondWith(cacheFirst(request, STATIC_CACHE))
    return
  }

  // Стратегия для изображений: Stale While Revalidate
  if (CACHE_STRATEGIES.images.test(url.pathname)) {
    event.respondWith(staleWhileRevalidate(request, DYNAMIC_CACHE))
    return
  }

  // По умолчанию: Network First с фолбэком на кэш
  event.respondWith(networkFirst(request, DYNAMIC_CACHE))
})

// Cache First - сначала кэш, потом сеть
async function cacheFirst(request, cacheName) {
  const cached = await caches.match(request)
  if (cached) return cached

  try {
    const response = await fetch(request)
    if (response.ok) {
      const cache = await caches.open(cacheName)
      cache.put(request, response.clone())
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
          background: #53B175;
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

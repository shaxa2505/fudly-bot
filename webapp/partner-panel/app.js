// Telegram WebApp
const tg = window.Telegram?.WebApp || {
    ready: () => {},
    expand: () => {},
    initData: '',
    initDataUnsafe: { user: { id: 0 } },
    HapticFeedback: { impactOccurred: () => {}, notificationOccurred: () => {} },
    showAlert: (msg) => alert(msg)
};
tg.expand();
tg.ready();

// Применяем тему Telegram
if (tg.colorScheme === 'dark') {
    document.documentElement.style.setProperty('--bg', '#1a1a1a');
    document.documentElement.style.setProperty('--surface', '#2a2a2a');
    document.documentElement.style.setProperty('--text', '#ffffff');
    document.documentElement.style.setProperty('--text-secondary', '#a0a0a0');
    document.documentElement.style.setProperty('--border', '#3a3a3a');
}

// API URL - определяется автоматически
const API_URL = (() => {
    const hostname = window.location.hostname;

    // Локальная разработка
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
        return 'http://localhost:8000/api/partner';
    }

    // Vercel - использует Railway API
    if (hostname.includes('vercel.app')) {
        return 'https://fudly-bot-production.up.railway.app/api/partner';
    }

    // По умолчанию - относительный путь
    return '/api/partner';
})();

// Auth
const isDevMode = !tg.initData && window.location.hostname === 'localhost';
let devTelegramId = null;

if (isDevMode) {
    devTelegramId = prompt('Введите ваш Telegram ID:', '253445521');
}

function getAuthHeader() {
    if (isDevMode) {
        return `dev_${devTelegramId}`;
    }
    return `tma ${tg.initData}`;
}

// State
let currentView = 'dashboard';
let productsData = [];
let ordersData = [];
let statsData = {};

// Кэш для оптимизации
const cache = {
    profile: null,
    products: { data: null, timestamp: 0 },
    orders: { data: null, timestamp: 0 },
    stats: { data: null, timestamp: 0 }
};
const CACHE_TTL = 30000; // 30 секунд

// Проверка кэша
function isCacheValid(key) {
    return cache[key]?.timestamp && (Date.now() - cache[key].timestamp) < CACHE_TTL;
}

// API Request с кэшированием
async function apiRequest(endpoint, options = {}) {
    // Проверяем кэш для GET запросов
    if (!options.method || options.method === 'GET') {
        const cacheKey = endpoint.split('?')[0].replace('/', '');
        if (isCacheValid(cacheKey)) {
            console.log('📦 Cache hit:', cacheKey);
            return cache[cacheKey].data;
        }
    }

    try {
        const response = await fetch(`${API_URL}${endpoint}`, {
            ...options,
            headers: {
                'Authorization': getAuthHeader(),
                'Content-Type': 'application/json',
                ...options.headers
            }
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`HTTP ${response.status}: ${errorText}`);
        }

        const data = await response.json();

        // Сохраняем в кэш GET запросы
        if (!options.method || options.method === 'GET') {
            const cacheKey = endpoint.split('?')[0].replace('/', '');
            cache[cacheKey] = { data, timestamp: Date.now() };
        }

        return data;
    } catch (error) {
        console.error('API Error:', error);
        showToast('❌ ' + (error.message || 'Ошибка подключения'));
        throw error;
    }
}

// Show Toast с вибрацией
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;
    document.body.appendChild(toast);

    // Тактильная обратная связь
    if (type === 'success') {
        tg.HapticFeedback?.notificationOccurred('success');
    } else if (type === 'error') {
        tg.HapticFeedback?.notificationOccurred('error');
    } else {
        tg.HapticFeedback?.impactOccurred('light');
    }

    setTimeout(() => toast.remove(), 3000);
}

// Format Money
function formatMoney(amount) {
    return new Intl.NumberFormat('ru-RU').format(amount) + ' сум';
}

// Switch View с анимацией
function switchView(view) {
    if (currentView === view) return;

    tg.HapticFeedback?.impactOccurred('light');
    currentView = view;

    // Update sections
    document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
    document.getElementById(view).classList.add('active');

    // Update nav
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    event.target.closest('.nav-item').classList.add('active');

    // Показываем/скрываем FAB
    const fab = document.querySelector('.fab');
    if (view === 'products') {
        fab.style.display = 'flex';
    } else {
        fab.style.display = 'none';
    }

    // Load data
    loadView(view);
}

// Load View
async function loadView(view) {
    switch(view) {
        case 'dashboard':
            await loadDashboard();
            break;
        case 'products':
            await loadProducts();
            break;
        case 'orders':
            await loadOrders();
            break;
        case 'stats':
            await loadStats();
            break;
    }
}

// Load Dashboard с оптимизацией
async function loadDashboard() {
    try {
        const [profile, products, orders, stats] = await Promise.all([
            apiRequest('/profile'),
            apiRequest('/products'),
            apiRequest('/orders'),
            apiRequest('/stats?period=today')
        ]);

        // Сохраняем профиль
        cache.profile = profile;

        // Update store name с анимацией
        const storeNameEl = document.getElementById('storeName');
        storeNameEl.style.opacity = '0';
        setTimeout(() => {
            storeNameEl.textContent = profile.store_name || 'Магазин';
            storeNameEl.style.opacity = '1';
        }, 150);

        // Update stats с анимацией чисел
        animateNumber('todayRevenue', stats.revenue || 0, formatMoney);
        animateNumber('todayOrders', stats.orders || 0);
        animateNumber('totalProducts', products.length);

        const pending = orders.filter(o => o.status === 'pending').length;
        animateNumber('pendingOrders', pending);

        // Проверяем новые заказы
        checkNewOrders(orders);
    } catch (error) {
        console.error('Dashboard error:', error);
        showToast('Ошибка загрузки данных', 'error');
    }
}

// Анимация чисел
function animateNumber(elementId, targetValue, formatter) {
    const el = document.getElementById(elementId);
    const currentText = el.textContent;
    const currentValue = parseInt(currentText.replace(/[^0-9]/g, '')) || 0;

    if (currentValue === targetValue) return;

    const duration = 500;
    const steps = 20;
    const increment = (targetValue - currentValue) / steps;
    let current = currentValue;
    let step = 0;

    const timer = setInterval(() => {
        step++;
        current += increment;

        if (step >= steps) {
            clearInterval(timer);
            current = targetValue;
        }

        el.textContent = formatter ? formatter(Math.round(current)) : Math.round(current);
    }, duration / steps);
}

// Проверка новых заказов
let lastOrderCount = 0;
function checkNewOrders(orders) {
    const pendingOrders = orders.filter(o => o.status === 'pending');

    if (lastOrderCount > 0 && pendingOrders.length > lastOrderCount) {
        tg.HapticFeedback?.notificationOccurred('success');
        showToast('🔔 Новый заказ!', 'success');
    }

    lastOrderCount = pendingOrders.length;
}

// Load Products с поиском
let productSearchQuery = '';
async function loadProducts(forceRefresh = false) {
    const container = document.getElementById('productsContent');

    if (!forceRefresh && productsData.length > 0) {
        renderProducts();
        return;
    }

    container.innerHTML = '<div class="loading"><div class="spinner"></div></div>';

    try {
        if (forceRefresh) {
            cache.products = { data: null, timestamp: 0 };
        }
        productsData = await apiRequest('/products');
        renderProducts();
    } catch (error) {
        container.innerHTML = '<div class="empty-state"><div class="empty-text">Ошибка загрузки</div></div>';
    }
}

// Рендер товаров с фильтрацией
function renderProducts() {
    const container = document.getElementById('productsContent');

    // Фильтруем товары по поисковому запросу
    let filtered = productsData;
    if (productSearchQuery) {
        const query = productSearchQuery.toLowerCase();
        filtered = productsData.filter(p =>
            p.title.toLowerCase().includes(query) ||
            (p.description && p.description.toLowerCase().includes(query))
        );
    }

    if (filtered.length === 0) {
        container.innerHTML = `
            <div class="search-box">
                <input type="search" class="form-input" placeholder="🔍 Поиск товаров..."
                       value="${escapeHtml(productSearchQuery)}"
                       oninput="searchProducts(this.value)">
            </div>
            <div class="empty-state">
                <div class="empty-icon">📦</div>
                <div class="empty-text">${productSearchQuery ? 'Ничего не найдено' : 'Нет товаров'}</div>
                ${!productSearchQuery ? '<button class="btn btn-primary" onclick="openAddProductModal()">Добавить товар</button>' : ''}
            </div>
        `;
        return;
    }

    container.innerHTML = `
        <div class="search-box">
            <input type="search" class="form-input" placeholder="🔍 Поиск товаров..."
                   value="${escapeHtml(productSearchQuery)}"
                   oninput="searchProducts(this.value)">
        </div>
    ` + filtered.map(product => `
        <div class="card" data-id="${product.offer_id}">
            <div class="card-header">
                <div>
                    <div class="card-title">${escapeHtml(product.title)}</div>
                    <div class="card-info">${formatMoney(product.discount_price || product.original_price)}</div>
                </div>
                <span class="badge ${product.quantity > 0 ? 'success' : 'danger'}">
                    ${product.quantity} шт
                </span>
            </div>
            ${product.description ? `<div class="card-info">${escapeHtml(product.description)}</div>` : ''}
            <div class="btn-group">
                <button class="btn btn-primary btn-sm" onclick="quickEditQuantity(${product.offer_id}, ${product.quantity})">📝 Остаток</button>
                <button class="btn btn-danger btn-sm" onclick="deleteProduct(${product.offer_id})">🗑️</button>
            </div>
        </div>
    `).join('');
}

// Поиск товаров
function searchProducts(query) {
    productSearchQuery = query;
    renderProducts();
}

// Быстрое редактирование количества
function quickEditQuantity(productId, currentQty) {
    tg.HapticFeedback?.impactOccurred('medium');
    const newQty = prompt('Введите новое количество:', currentQty);
    if (newQty === null) return;

    const qty = parseInt(newQty);
    if (isNaN(qty) || qty < 0) {
        showToast('❌ Неверное количество', 'error');
        return;
    }

    updateProductQuantity(productId, qty);
}

// Обновление количества товара
async function updateProductQuantity(productId, quantity) {
    try {
        await apiRequest(`/products/${productId}`, {
            method: 'PUT',
            body: JSON.stringify({ quantity })
        });

        // Обновляем локальные данные
        const product = productsData.find(p => p.offer_id === productId);
        if (product) {
            product.quantity = quantity;
        }

        // Инвалидируем кэш
        cache.products = { data: null, timestamp: 0 };

        showToast('✅ Обновлено', 'success');
        renderProducts();
        loadDashboard();
    } catch (error) {
        showToast('❌ Ошибка обновления', 'error');
    }
}

// Load Orders
async function loadOrders() {
    const container = document.getElementById('ordersContent');
    container.innerHTML = '<div class="loading"><div class="spinner"></div></div>';

    try {
        ordersData = await apiRequest('/orders');

        if (ordersData.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">🎫</div>
                    <div class="empty-text">Нет заказов</div>
                </div>
            `;
            return;
        }

        const statusMap = {
            pending: { text: 'Новый', badge: 'warning' },
            confirmed: { text: 'Подтверждён', badge: 'success' },
            ready: { text: 'Готов', badge: 'success' },
            completed: { text: 'Завершён', badge: 'success' },
            cancelled: { text: 'Отменён', badge: 'danger' }
        };

        container.innerHTML = ordersData.map(order => {
            const status = statusMap[order.status] || { text: order.status, badge: 'warning' };
            return `
                <div class="card">
                    <div class="card-header">
                        <div>
                            <div class="card-title">Заказ #${order.order_id}</div>
                            <div class="card-info">${new Date(order.created_at).toLocaleString('ru-RU')}</div>
                        </div>
                        <span class="badge ${status.badge}">${status.text}</span>
                    </div>
                    <div class="card-info">
                        <strong>${escapeHtml(order.offer_title || 'Товар')}</strong> × ${order.quantity}<br>
                        💰 ${formatMoney(order.price)}<br>
                        👤 ${escapeHtml(order.customer_name || 'Клиент')}<br>
                        📞 ${escapeHtml(order.customer_phone || '-')}
                    </div>
                    ${order.status === 'pending' ? `
                        <div class="btn-group">
                            <button class="btn btn-success btn-sm" onclick="confirmOrder(${order.order_id})">✅ Подтвердить</button>
                            <button class="btn btn-danger btn-sm" onclick="cancelOrder(${order.order_id})">❌ Отменить</button>
                        </div>
                    ` : ''}
                </div>
            `;
        }).join('');
    } catch (error) {
        container.innerHTML = '<div class="empty-state"><div class="empty-text">Ошибка загрузки</div></div>';
    }
}

// Load Stats
async function loadStats() {
    const container = document.getElementById('statsContent');
    container.innerHTML = '<div class="loading"><div class="spinner"></div></div>';

    try {
        const [today, week, month] = await Promise.all([
            apiRequest('/stats?period=today'),
            apiRequest('/stats?period=week'),
            apiRequest('/stats?period=month')
        ]);

        container.innerHTML = `
            <div class="card">
                <div class="card-title">📅 Сегодня</div>
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-value">${formatMoney(today.revenue || 0)}</div>
                        <div class="stat-label">Выручка</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${today.orders || 0}</div>
                        <div class="stat-label">Заказов</div>
                    </div>
                </div>
            </div>

            <div class="card">
                <div class="card-title">📅 Неделя</div>
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-value">${formatMoney(week.revenue || 0)}</div>
                        <div class="stat-label">Выручка</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${week.orders || 0}</div>
                        <div class="stat-label">Заказов</div>
                    </div>
                </div>
            </div>

            <div class="card">
                <div class="card-title">📅 Месяц</div>
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-value">${formatMoney(month.revenue || 0)}</div>
                        <div class="stat-label">Выручка</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">${month.orders || 0}</div>
                        <div class="stat-label">Заказов</div>
                    </div>
                </div>
            </div>
        `;
    } catch (error) {
        container.innerHTML = '<div class="empty-state"><div class="empty-text">Ошибка загрузки</div></div>';
    }
}

// Modal functions
function openAddProductModal() {
    document.getElementById('addProductModal').classList.add('show');
    document.getElementById('productForm').reset();
}

function closeAddProductModal() {
    document.getElementById('addProductModal').classList.remove('show');
}

// Add Product
async function addProduct(event) {
    event.preventDefault();

    const product = {
        title: document.getElementById('productTitle').value,
        discount_price: parseInt(document.getElementById('productPrice').value),
        quantity: parseInt(document.getElementById('productQuantity').value),
        description: document.getElementById('productDescription').value,
        category: 'other',
        unit: 'шт'
    };

    try {
        await apiRequest('/products', {
            method: 'POST',
            body: JSON.stringify(product)
        });

        showToast('✅ Товар добавлен');
        closeAddProductModal();
        loadProducts();
        loadDashboard();
    } catch (error) {
        showToast('❌ Ошибка добавления');
    }
}

// Delete Product
async function deleteProduct(id) {
    if (!confirm('Удалить товар?')) return;

    try {
        await apiRequest(`/products/${id}`, { method: 'DELETE' });
        showToast('✅ Товар удалён');
        loadProducts();
        loadDashboard();
    } catch (error) {
        showToast('❌ Ошибка удаления');
    }
}

// Confirm Order
async function confirmOrder(id) {
    try {
        await apiRequest(`/orders/${id}/confirm`, { method: 'POST' });
        showToast('✅ Заказ подтверждён');
        loadOrders();
        loadDashboard();
    } catch (error) {
        showToast('❌ Ошибка');
    }
}

// Cancel Order
async function cancelOrder(id) {
    if (!confirm('Отменить заказ?')) return;

    try {
        await apiRequest(`/orders/${id}/cancel`, { method: 'POST' });
        showToast('✅ Заказ отменён');
        loadOrders();
        loadDashboard();
    } catch (error) {
        showToast('❌ Ошибка');
    }
}

// Escape HTML
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Pull-to-refresh
let startY = 0;
let pulling = false;

document.addEventListener('touchstart', (e) => {
    if (window.scrollY === 0) {
        startY = e.touches[0].pageY;
        pulling = true;
    }
}, { passive: true });

document.addEventListener('touchmove', (e) => {
    if (!pulling) return;
    const currentY = e.touches[0].pageY;
    const diff = currentY - startY;

    if (diff > 80) {
        pulling = false;
        refreshData();
    }
}, { passive: true });

document.addEventListener('touchend', () => {
    pulling = false;
});

// Обновление данных
async function refreshData() {
    tg.HapticFeedback?.impactOccurred('medium');
    showToast('🔄 Обновление...');

    // Очищаем кэш
    cache.products = { data: null, timestamp: 0 };
    cache.orders = { data: null, timestamp: 0 };
    cache.stats = { data: null, timestamp: 0 };

    await loadView(currentView);
    showToast('✅ Обновлено', 'success');
}

// Автообновление каждые 30 секунд
setInterval(() => {
    if (currentView === 'dashboard' || currentView === 'orders') {
        loadView(currentView);
    }
}, 30000);

// Слушатель видимости вкладки
document.addEventListener('visibilitychange', () => {
    if (!document.hidden) {
        // Обновляем при возврате на вкладку
        loadView(currentView);
    }
});

// Init
console.log('🚀 Partner Panel v2.0 loaded');
console.log('📱 Telegram WebApp:', !!window.Telegram?.WebApp?.initData);
console.log('🎨 Theme:', tg.colorScheme);
console.log('🔗 API URL:', API_URL);
console.log('🔑 Auth:', isDevMode ? 'Development' : 'Production');
console.log('🌐 Origin:', window.location.origin);

// Тестируем соединение
fetch(`${API_URL}/profile`, {
    headers: {
        'Authorization': getAuthHeader()
    }
})
.then(response => {
    console.log('✅ API Test:', response.status, response.statusText);
    if (!response.ok) {
        return response.text().then(text => {
            console.error('❌ API Error:', text);
        });
    }
})
.catch(error => {
    console.error('❌ Connection Error:', error);
});

loadDashboard();

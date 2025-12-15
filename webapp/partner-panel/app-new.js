// Telegram WebApp
const tg = window.Telegram?.WebApp || {
    ready: () => {},
    expand: () => {},
    initData: '',
    initDataUnsafe: { user: { id: 0 } }
};
tg.expand();
tg.ready();

// API URL
const API_URL = window.location.hostname === 'localhost'
    ? 'http://localhost:8000/api/partner'
    : 'https://fudly-bot-main-production.up.railway.app/api/partner';

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

// API Request
async function apiRequest(endpoint, options = {}) {
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
            throw new Error(`HTTP ${response.status}`);
        }

        return await response.json();
    } catch (error) {
        console.error('API Error:', error);
        showToast('❌ Ошибка подключения');
        throw error;
    }
}

// Show Toast
function showToast(message) {
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

// Format Money
function formatMoney(amount) {
    return new Intl.NumberFormat('ru-RU').format(amount) + ' сум';
}

// Switch View
function switchView(view) {
    currentView = view;

    // Update sections
    document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
    document.getElementById(view).classList.add('active');

    // Update nav
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    event.target.closest('.nav-item').classList.add('active');

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

// Load Dashboard
async function loadDashboard() {
    try {
        const [profile, products, orders, stats] = await Promise.all([
            apiRequest('/profile'),
            apiRequest('/products'),
            apiRequest('/orders'),
            apiRequest('/stats?period=today')
        ]);

        // Update store name
        document.getElementById('storeName').textContent = profile.store_name || 'Магазин';

        // Update stats
        document.getElementById('todayRevenue').textContent = formatMoney(stats.revenue || 0);
        document.getElementById('todayOrders').textContent = stats.orders || 0;
        document.getElementById('totalProducts').textContent = products.length;

        const pending = orders.filter(o => o.status === 'pending').length;
        document.getElementById('pendingOrders').textContent = pending;
    } catch (error) {
        console.error('Dashboard error:', error);
    }
}

// Load Products
async function loadProducts() {
    const container = document.getElementById('productsContent');
    container.innerHTML = '<div class="loading"><div class="spinner"></div></div>';

    try {
        productsData = await apiRequest('/products');

        if (productsData.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">📦</div>
                    <div class="empty-text">Нет товаров</div>
                    <button class="btn btn-primary" onclick="openAddProductModal()">Добавить товар</button>
                </div>
            `;
            return;
        }

        container.innerHTML = productsData.map(product => `
            <div class="card">
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
                    <button class="btn btn-primary btn-sm" onclick="editProduct(${product.offer_id})">✏️ Изменить</button>
                    <button class="btn btn-danger btn-sm" onclick="deleteProduct(${product.offer_id})">🗑️ Удалить</button>
                </div>
            </div>
        `).join('');
    } catch (error) {
        container.innerHTML = '<div class="empty-state"><div class="empty-text">Ошибка загрузки</div></div>';
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

// Init
loadDashboard();

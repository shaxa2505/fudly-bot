// Telegram WebApp Init
const tg = window.Telegram?.WebApp || {
    ready: () => {},
    expand: () => {},
    initData: '',
    initDataUnsafe: { user: { id: 0 } },
    themeParams: {},
    colorScheme: 'light'
};

tg.ready();
tg.expand();

// Apply Telegram theme
function applyTheme() {
    const isDark = tg.colorScheme === 'dark';
    if (isDark) {
        document.body.classList.add('dark-theme');
    }

    // Apply theme colors if available
    const root = document.documentElement;
    if (tg.themeParams.bg_color) root.style.setProperty('--tg-theme-bg-color', tg.themeParams.bg_color);
    if (tg.themeParams.text_color) root.style.setProperty('--tg-theme-text-color', tg.themeParams.text_color);
    if (tg.themeParams.hint_color) root.style.setProperty('--tg-theme-hint-color', tg.themeParams.hint_color);
    if (tg.themeParams.link_color) root.style.setProperty('--tg-theme-link-color', tg.themeParams.link_color);
    if (tg.themeParams.button_color) root.style.setProperty('--tg-theme-button-color', tg.themeParams.button_color);
    if (tg.themeParams.secondary_bg_color) root.style.setProperty('--tg-theme-secondary-bg-color', tg.themeParams.secondary_bg_color);
}

applyTheme();

// API Configuration
const API_URL = `${window.location.origin}/api`;

// Auth Header
function getAuthHeader() {
    const isDev = !tg.initData;
    if (isDev) {
        const devId = localStorage.getItem('dev_telegram_id') || '123456789';
        return `dev_${devId}`;
    }
    return `tma ${tg.initData}`;
}

// Toast notification
function showToast(message) {
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 2000);
}

// View switching
let currentView = 'dashboard';

function switchView(viewName) {
    // Hide all views
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));

    // Show selected view
    const viewId = viewName + 'View';
    document.getElementById(viewId)?.classList.add('active');

    // Update tabs
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    event.currentTarget?.classList.add('active');

    currentView = viewName;

    // Load data
    if (viewName === 'dashboard') loadDashboard();
    else if (viewName === 'products') loadProducts();
    else if (viewName === 'orders') loadAllOrders();
    else if (viewName === 'stats') loadStats();

    // Haptic feedback
    if (tg.HapticFeedback) {
        tg.HapticFeedback.impactOccurred('light');
    }
}

// Load Dashboard
async function loadDashboard() {
    try {
        // Load profile
        const [profileRes, statsRes, ordersRes] = await Promise.all([
            fetch(`${API_URL}/partner/profile`, { headers: { 'Authorization': getAuthHeader() } }),
            fetch(`${API_URL}/partner/stats?period=today`, { headers: { 'Authorization': getAuthHeader() } }),
            fetch(`${API_URL}/partner/orders`, { headers: { 'Authorization': getAuthHeader() } })
        ]);

        if (profileRes.ok) {
            const profile = await profileRes.json();
            document.getElementById('storeName').textContent = profile.name || 'Мой магазин';
        }

        if (statsRes.ok) {
            const stats = await statsRes.json();
            const today = stats.today || {};
            document.getElementById('todayRevenue').textContent = formatMoney(today.revenue || 0);
            document.getElementById('todayOrders').textContent = today.orders || 0;
        }

        if (ordersRes.ok) {
            const data = await ordersRes.json();
            renderOrders(data.orders || [], 'recentOrders', 3);
        }

    } catch (error) {
        console.error('Failed to load dashboard:', error);
        showToast('❌ Ошибка загрузки');
    }
}

// Load Products
async function loadProducts() {
    try {
        const res = await fetch(`${API_URL}/partner/products`, {
            headers: { 'Authorization': getAuthHeader() }
        });

        if (res.ok) {
            const data = await res.json();
            renderProducts(data.products || []);
        }
    } catch (error) {
        console.error('Failed to load products:', error);
        showToast('❌ Ошибка загрузки товаров');
    }
}

// Load All Orders
async function loadAllOrders() {
    try {
        const res = await fetch(`${API_URL}/partner/orders`, {
            headers: { 'Authorization': getAuthHeader() }
        });

        if (res.ok) {
            const data = await res.json();
            renderOrders(data.orders || [], 'allOrdersList');
        }
    } catch (error) {
        console.error('Failed to load orders:', error);
    }
}

// Load Stats
async function loadStats() {
    try {
        const res = await fetch(`${API_URL}/partner/stats?period=month`, {
            headers: { 'Authorization': getAuthHeader() }
        });

        if (res.ok) {
            const stats = await res.json();
            document.getElementById('weekRevenue').textContent = formatMoney(stats.week?.revenue || 0);
            document.getElementById('monthRevenue').textContent = formatMoney(stats.month?.revenue || 0);
            document.getElementById('avgCheck').textContent = formatMoney(stats.month?.avg_check || 0);
        }
    } catch (error) {
        console.error('Failed to load stats:', error);
    }
}

// Render functions
function renderProducts(products) {
    const container = document.getElementById('productsList');
    if (!products.length) {
        container.innerHTML = '';
        return;
    }

    container.innerHTML = products.map(p => `
        <div class="product-card">
            <img src="${p.image || ''}" alt="${p.name}" class="product-image" onerror="this.src='data:image/svg+xml,%3Csvg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'64\\' height=\\'64\\'%3E%3Crect fill=\\'%23e5e5e5\\' width=\\'64\\' height=\\'64\\'/%3E%3C/svg%3E'">
            <div class="product-info">
                <h3 class="product-name">${p.name}</h3>
                <div class="product-meta">
                    <span>Остаток: ${p.stock || 0}</span>
                </div>
            </div>
            <div class="product-price">${formatMoney(p.price)}</div>
        </div>
    `).join('');
}

function renderOrders(orders, containerId, limit = null) {
    const container = document.getElementById(containerId);
    const displayOrders = limit ? orders.slice(0, limit) : orders;

    if (!displayOrders.length) {
        container.innerHTML = '<div class="empty-state"><div class="empty-icon">🎫</div><div class="empty-title">Нет заказов</div><div class="empty-text">Заказы появятся здесь</div></div>';
        return;
    }

    container.innerHTML = displayOrders.map(o => `
        <div class="order-card">
            <div class="order-header">
                <div class="order-id">#${o.id}</div>
                <div class="order-status ${o.status}">${getStatusText(o.status)}</div>
            </div>
            <div class="order-items">${o.items_count || 1} товар${o.items_count > 1 ? 'а' : ''}</div>
            <div class="order-footer">
                <div class="order-time">${formatTime(o.created_at)}</div>
                <div class="order-total">${formatMoney(o.total)}</div>
            </div>
        </div>
    `).join('');
}

// Helpers
function formatMoney(amount) {
    return new Intl.NumberFormat('ru-RU', {
        style: 'currency',
        currency: 'KZT',
        minimumFractionDigits: 0
    }).format(amount || 0);
}

function formatTime(timestamp) {
    if (!timestamp) return 'Сейчас';
    const date = new Date(timestamp);
    const now = new Date();
    const diff = (now - date) / 1000 / 60; // minutes

    if (diff < 1) return 'Только что';
    if (diff < 60) return `${Math.floor(diff)} мин назад`;
    if (diff < 1440) return `${Math.floor(diff / 60)} ч назад`;
    return date.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
}

function getStatusText(status) {
    const texts = {
        new: 'Новый',
        confirmed: 'Подтвержден',
        delivering: 'Доставляется',
        completed: 'Выполнен',
        cancelled: 'Отменен'
    };
    return texts[status] || status;
}

// Initial load
loadDashboard();

// Auto-refresh every 30 seconds
setInterval(() => {
    if (currentView === 'dashboard') loadDashboard();
    else if (currentView === 'orders') loadAllOrders();
}, 30000);

console.log('✅ Partner Panel loaded');
console.log('🔌 API:', API_URL);

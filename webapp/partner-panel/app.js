// ============================================
// Partner Panel - Simple & Clean Version
// ============================================

// Telegram WebApp SDK
const tg = window.Telegram?.WebApp;
if (tg) {
    tg.ready();
    tg.expand();
}

// API Configuration
const API_URL = 'https://fudly-bot-production.up.railway.app/api/partner';

// Get authorization header from Telegram initData
function getAuthHeader() {
    if (tg?.initData) {
        return `tma ${tg.initData}`;
    }
    // Fallback for testing - will fail auth on server but won't crash
    return 'tma ';
}

console.log('🚀 Partner Panel loaded', {
    telegram: !!tg,
    initData: tg?.initData ? `${tg.initData.length} chars` : 'none',
    platform: tg?.platform || 'unknown'
});

// ============================================
// State
// ============================================
let currentView = 'dashboard';
let productsData = [];
let ordersData = [];

// ============================================
// API Functions
// ============================================
async function apiRequest(endpoint, options = {}) {
    const url = `${API_URL}${endpoint}`;
    console.log(`📡 API: ${options.method || 'GET'} ${endpoint}`);
    
    try {
        const response = await fetch(url, {
            ...options,
            headers: {
                'Authorization': getAuthHeader(),
                'Content-Type': 'application/json',
                ...options.headers
            }
        });

        console.log(`📡 Response: ${response.status}`);

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
            console.error('API Error:', errorData);
            
            if (response.status === 401) {
                showError('Ошибка авторизации', 'Откройте панель через меню бота');
                throw new Error('Unauthorized');
            }
            
            if (response.status === 403) {
                showError('Доступ запрещён', errorData.detail || 'Вы не являетесь партнёром');
                throw new Error('Forbidden');
            }
            
            throw new Error(errorData.detail || `HTTP ${response.status}`);
        }

        return await response.json();
    } catch (error) {
        if (error.message === 'Unauthorized' || error.message === 'Forbidden') {
            throw error;
        }
        console.error('Network error:', error);
        showToast('❌ Ошибка сети');
        throw error;
    }
}

// ============================================
// UI Helpers
// ============================================
function showToast(message) {
    // Remove existing toasts
    document.querySelectorAll('.toast').forEach(t => t.remove());
    
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;
    toast.style.cssText = 'position:fixed;bottom:80px;left:50%;transform:translateX(-50%);background:#333;color:white;padding:12px 24px;border-radius:8px;z-index:9999;animation:fadeIn 0.3s';
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

function showError(title, message) {
    document.body.innerHTML = `
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;text-align:center;padding:20px;background:var(--bg, #f8fafc);color:var(--text, #1e293b);font-family:system-ui">
            <div style="font-size:64px;margin-bottom:20px">⚠️</div>
            <h1 style="margin:0 0 10px;font-size:24px">${title}</h1>
            <p style="color:var(--text-secondary, #64748b);margin:0 0 20px">${message}</p>
            <button onclick="location.reload()" style="background:var(--primary, #6366f1);color:white;padding:12px 24px;border-radius:8px;border:none;cursor:pointer">Попробовать снова</button>
        </div>
    `;
}

function formatMoney(amount) {
    return new Intl.NumberFormat('ru-RU').format(amount || 0) + ' сум';
}

function formatDate(dateStr) {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

// ============================================
// Dashboard
// ============================================
async function loadDashboard() {
    try {
        // Load all data in parallel
        const [profile, products, orders, stats] = await Promise.all([
            apiRequest('/profile'),
            apiRequest('/products'),
            apiRequest('/orders'),
            apiRequest('/stats?period=today')
        ]);

        console.log('✅ Dashboard data loaded', { profile, products: products?.length, orders: orders?.length });

        // Update stats cards
        document.getElementById('todayRevenue').textContent = formatMoney(stats?.revenue || 0);
        document.getElementById('todayOrders').textContent = stats?.orders_count || 0;
        document.getElementById('totalProducts').textContent = products?.length || 0;
        document.getElementById('pendingOrders').textContent = orders?.filter(o => o.status === 'pending')?.length || 0;

        // Store data
        productsData = products || [];
        ordersData = orders || [];

        // Hide loading
        document.querySelector('.loading')?.remove();
        
    } catch (error) {
        console.error('Dashboard error:', error);
    }
}

// ============================================
// Products
// ============================================
async function loadProducts() {
    try {
        const products = await apiRequest('/products');
        productsData = products || [];
        renderProducts();
    } catch (error) {
        console.error('Products error:', error);
    }
}

function renderProducts() {
    const container = document.getElementById('productsList');
    if (!container) return;

    if (productsData.length === 0) {
        container.innerHTML = '<div class="empty-state">Нет товаров. Нажмите + чтобы добавить.</div>';
        return;
    }

    container.innerHTML = productsData.map(p => `
        <div class="product-card" onclick="editProduct(${p.offer_id})">
            <div class="product-image">${p.photo_id ? `<img src="https://fudly-bot-production.up.railway.app/api/partner/photo/${p.photo_id}" alt="">` : '📦'}</div>
            <div class="product-info">
                <div class="product-title">${escapeHtml(p.title || 'Без названия')}</div>
                <div class="product-price">${formatMoney(p.discount_price)}</div>
                <div class="product-stock ${p.quantity <= 0 ? 'out-of-stock' : ''}">${p.quantity} шт</div>
            </div>
            <div class="product-status ${p.status === 'active' ? 'active' : 'inactive'}">${p.status === 'active' ? '●' : '○'}</div>
        </div>
    `).join('');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ============================================
// Orders
// ============================================
async function loadOrders() {
    try {
        const orders = await apiRequest('/orders');
        ordersData = orders || [];
        renderOrders();
    } catch (error) {
        console.error('Orders error:', error);
    }
}

function renderOrders() {
    const container = document.getElementById('ordersList');
    if (!container) return;

    if (ordersData.length === 0) {
        container.innerHTML = '<div class="empty-state">Нет заказов</div>';
        return;
    }

    const statusLabels = {
        pending: '⏳ Ожидает',
        confirmed: '✅ Подтверждён',
        completed: '🎉 Завершён',
        cancelled: '❌ Отменён'
    };

    container.innerHTML = ordersData.map(o => `
        <div class="order-card" onclick="viewOrder(${o.booking_id || o.order_id})">
            <div class="order-header">
                <span class="order-code">#${o.booking_code || o.order_id}</span>
                <span class="order-status status-${o.status}">${statusLabels[o.status] || o.status}</span>
            </div>
            <div class="order-info">
                <div class="order-customer">${escapeHtml(o.customer_name || 'Клиент')}</div>
                <div class="order-total">${formatMoney(o.total_amount)}</div>
            </div>
            <div class="order-date">${formatDate(o.created_at)}</div>
        </div>
    `).join('');
}

// ============================================
// Stats
// ============================================
async function loadStats() {
    try {
        const [today, week, month] = await Promise.all([
            apiRequest('/stats?period=today'),
            apiRequest('/stats?period=week'),
            apiRequest('/stats?period=month')
        ]);

        document.getElementById('statsContent').innerHTML = `
            <div class="stats-period">
                <h3>Сегодня</h3>
                <div class="stats-row"><span>Выручка:</span><span>${formatMoney(today?.revenue)}</span></div>
                <div class="stats-row"><span>Заказов:</span><span>${today?.orders_count || 0}</span></div>
            </div>
            <div class="stats-period">
                <h3>Неделя</h3>
                <div class="stats-row"><span>Выручка:</span><span>${formatMoney(week?.revenue)}</span></div>
                <div class="stats-row"><span>Заказов:</span><span>${week?.orders_count || 0}</span></div>
            </div>
            <div class="stats-period">
                <h3>Месяц</h3>
                <div class="stats-row"><span>Выручка:</span><span>${formatMoney(month?.revenue)}</span></div>
                <div class="stats-row"><span>Заказов:</span><span>${month?.orders_count || 0}</span></div>
            </div>
        `;
    } catch (error) {
        console.error('Stats error:', error);
    }
}

// ============================================
// Navigation
// ============================================
function switchView(view) {
    currentView = view;

    // Update sections
    document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
    const section = document.getElementById(view);
    if (section) section.classList.add('active');

    // Update nav
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    event?.target?.closest('.nav-item')?.classList.add('active');

    // Load data
    switch(view) {
        case 'dashboard': loadDashboard(); break;
        case 'products': loadProducts(); break;
        case 'orders': loadOrders(); break;
        case 'stats': loadStats(); break;
    }
}

// ============================================
// Product Form (Add/Edit)
// ============================================
function showAddProduct() {
    document.getElementById('productModal').style.display = 'flex';
    document.getElementById('productForm').reset();
    document.getElementById('productId').value = '';
}

function closeModal() {
    document.getElementById('productModal').style.display = 'none';
}

async function editProduct(id) {
    const product = productsData.find(p => p.offer_id === id);
    if (!product) return;

    document.getElementById('productId').value = id;
    document.getElementById('productTitle').value = product.title || '';
    document.getElementById('productCategory').value = product.category || '';
    document.getElementById('productPrice').value = product.discount_price || '';
    document.getElementById('productQuantity').value = product.quantity || 0;
    document.getElementById('productDescription').value = product.description || '';
    
    document.getElementById('productModal').style.display = 'flex';
}

async function saveProduct(event) {
    event.preventDefault();
    
    const id = document.getElementById('productId').value;
    const formData = new FormData();
    formData.append('title', document.getElementById('productTitle').value);
    formData.append('category', document.getElementById('productCategory').value);
    formData.append('discount_price', document.getElementById('productPrice').value);
    formData.append('quantity', document.getElementById('productQuantity').value);
    formData.append('description', document.getElementById('productDescription').value);

    try {
        const url = id ? `/products/${id}` : '/products';
        const method = id ? 'PUT' : 'POST';
        
        await fetch(`${API_URL}${url}`, {
            method,
            headers: { 'Authorization': getAuthHeader() },
            body: formData
        });

        showToast(id ? '✅ Товар обновлён' : '✅ Товар добавлен');
        closeModal();
        loadProducts();
    } catch (error) {
        showToast('❌ Ошибка сохранения');
    }
}

// ============================================
// Initialize
// ============================================
document.addEventListener('DOMContentLoaded', () => {
    console.log('📱 DOM ready, loading dashboard...');
    loadDashboard();
    
    // Setup form handler
    const form = document.getElementById('productForm');
    if (form) {
        form.addEventListener('submit', saveProduct);
    }
});

/* ================================================
   ORDERS MODULE
   Order management and dashboard
   ================================================ */

import { ordersAPI, statsAPI, storeAPI } from './api.js';
import { formatPrice, timeAgo, toast } from './utils.js';
import { state, actions } from './state.js';

// Load dashboard (orders + stats)
export async function loadDashboard() {
    console.log('⚡ Loading dashboard...');

    try {
        actions.setOrdersLoading(true);

        // Load store info
        const storeInfo = await storeAPI.getInfo();
        actions.setStoreInfo(storeInfo);
        document.getElementById('storeName').textContent = storeInfo.name || 'Мой магазин';

        // Load orders
        const orders = await ordersAPI.getAll();
        actions.setOrders(orders);

        // Load stats
        const stats = await statsAPI.getDashboard('today');
        actions.setStats(stats);

        // Render
        renderDashboard();

        console.log('✅ Dashboard loaded');
    } catch (error) {
        console.error('❌ Dashboard load error:', error);
        actions.setOrdersError(error.message);
        toast('Ошибка загрузки данных', 'error');
    }
}

// Load orders
export async function loadOrders() {
    try {
        actions.setOrdersLoading(true);
        const orders = await ordersAPI.getAll();
        actions.setOrders(orders);
        renderOrders();
    } catch (error) {
        console.error('❌ Orders load error:', error);
        toast('Ошибка загрузки заказов', 'error');
    }
}

// Render dashboard
function renderDashboard() {
    renderStats();
    renderOrders();
}

// Render stats cards
function renderStats() {
    const stats = state.stats;
    if (!stats) return;

    // Update stat cards
    updateStat('todayOrders', stats.today_orders || 0);
    updateStat('todayRevenue', formatPrice(stats.today_revenue || 0));
    updateStat('activeOrders', stats.active_orders || 0);
    updateStat('pendingOrders', stats.pending_orders || 0);
}

function updateStat(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

// Render orders list
function renderOrders() {
    const ordersListEl = document.getElementById('ordersList');
    if (!ordersListEl) return;

    const orders = state.filteredOrders;

    if (state.ordersLoading) {
        ordersListEl.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
        return;
    }

    if (!orders || orders.length === 0) {
        ordersListEl.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">📦</div>
                <div class="empty-title">Нет заказов</div>
                <div class="empty-text">Заказы появятся здесь</div>
            </div>
        `;
        return;
    }

    ordersListEl.innerHTML = orders.map(order => renderOrderCard(order)).join('');
}

// Render single order card
function renderOrderCard(order) {
    const statusNames = {
        pending: 'Новый',
        confirmed: 'Подтвержден',
        preparing: 'Готовится',
        ready: 'Готов',
        delivering: 'В пути',
        completed: 'Завершен',
        cancelled: 'Отменен'
    };

    const statusName = statusNames[order.status] || order.status;
    const typeText = order.order_type === 'delivery' ? 'Доставка' : 'Самовывоз';
    const typeIcon = order.order_type === 'delivery' ? '🚚' : '🏃';

    return `
        <div class="order-card ${order.status}" data-order-id="${order.id}">
            <div class="order-header">
                <div class="order-id">#${order.id}</div>
                <div class="order-status-badge ${order.status}">
                    ${getStatusEmoji(order.status)} ${statusName}
                </div>
            </div>

            <div class="order-content">
                <div class="order-info">
                    <div class="order-title">${order.product_name || 'Товар'}</div>
                    <div class="order-meta">
                        <div class="order-meta-row">
                            <span>${typeIcon} ${typeText}</span>
                            <span>• ${order.quantity} шт</span>
                        </div>
                        <div class="order-meta-row">
                            <span>⏰ ${timeAgo(order.created_at)}</span>
                        </div>
                    </div>
                </div>
                <div class="order-price">${formatPrice(order.total_price || 0)}</div>
            </div>

            ${order.customer_name || order.delivery_address ? `
            <div class="order-details">
                ${order.customer_name ? `
                <div class="detail-row">
                    <span class="detail-icon">👤</span>
                    <span class="detail-label">Клиент</span>
                    <span class="detail-value">${order.customer_name}</span>
                </div>
                ` : ''}
                ${order.customer_phone ? `
                <div class="detail-row">
                    <span class="detail-icon">📞</span>
                    <span class="detail-label">Телефон</span>
                    <span class="detail-value">${order.customer_phone}</span>
                </div>
                ` : ''}
                ${order.delivery_address ? `
                <div class="detail-row">
                    <span class="detail-icon">📍</span>
                    <span class="detail-label">Адрес</span>
                    <span class="detail-value">${order.delivery_address}</span>
                </div>
                ` : ''}
            </div>
            ` : ''}

            <div class="order-actions">
                ${getOrderActions(order)}
            </div>
        </div>
    `;
}

function getStatusEmoji(status) {
    const emojis = {
        pending: '⏳',
        confirmed: '✅',
        preparing: '👨‍🍳',
        ready: '✅',
        delivering: '🚚',
        completed: '🎉',
        cancelled: '❌'
    };
    return emojis[status] || '📦';
}

function getOrderActions(order) {
    const id = order.id;

    if (order.status === 'pending') {
        return `
            <button class="btn btn-success" onclick="window.confirmOrder(${id})">
                ✅ Подтвердить
            </button>
            <button class="btn btn-danger" onclick="window.cancelOrder(${id})">
                ❌ Отказать
            </button>
        `;
    } else if (order.status === 'confirmed') {
        return `
            <button class="btn btn-primary" onclick="window.updateOrderStatus(${id}, 'preparing')">
                👨‍🍳 Готовится
            </button>
            <button class="btn btn-outline" onclick="window.cancelOrder(${id})">
                ❌ Отменить
            </button>
        `;
    } else if (order.status === 'preparing') {
        return `
            <button class="btn btn-success" onclick="window.updateOrderStatus(${id}, 'ready')">
                ✅ Готово
            </button>
        `;
    } else if (order.status === 'ready') {
        return order.order_type === 'delivery' ? `
            <button class="btn btn-primary" onclick="window.updateOrderStatus(${id}, 'delivering')">
                🚚 В пути
            </button>
            <button class="btn btn-success" onclick="window.completeOrder(${id})">
                ✅ Завершить
            </button>
        ` : `
            <button class="btn btn-success" onclick="window.completeOrder(${id})">
                🎉 Выдано
            </button>
        `;
    } else if (order.status === 'delivering') {
        return `
            <button class="btn btn-success" onclick="window.completeOrder(${id})">
                🎉 Доставлено
            </button>
        `;
    }

    return '';
}

// Confirm order
export async function confirmOrder(orderId) {
    try {
        await ordersAPI.confirm(orderId);
        actions.updateOrder(orderId, { status: 'confirmed' });
        renderOrders();
        toast('Заказ подтвержден', 'success');
    } catch (error) {
        console.error('Error confirming order:', error);
        toast('Ошибка подтверждения', 'error');
    }
}

// Update order status
export async function updateOrderStatus(orderId, status) {
    try {
        await ordersAPI.updateStatus(orderId, status);
        actions.updateOrder(orderId, { status });
        renderOrders();

        const statusText = {
            preparing: 'Заказ готовится',
            ready: 'Заказ готов',
            delivering: 'Заказ в пути'
        }[status] || 'Статус обновлен';

        toast(statusText, 'success');
    } catch (error) {
        console.error('Error updating status:', error);
        toast('Ошибка обновления', 'error');
    }
}

// Complete order
export async function completeOrder(orderId) {
    try {
        await ordersAPI.updateStatus(orderId, 'completed');
        actions.updateOrder(orderId, { status: 'completed' });
        renderOrders();
        toast('Заказ завершен! 🎉', 'success');
    } catch (error) {
        console.error('Error completing order:', error);
        toast('Ошибка завершения', 'error');
    }
}

// Cancel order
export async function cancelOrder(orderId) {
    if (!confirm('Отменить заказ?')) return;

    try {
        await ordersAPI.cancel(orderId);
        actions.updateOrder(orderId, { status: 'cancelled' });
        renderOrders();
        toast('Заказ отменен', 'warning');
    } catch (error) {
        console.error('Error cancelling order:', error);
        toast('Ошибка отмены', 'error');
    }
}

// Make functions global for onclick handlers
window.confirmOrder = confirmOrder;
window.updateOrderStatus = updateOrderStatus;
window.completeOrder = completeOrder;
window.cancelOrder = cancelOrder;

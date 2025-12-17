/* ================================================
   STATS MODULE
   Statistics and analytics
   ================================================ */

import { statsAPI } from './api.js';
import { formatPrice, toast } from './utils.js';
import { state, actions } from './state.js';

// Load statistics
export async function loadStatistics(period = 'today') {
    try {
        actions.setStatsLoading(true);
        actions.setStatsPeriod(period);

        const stats = await statsAPI.getDashboard(period);
        actions.setStats(stats);

        renderStatistics();

        console.log('✅ Statistics loaded');
    } catch (error) {
        console.error('❌ Stats load error:', error);
        toast('Ошибка загрузки статистики', 'error');
    }
}

// Render statistics
function renderStatistics() {
    renderStatsPeriodTabs();
    renderCharts();
}

// Render period tabs
function renderStatsPeriodTabs() {
    const tabs = document.querySelectorAll('.period-tab');
    tabs.forEach(tab => {
        tab.classList.toggle('active', tab.dataset.period === state.statsPeriod);
    });
}

// Render charts
function renderCharts() {
    const stats = state.stats;
    if (!stats) return;

    // Revenue chart
    renderRevenueChart(stats.revenue_data || []);

    // Orders chart
    renderOrdersChart(stats.orders_data || []);

    // Top products
    renderTopProducts(stats.top_products || []);
}

// Revenue chart
function renderRevenueChart(data) {
    const canvas = document.getElementById('revenueChart');
    if (!canvas) return;

    // Destroy existing chart
    if (state.charts.revenue) {
        state.charts.revenue.destroy();
    }

    const ctx = canvas.getContext('2d');

    state.charts.revenue = new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.map(d => d.label),
            datasets: [{
                label: 'Выручка',
                data: data.map(d => d.value / 100), // Convert kopeks to sums
                borderColor: '#6366f1',
                backgroundColor: 'rgba(99, 102, 241, 0.1)',
                borderWidth: 2,
                fill: true,
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        label: (context) => formatPrice(context.raw * 100)
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: (value) => (value / 1000).toFixed(0) + 'K'
                    }
                }
            }
        }
    });
}

// Orders chart
function renderOrdersChart(data) {
    const canvas = document.getElementById('ordersChart');
    if (!canvas) return;

    // Destroy existing chart
    if (state.charts.orders) {
        state.charts.orders.destroy();
    }

    const ctx = canvas.getContext('2d');

    state.charts.orders = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.map(d => d.label),
            datasets: [{
                label: 'Заказы',
                data: data.map(d => d.value),
                backgroundColor: '#10b981',
                borderRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        stepSize: 1
                    }
                }
            }
        }
    });
}

// Top products
function renderTopProducts(products) {
    const container = document.getElementById('topProductsList');
    if (!container) return;

    if (!products || products.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">📊</div>
                <div class="empty-text">Нет данных о продажах</div>
            </div>
        `;
        return;
    }

    container.innerHTML = products.map((product, index) => `
        <div class="top-product-item">
            <div class="top-product-rank">${index + 1}</div>
            <div class="top-product-info">
                <div class="top-product-name">${product.name}</div>
                <div class="top-product-sales">${product.sales} продаж</div>
            </div>
            <div class="top-product-revenue">${formatPrice(product.revenue)}</div>
        </div>
    `).join('');
}

// Change period
export function changePeriod(period) {
    loadStatistics(period);
}

// Make functions global
window.changePeriod = changePeriod;

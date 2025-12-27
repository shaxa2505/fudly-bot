/* ================================================
   FUDLY PARTNER PANEL - UX IMPROVEMENTS LOGIC
   Phase 1: Quick Wins Implementation
   ================================================ */

// === ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ===
let viewMode = localStorage.getItem('viewMode') || 'grid'; // 'grid' | 'compact'
let selectedProducts = new Set();
let productAnalytics = {}; // Кэш аналитики
let uxBootstrapped = false;
window.allProducts = window.allProducts || [];

function getAllProducts() {
    return Array.isArray(window.allProducts) ? window.allProducts : [];
}

function getApiBaseSafe() {
    if (typeof API_BASE !== 'undefined' && API_BASE) return API_BASE;
    return (
        window.PARTNER_API_BASE ||
        document.querySelector('meta[name="api-base"]')?.getAttribute('content') ||
        window.location.origin
    );
}

function buildAuthHeaderSafe() {
    if (typeof getAuth !== 'function') return '';
    const auth = getAuth();
    if (auth?.data) {
        return `tma ${auth.data}`;
    }
    if (auth?.urlUserId && auth?.urlAuthDate && auth?.urlSig) {
        return `tma uid=${auth.urlUserId}&auth_date=${auth.urlAuthDate}&sig=${auth.urlSig}`;
    }
    return '';
}

// === 1. ИНИЦИАЛИЗАЦИЯ ===
function initUXImprovements() {
    initViewModeToggle();
    initSmartBadges();
    initQuickFilters();
    initBulkActions();
    calculateProductMetrics();

    if (!uxBootstrapped) {
        initInlinePriceEdit();
        initKeyboardShortcuts();
        uxBootstrapped = true;
    }
}

// === 2. ПЕРЕКЛЮЧЕНИЕ РЕЖИМОВ ОТОБРАЖЕНИЯ ===
function initViewModeToggle() {
    // Добавляем переключатель в заголовок
    const header = document.querySelector('.products-header .section-title');
    if (!header) {
        console.log('⏳ Products header not found yet, will retry later');
        return;
    }

    // Проверяем, не добавлен ли уже переключатель
    if (header.querySelector('.view-mode-toggle')) {
        console.log('✅ View mode toggle already exists');
        return;
    }

    const toggle = document.createElement('div');
    toggle.className = 'view-mode-toggle';
    toggle.innerHTML = `
        <button class="view-mode-btn ${viewMode === 'grid' ? 'active' : ''}" data-mode="grid" title="Карточки">
            <i data-lucide="grid" style="width: 16px; height: 16px;"></i>
            <span>Карточки</span>
        </button>
        <button class="view-mode-btn ${viewMode === 'compact' ? 'active' : ''}" data-mode="compact" title="Список">
            <i data-lucide="list" style="width: 16px; height: 16px;"></i>
            <span>Список</span>
        </button>
    `;

    header.appendChild(toggle);
    console.log('✅ View mode toggle added');

    // Инициализируем иконки Lucide
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }

    // Обработчик переключения
    toggle.querySelectorAll('.view-mode-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const mode = btn.dataset.mode;
            switchViewMode(mode);
        });
    });

    // Применяем сохраненный режим
    applyViewMode(viewMode);
}

function switchViewMode(mode) {
    viewMode = mode;
    localStorage.setItem('viewMode', mode);

    // Обновляем активную кнопку
    document.querySelectorAll('.view-mode-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.mode === mode);
    });

    applyViewMode(mode);
}

function applyViewMode(mode) {
    const grid = document.getElementById('productsList');
    if (!grid) return;

    if (mode === 'compact') {
        grid.classList.add('compact');
        grid.querySelectorAll('.product-card').forEach(card => {
            card.classList.add('compact');
        });
    } else {
        grid.classList.remove('compact');
        grid.querySelectorAll('.product-card').forEach(card => {
            card.classList.remove('compact');
        });
    }
}

// === 3. УМНЫЕ БЕЙДЖИ (ХИТ, МАЛО, НОВЫЙ) ===
function initSmartBadges() {
    // Вызывается при рендеринге товаров
    // Добавим в функцию renderProducts
}

function getSmartBadge(product, analytics) {
    const badges = [];

    // ХИТ ПРОДАЖ (топ 10% по продажам)
    if (analytics && analytics.salesRank <= 10) {
        badges.push({ type: 'hot', icon: '🔥', text: 'Хит' });
    }

    // ТРЕНД (рост продаж > 20%)
    if (analytics && analytics.trend > 20) {
        badges.push({ type: 'trending', icon: '📈', text: `+${analytics.trend}%` });
    }

    // НОВЫЙ (добавлен < 7 дней назад)
    const daysSinceAdded = getDaysSince(product.created_at);
    if (daysSinceAdded <= 7) {
        badges.push({ type: 'new', icon: '✨', text: 'Новый' });
    }

    // МАЛО (остаток < 10 или < 3 дней продаж)
    const lowStockThreshold = analytics ? Math.max(10, analytics.avgDailySales * 3) : 10;
    if (product.stock > 0 && product.stock < lowStockThreshold) {
        badges.push({ type: 'low', icon: '⚠️', text: 'Мало!' });
    }

    return badges[0]; // Возвращаем самый важный бейдж
}

function renderSmartBadge(badge) {
    if (!badge) return '';
    return `
        <div class="smart-badge badge-${badge.type}">
            <span>${badge.icon}</span>
            <span>${badge.text}</span>
        </div>
    `;
}

// === 4. INLINE РЕДАКТИРОВАНИЕ ЦЕНЫ ===
function initInlinePriceEdit() {
    // Делегирование событий
    document.addEventListener('click', (e) => {
        const priceEl = e.target.closest('.product-price.editable');
        if (priceEl && !priceEl.classList.contains('editing')) {
            startPriceEdit(priceEl);
        }
    });
}

function makePriceEditable(productId) {
    const card = document.querySelector(`[data-product-id="${productId}"]`);
    if (!card) return;

    const priceEl = card.querySelector('.product-price');
    if (priceEl) {
        priceEl.classList.add('editable');
        priceEl.title = 'Нажмите для редактирования';
    }
}

function startPriceEdit(priceEl) {
    const card = priceEl.closest('.product-card');
    const productId = card.dataset.productId;
    const product = getAllProducts().find(p => p.id == productId);
    if (!product) return;

    priceEl.classList.add('editing');
    const currentPrice = product.price;

    priceEl.innerHTML = `
        <input
            type="number"
            class="price-edit-input"
            value="${currentPrice}"
            min="0"
            step="100"
            autofocus
        />
        <div class="price-edit-actions">
            <button class="price-edit-btn save">✓ Сохранить</button>
            <button class="price-edit-btn cancel">✗ Отмена</button>
        </div>
    `;

    const input = priceEl.querySelector('.price-edit-input');
    const saveBtn = priceEl.querySelector('.save');
    const cancelBtn = priceEl.querySelector('.cancel');

    input.select();
    input.focus();

    // Enter - сохранить, Escape - отмена
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') saveBtn.click();
        if (e.key === 'Escape') cancelBtn.click();
    });

    saveBtn.addEventListener('click', () => {
        const newPrice = parseInt(input.value);
        if (newPrice && newPrice !== currentPrice) {
            updateProductPrice(productId, newPrice);
        }
        endPriceEdit(priceEl, newPrice || currentPrice);
    });

    cancelBtn.addEventListener('click', () => {
        endPriceEdit(priceEl, currentPrice);
    });
}

function endPriceEdit(priceEl, price) {
    priceEl.classList.remove('editing');
    priceEl.innerHTML = formatPrice(price);
}

async function updateProductPrice(productId, newPrice) {
    try {
        const formData = new FormData();
        formData.append('price', newPrice.toString());
        const endpoint = `/api/partner/products/${productId}`;
        if (typeof apiFetch === 'function') {
            await apiFetch(endpoint, { method: 'PATCH', body: formData });
        } else {
            const authHeader = buildAuthHeaderSafe();
            const headers = authHeader ? { Authorization: authHeader } : {};
            const response = await fetch(`${getApiBaseSafe()}${endpoint}`, {
                method: 'PATCH',
                headers,
                body: formData
            });

            if (!response.ok) {
                throw new Error('?????? ?????????? ????');
            }
        }
// Обновляем локальные данные
        const product = getAllProducts().find(p => p.id == productId);
        if (product) {
            product.price = newPrice;
        }

        toast('✓ Цена обновлена', 'success');
    } catch (error) {
        console.error('Error updating price:', error);
        toast(error.message, 'error');
    }
}

// === 5. KEYBOARD SHORTCUTS ===
function initKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        // Игнорируем, если фокус в input/textarea
        if (e.target.matches('input, textarea')) return;

        // N - добавить товар
        if (e.key === 'n' || e.key === 'N') {
            e.preventDefault();
            document.querySelector('.add-product-btn')?.click();
        }

        // / - фокус на поиск
        if (e.key === '/') {
            e.preventDefault();
            document.querySelector('.search-input')?.focus();
        }

        // 1-5 - быстрые фильтры
        if (e.key >= '1' && e.key <= '5') {
            const filters = document.querySelectorAll('.filter-chip');
            filters[e.key - 1]?.click();
        }

        // ? - показать подсказки
        if (e.key === '?') {
            showKeyboardHints();
        }
    });
}

function showKeyboardHints() {
    const hint = document.createElement('div');
    hint.className = 'keyboard-hint visible';
    hint.innerHTML = `
        <div><kbd>N</kbd> Добавить товар</div>
        <div><kbd>/</kbd> Поиск</div>
        <div><kbd>1-5</kbd> Фильтры</div>
        <div><kbd>?</kbd> Подсказки</div>
    `;
    document.body.appendChild(hint);

    setTimeout(() => {
        hint.classList.remove('visible');
        setTimeout(() => hint.remove(), 300);
    }, 3000);
}

// === 6. УЛУЧШЕННЫЕ ФИЛЬТРЫ С МЕТРИКАМИ ===
function initQuickFilters() {
    const filtersEl = document.querySelector('.products-filters');
    if (!filtersEl) return;

    // Обновляем структуру фильтров
    updateFilterCounts();

    // Обработчики уже есть, просто улучшаем визуал
}

function updateFilterCounts() {
    const products = getAllProducts();
    if (!products.length) return;

    const counts = {
        all: products.length,
        active: products.filter(p => p.is_active).length,
        inactive: products.filter(p => !p.is_active).length,
        low_stock: products.filter(p => p.stock_quantity > 0 && p.stock_quantity < 10).length,
        out_of_stock: products.filter(p => p.stock_quantity === 0).length
    };

    // Обновляем счетчики по ID (для существующих элементов)
    Object.entries(counts).forEach(([key, count]) => {
        const el = document.getElementById(`count-${key}`);
        if (el) el.textContent = count;
    });

    // Также обновляем через data-filter (для динамических чипов)
    document.querySelectorAll('.filter-chip').forEach(chip => {
        const filter = chip.dataset.filter;
        const count = counts[filter] || 0;

        let countEl = chip.querySelector('.count');
        if (!countEl) {
            countEl = document.createElement('span');
            countEl.className = 'count';
            chip.appendChild(countEl);
        }
        countEl.textContent = count;
    });
}

// === 7. BULK ACTIONS (МАССОВЫЕ ОПЕРАЦИИ) ===
function initBulkActions() {
    // Добавляем чекбоксы на карточки
    // Показываем панель действий при выборе
}

function toggleProductSelection(productId) {
    if (selectedProducts.has(productId)) {
        selectedProducts.delete(productId);
    } else {
        selectedProducts.add(productId);
    }

    updateSelectionUI();
    toggleQuickActionsBar();
}

function toggleQuickActionsBar() {
    let bar = document.querySelector('.quick-actions-bar');

    if (selectedProducts.size > 0) {
        if (!bar) {
            bar = createQuickActionsBar();
            document.body.appendChild(bar);
        }

        bar.querySelector('.selected-count').textContent = selectedProducts.size;
        bar.classList.add('visible');
    } else {
        bar?.classList.remove('visible');
    }
}

function createQuickActionsBar() {
    const bar = document.createElement('div');
    bar.className = 'quick-actions-bar';
    bar.innerHTML = `
        <div class="selected-info">
            <span>Выбрано: <strong class="selected-count">0</strong></span>
        </div>
        <div class="bulk-actions">
            <button class="bulk-action-btn secondary" onclick="bulkHideProducts()">
                <i data-lucide="eye-off" style="width: 16px; height: 16px;"></i>
                Скрыть
            </button>
            <button class="bulk-action-btn secondary" onclick="bulkShowProducts()">
                <i data-lucide="eye" style="width: 16px; height: 16px;"></i>
                Показать
            </button>
            <button class="bulk-action-btn primary" onclick="bulkEditPrice()">
                <i data-lucide="dollar-sign" style="width: 16px; height: 16px;"></i>
                Изменить цену
            </button>
            <button class="bulk-action-btn danger" onclick="bulkDeleteProducts()">
                <i data-lucide="trash-2" style="width: 16px; height: 16px;"></i>
                Удалить
            </button>
        </div>
    `;

    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }

    return bar;
}

async function bulkHideProducts() {
    // Реализация массового скрытия
    console.log('Hiding products:', Array.from(selectedProducts));
    // TODO: API call
}

async function bulkShowProducts() {
    // Реализация массового показа
    console.log('Showing products:', Array.from(selectedProducts));
    // TODO: API call
}

async function bulkEditPrice() {
    const newPrice = prompt('Введите новую цену для выбранных товаров:');
    if (!newPrice) return;

    console.log('Updating price for products:', Array.from(selectedProducts), 'to:', newPrice);
    // TODO: API call
}

async function bulkDeleteProducts() {
    if (!confirm(`Удалить ${selectedProducts.size} товаров?`)) return;

    console.log('Deleting products:', Array.from(selectedProducts));
    // TODO: API call
}

// === 8. МЕТРИКИ И АНАЛИТИКА ===
function calculateProductMetrics() {
    // Рассчитываем метрики для каждого товара
    // В реальном проекте данные приходят с бэкенда
    getAllProducts().forEach(product => {
        productAnalytics[product.id] = {
            salesRank: Math.floor(Math.random() * 100), // 1-100
            trend: Math.floor(Math.random() * 50) - 10, // -10 до +40
            avgDailySales: Math.floor(Math.random() * 5) + 1, // 1-5
            revenue: product.price * Math.floor(Math.random() * 20),
            rating: (Math.random() * 2 + 3).toFixed(1), // 3.0-5.0
            reviews: Math.floor(Math.random() * 50)
        };
    });
}

function showProductAnalytics(productId) {
    const product = getAllProducts().find(p => p.id == productId);
    const analytics = productAnalytics[productId];
    if (!product || !analytics) return;

    // Создаем модальное окно с аналитикой
    const modal = document.createElement('div');
    modal.className = 'analytics-modal visible';
    modal.innerHTML = `
        <div class="analytics-content">
            <div class="analytics-header">
                <div class="analytics-title">📊 Аналитика: ${product.name}</div>
                <button class="analytics-close" onclick="this.closest('.analytics-modal').remove()">✕</button>
            </div>

            <div class="analytics-stat">
                <div class="analytics-stat-label">Продажи за 30 дней</div>
                <div class="analytics-stat-value">${formatPrice(analytics.revenue)}</div>
            </div>

            <div class="analytics-stat">
                <div class="analytics-stat-label">Тренд продаж</div>
                <div class="analytics-stat-value" style="color: ${analytics.trend > 0 ? '#10b981' : '#ef4444'}">
                    ${analytics.trend > 0 ? '+' : ''}${analytics.trend}% ${analytics.trend > 0 ? '↗' : '↘'}
                </div>
            </div>

            <div class="analytics-chart">
                ${Array.from({length: 7}, () => {
                    const height = Math.random() * 100 + 20;
                    return `<div class="chart-bar" style="height: ${height}px"></div>`;
                }).join('')}
            </div>

            <div class="recommendations-card">
                <div class="recommendation-title">
                    💡 Рекомендации
                </div>
                <ul class="recommendation-list">
                    <li class="recommendation-item">
                        <div class="recommendation-icon">📦</div>
                        <div class="recommendation-text">
                            Закажите еще ${Math.ceil(analytics.avgDailySales * 7)} шт (хватит на 7 дней)
                        </div>
                        <button class="recommendation-action">Заказать</button>
                    </li>
                </ul>
            </div>
        </div>
    `;

    document.body.appendChild(modal);

    // Закрытие по клику вне модального окна
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.remove();
        }
    });
}

// === 9. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===
function getDaysSince(date) {
    if (!date) return Infinity;
    const then = new Date(date);
    const now = new Date();
    return Math.floor((now - then) / (1000 * 60 * 60 * 24));
}

function updateSelectionUI() {
    selectedProducts.forEach(id => {
        const card = document.querySelector(`[data-product-id="${id}"]`);
        card?.classList.add('selected');
    });

    document.querySelectorAll('.product-card.selected').forEach(card => {
        if (!selectedProducts.has(parseInt(card.dataset.productId))) {
            card.classList.remove('selected');
        }
    });
}

// === ЭКСПОРТ ===
window.initUXImprovements = initUXImprovements;
window.switchViewMode = switchViewMode;
window.showProductAnalytics = showProductAnalytics;
window.toggleProductSelection = toggleProductSelection;

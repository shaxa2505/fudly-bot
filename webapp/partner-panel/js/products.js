/* ================================================
   PRODUCTS MODULE
   Product management and inventory
   ================================================ */

import { productsAPI } from './api.js';
import { formatPrice, toast, validateImageFile, setLoading } from './utils.js';
import { state, actions, computed } from './state.js';

// Load products
export async function loadProducts() {
    try {
        actions.setProductsLoading(true);
        const products = await productsAPI.getAll();
        actions.setProducts(products);
        renderProducts();
        updateFilterCounts();
    } catch (error) {
        console.error('❌ Products load error:', error);
        actions.setProductsError(error.message);
        toast('Ошибка загрузки товаров', 'error');
    }
}

// Render products grid
export function renderProducts() {
    const productsGridEl = document.getElementById('productsGrid');
    if (!productsGridEl) return;

    const products = computed.filteredProducts;

    if (state.productsLoading) {
        productsGridEl.innerHTML = Array(6).fill(0).map(() => `
            <div class="skeleton-card">
                <div class="skeleton-image"></div>
                <div class="skeleton-content">
                    <div class="skeleton-line"></div>
                    <div class="skeleton-line short"></div>
                </div>
            </div>
        `).join('');
        return;
    }

    if (!products || products.length === 0) {
        productsGridEl.innerHTML = `
            <div class="empty-search-state">
                <div class="empty-search-icon">🔍</div>
                <div class="empty-search-title">Ничего не найдено</div>
            </div>
        `;
        return;
    }

    // Apply view mode
    productsGridEl.className = `products-grid ${state.viewMode}`;

    productsGridEl.innerHTML = products.map(product => renderProductCard(product)).join('');

    // Load images
    setTimeout(() => {
        document.querySelectorAll('.product-image').forEach(img => {
            img.classList.add('loaded');
        });
    }, 100);
}

// Render single product card
function renderProductCard(product) {
    const isCompact = state.viewMode === 'compact';
    const compactClass = isCompact ? 'compact' : '';

    return `
        <div class="product-card ${compactClass}" data-product-id="${product.id}">
            <div class="product-image-wrapper">
                <img src="${product.photo_url || '/api/placeholder/300/200'}"
                     alt="${product.name}"
                     class="product-image"
                     onerror="this.src='/api/placeholder/300/200'">

                <div class="product-actions">
                    <button class="action-btn" onclick="window.editProduct(${product.id})">
                        <i data-lucide="edit-2"></i>
                    </button>
                    <button class="action-btn danger" onclick="window.deleteProduct(${product.id})">
                        <i data-lucide="trash-2"></i>
                    </button>
                </div>

                ${product.discount_price > 0 ? `
                <div class="discount-badge">
                    -${Math.round((1 - product.discount_price / product.price) * 100)}%
                </div>
                ` : ''}
            </div>

            <div class="product-info">
                ${product.category ? `
                <div class="product-category">${product.category}</div>
                ` : ''}

                <div class="product-name">${product.name}</div>

                <div class="product-pricing">
                    ${product.discount_price > 0 ? `
                        <div class="original-price">${formatPrice(product.price)}</div>
                        <div class="product-price">${formatPrice(product.discount_price)}</div>
                    ` : `
                        <div class="product-price">${formatPrice(product.price)}</div>
                    `}
                </div>

                <div class="stock-label">
                    📦 Остаток:
                    ${product.quantity <= 5 ? `
                        <span class="low-stock-warning">⚠️ ${product.quantity}</span>
                    ` : `
                        <span>${product.quantity}</span>
                    `}
                </div>

                <div class="product-stock-control">
                    <button class="stock-btn" onclick="window.adjustStock(${product.id}, -1, event)">
                        −
                    </button>
                    <span class="stock-value">${product.quantity}</span>
                    <button class="stock-btn" onclick="window.adjustStock(${product.id}, 1, event)">
                        +
                    </button>
                </div>

                <div class="product-status ${product.is_active ? 'active' : 'hidden'}">
                    ${product.is_active ? 'Активен' : 'Скрыт'}
                </div>
            </div>
        </div>
    `;
}

// Adjust stock
export async function adjustStock(productId, delta, event) {
    if (event) event.stopPropagation();

    const btn = event?.target?.closest('.stock-btn');

    try {
        if (btn) setLoading(btn, true);

        const product = state.products.find(p => p.id === productId);
        if (!product) throw new Error('Товар не найден');

        const newStock = Math.max(0, product.quantity + delta);

        await productsAPI.updateStock(productId, newStock);

        // Update state
        actions.updateProduct(productId, { quantity: newStock });

        // Update UI directly
        const card = document.querySelector(`[data-product-id="${productId}"]`);
        if (card) {
            const stockValueEl = card.querySelector('.stock-value');
            if (stockValueEl) stockValueEl.textContent = newStock;
        }

        updateFilterCounts();
        toast(`Остаток: ${newStock}`, 'success');
    } catch (error) {
        console.error('Error adjusting stock:', error);
        toast('Ошибка обновления остатка', 'error');
    } finally {
        if (btn) setLoading(btn, false);
    }
}

// Filter products
export function filterProducts(filter) {
    actions.setFilter(filter);
    renderProducts();

    // Update filter chips
    document.querySelectorAll('.filter-chip').forEach(chip => {
        chip.classList.toggle('active', chip.dataset.filter === filter);
    });
}

// Search products
export function searchProducts(query) {
    actions.setSearch(query);
    renderProducts();
}

// Change view mode
export function changeViewMode(mode) {
    actions.setViewMode(mode);
    renderProducts();

    // Update view mode buttons
    document.querySelectorAll('.view-mode-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.mode === mode);
    });
}

// Update filter counts
function updateFilterCounts() {
    const counts = computed.productsCounts;

    Object.entries(counts).forEach(([key, count]) => {
        const countEl = document.querySelector(`[data-filter="${key}"] .count`);
        if (countEl) countEl.textContent = count;
    });
}

// Edit product
export function editProduct(productId) {
    const product = state.products.find(p => p.id === productId);
    if (!product) return;

    // TODO: Open edit modal
    toast('Редактирование в разработке', 'info');
}

// Delete product
export async function deleteProduct(productId) {
    if (!confirm('Удалить товар?')) return;

    try {
        await productsAPI.delete(productId);
        actions.deleteProduct(productId);
        renderProducts();
        updateFilterCounts();
        toast('Товар удален', 'success');
    } catch (error) {
        console.error('Error deleting product:', error);
        toast('Ошибка удаления', 'error');
    }
}

// Show add product modal
export function showAddProductModal() {
    // TODO: Implement modal
    toast('Добавление товара в разработке', 'info');
}

// Make functions global for onclick handlers
window.adjustStock = adjustStock;
window.filterProducts = filterProducts;
window.searchProducts = searchProducts;
window.changeViewMode = changeViewMode;
window.editProduct = editProduct;
window.deleteProduct = deleteProduct;
window.showAddProductModal = showAddProductModal;

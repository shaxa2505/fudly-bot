// Telegram WebApp initialization
const tg = window.Telegram?.WebApp || {
    ready: () => console.log('🔧 Dev mode: Telegram WebApp not available'),
    expand: () => {},
    initData: '',
    initDataUnsafe: { user: { id: 0 } },
    onEvent: () => {},
    offEvent: () => {}
};
tg.expand();
tg.ready();

// Enable pull-to-refresh
if (tg.isVersionAtLeast && tg.isVersionAtLeast('7.7')) {
    let isRefreshing = false;
    
    tg.onEvent('viewportChanged', async () => {
        if (!isRefreshing && tg.viewportStableHeight < window.innerHeight - 100) {
            isRefreshing = true;
            showToast('🔄 Обновление...');
            await loadView(currentView);
            isRefreshing = false;
        }
    });
}

// API Configuration - auto-detect environment
const API_BASE_URL = (() => {
    // Check if explicitly set in environment (for build systems)
    if (typeof PARTNER_API_URL !== 'undefined') {
        return PARTNER_API_URL;
    }
    
    // Auto-detect based on hostname
    const hostname = window.location.hostname;
    
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
        return 'http://localhost:8000/api';
    }
    
    // ngrok для локального тестирования
    if (hostname.includes('ngrok')) {
        return 'https://unsplattered-cornelia-cymosely.ngrok-free.dev/api';
    }
    
    // Production Vercel - используем ngrok пока не будет Railway
    return 'https://unsplattered-cornelia-cymosely.ngrok-free.dev/api';
})();

// For development: show API URL in console
console.log('🔌 API Base URL:', API_BASE_URL);
console.log('🌐 Hostname:', window.location.hostname);

// Development mode: use dev auth if not in Telegram
const IS_DEV_MODE = !window.Telegram?.WebApp?.initData;
let DEV_TELEGRAM_ID = localStorage.getItem('dev_telegram_id');
if (IS_DEV_MODE && !DEV_TELEGRAM_ID) {
    DEV_TELEGRAM_ID = prompt('🔧 Development Mode\n\nEnter your Telegram ID for testing:\n(You can find it by sending /start to the bot)', '123456789');
    if (DEV_TELEGRAM_ID) {
        localStorage.setItem('dev_telegram_id', DEV_TELEGRAM_ID);
    }
}
console.log('🔑 Auth mode:', IS_DEV_MODE ? `Development (ID: ${DEV_TELEGRAM_ID})` : 'Production (Telegram WebApp)');
console.log('💡 Tip: Your Telegram ID is saved in localStorage. Clear it to change.');

// Helper to get auth header
function getAuthHeader() {
    return IS_DEV_MODE ? `dev_${DEV_TELEGRAM_ID}` : `tma ${tg.initData}`;
}

// Haptic feedback helper
function haptic(type = 'light') {
    if (tg.HapticFeedback) {
        switch(type) {
            case 'light': tg.HapticFeedback.impactOccurred('light'); break;
            case 'medium': tg.HapticFeedback.impactOccurred('medium'); break;
            case 'heavy': tg.HapticFeedback.impactOccurred('heavy'); break;
            case 'success': tg.HapticFeedback.notificationOccurred('success'); break;
            case 'error': tg.HapticFeedback.notificationOccurred('error'); break;
            case 'warning': tg.HapticFeedback.notificationOccurred('warning'); break;
        }
    }
}

// Toast notification helper
function showToast(message, duration = 2000) {
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => toast.classList.add('show'), 10);
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// State
let currentView = 'products';
let products = [];
let orders = [];
let storeInfo = {};
let currentProduct = null;

// Initialize app
async function init() {
    setupEventListeners();
    await loadUserInfo();
    await loadQuickStats();
    await loadView(currentView);
}

// Load quick stats
async function loadQuickStats() {
    try {
        const response = await fetch(`${API_BASE_URL}/partner/stats?period=today`, {
            headers: { 'Authorization': getAuthHeader() }
        });
        const data = await response.json();
        
        if (response.ok) {
            document.getElementById('todayOrders').textContent = data.orders || 0;
            document.getElementById('todayRevenue').textContent = formatCurrency(data.revenue || 0);
            document.getElementById('activeProducts').textContent = data.active_products || 0;
            document.getElementById('avgTicket').textContent = formatCurrency(data.avg_ticket || 0);
        }
    } catch (error) {
        console.error('Failed to load quick stats:', error);
    }
}

// Format currency helper
function formatCurrency(amount) {
    return new Intl.NumberFormat('ru-RU', {
        style: 'decimal',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0
    }).format(amount) + ' сум';
}

// Setup event listeners
function setupEventListeners() {
    // Tab navigation
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            const view = tab.dataset.view;
            switchView(view);
        });
    });

    // Product actions
    document.getElementById('addProductBtn').addEventListener('click', () => {
        haptic('light');
        openProductModal();
    });
    document.getElementById('importCsvBtn').addEventListener('click', () => {
        haptic('light');
        openCsvModal();
    });
    document.getElementById('cancelProductBtn').addEventListener('click', () => closeProductModal());
    document.getElementById('productForm').addEventListener('submit', handleProductSubmit);
    
    // Filter events
    document.getElementById('searchProducts').addEventListener('input', filterProducts);
    document.getElementById('filterStatus').addEventListener('change', filterProducts);
    document.getElementById('filterCategory').addEventListener('change', filterProducts);
    document.getElementById('sortProducts').addEventListener('change', filterProducts);

    // CSV import
    document.getElementById('selectCsvBtn').addEventListener('click', () => {
        document.getElementById('csvFile').click();
    });
    document.getElementById('csvFile').addEventListener('change', handleCsvSelect);
    document.getElementById('cancelCsvBtn').addEventListener('click', () => closeCsvModal());
    document.getElementById('importCsvConfirmBtn').addEventListener('click', handleCsvImport);

    // Drop zone
    const dropZone = document.getElementById('dropZone');
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('drag-over');
    });
    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('drag-over');
    });
    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        const file = e.dataTransfer.files[0];
        if (file && file.type === 'text/csv') {
            document.getElementById('csvFile').files = e.dataTransfer.files;
            handleCsvSelect({ target: { files: [file] }});
        }
    });

    // Modal close buttons
    document.querySelectorAll('.modal-close').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.target.closest('.modal').classList.remove('active');
        });
    });

    // Filters
    document.getElementById('searchProducts').addEventListener('input', filterProducts);
    document.getElementById('filterStatus').addEventListener('change', filterProducts);
    document.getElementById('filterCategory').addEventListener('change', filterProducts);
    document.getElementById('sortProducts').addEventListener('change', filterProducts);
    document.getElementById('filterOrderStatus').addEventListener('change', loadOrders);
    document.getElementById('statsPeriod').addEventListener('change', loadStats);

    // Settings form
    document.getElementById('settingsForm').addEventListener('submit', handleSettingsSubmit);

    // Photo preview
    document.getElementById('productPhoto').addEventListener('change', previewPhoto);
}

// Load user info
async function loadUserInfo() {
    try {
        const response = await fetch(`${API_BASE_URL}/partner/profile`, {
            headers: { 'Authorization': getAuthHeader() }
        });
        const data = await response.json();
        if (!response.ok) {
            console.error('❌ Profile error:', data);
            document.getElementById('userInfo').textContent = 'Error loading profile';
            return;
        }
        const userInfoEl = document.getElementById('userInfo');
        userInfoEl.textContent = `${data.name} | ${data.city}`;
        storeInfo = data.store || {};
    } catch (error) {
        console.error('Failed to load user info:', error);
        document.getElementById('userInfo').textContent = 'Партнёр';
    }
}

// Switch view
function switchView(view) {
    haptic('light'); // Вибрация при переключении вкладок
    
    // Update tabs
    document.querySelectorAll('.tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.view === view);
    });

    // Update views
    document.querySelectorAll('.view').forEach(v => {
        v.classList.toggle('active', v.id === `${view}-view`);
    });

    currentView = view;
    loadView(view);
}

// Load view data
async function loadView(view) {
    switch (view) {
        case 'products':
            await loadProducts();
            break;
        case 'orders':
            await loadOrders();
            break;
        case 'stats':
            await loadStats();
            break;
        case 'settings':
            loadSettings();
            break;
    }
}

// Load products
async function loadProducts() {
    const container = document.getElementById('productsList');
    
    // Show skeleton loading
    container.innerHTML = `
        <div class="skeleton skeleton-card"></div>
        <div class="skeleton skeleton-card"></div>
        <div class="skeleton skeleton-card"></div>
    `;

    try {
        const response = await fetch(`${API_BASE_URL}/partner/products`, {
            headers: { 'Authorization': getAuthHeader() }
        });
        if (!response.ok) {
            haptic('error');
            const error = await response.json();
            console.error('❌ Products error:', error);
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">⚠️</div>
                    <div class="empty-title">Ошибка загрузки</div>
                    <div class="empty-text">${error.detail || 'Неизвестная ошибка'}</div>
                </div>
            `;
            return;
        }
        products = await response.json();
        renderProducts(products);
    } catch (error) {
        haptic('error');
        console.error('Failed to load products:', error);
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">⚠️</div>
                <div class="empty-title">Ошибка сети</div>
                <div class="empty-text">Проверьте подключение к интернету</div>
            </div>
        `;
    }
}

// Render products
function renderProducts(items) {
    const container = document.getElementById('productsList');
    
    if (items.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">📦</div>
                <div class="empty-title">Товары не найдены</div>
                <div class="empty-text">Добавьте первый товар или измените фильтры</div>
                <button class="btn btn-primary" onclick="document.getElementById('addProductBtn').click()">
                    ➕ Добавить товар
                </button>
            </div>
        `;
        return;
    }

    container.innerHTML = items.map(product => {
        const discount = product.original_price > product.discount_price 
            ? Math.round((1 - product.discount_price / product.original_price) * 100)
            : 0;
        
        // Quantity indicator
        let qtyClass = 'quantity-high';
        let qtyIcon = '✅';
        if (product.quantity <= 5) {
            qtyClass = 'quantity-low';
            qtyIcon = '⚠️';
        } else if (product.quantity <= 20) {
            qtyClass = 'quantity-medium';
            qtyIcon = '📦';
        }
        
        return `
        <div class="product-card ${product.status}" data-product-id="${product.offer_id}">
            <div class="card-header">
                <input type="checkbox" class="product-checkbox" onchange="toggleProductSelection(${product.offer_id})">
                ${discount > 0 ? `<div class="discount-badge">${discount}%</div>` : ''}
            </div>
            <div class="product-image" data-photo-id="${product.photo_id || ''}"></div>
            <div class="product-info">
                <h3 class="product-title">${product.title}</h3>
                <div class="product-price">
                    ${product.original_price > product.discount_price ? `<span class="price-old">${product.original_price.toLocaleString()} сум</span>` : ''}
                    <span class="price-new">${product.discount_price.toLocaleString()} сум</span>
                </div>
                <div class="product-badges">
                    <span class="badge ${qtyClass}">${qtyIcon} ${product.quantity} ${product.unit}</span>
                    <span class="badge status-badge status-${product.status}">${product.status === 'active' ? '●' : '○'}</span>
                </div>
                ${product.expiry_date ? `<div class="expiry-info">⏰ ${new Date(product.expiry_date).toLocaleDateString('ru')}</div>` : ''}
                
                <div class="quick-controls">
                    <div class="qty-control">
                        <button class="qty-btn" onclick="quickChangeQuantity(${product.offer_id}, -1)">−</button>
                        <span class="qty-display">${product.quantity}</span>
                        <button class="qty-btn" onclick="quickChangeQuantity(${product.offer_id}, 1)">+</button>
                    </div>
                    <button class="icon-btn ${product.status}" onclick="quickToggleStatus(${product.offer_id})" title="${product.status === 'active' ? 'Деактивировать' : 'Активировать'}">
                        ${product.status === 'active' ? '👁️' : '🚫'}
                    </button>
                </div>
                
                <div class="card-actions">
                    <button class="action-btn primary" onclick="editProduct(${product.offer_id})">
                        <span>✏️</span><span>Изменить</span>
                    </button>
                    <button class="action-btn secondary" onclick="duplicateProduct(${product.offer_id})">
                        <span>📋</span>
                    </button>
                    <button class="action-btn danger" onclick="deleteProduct(${product.offer_id})">
                        <span>🗑️</span>
                    </button>
                </div>
            </div>
        </div>
    `}).join('');
    
    // Load photos asynchronously
    loadProductPhotos();
}

// Load product photos asynchronously
async function loadProductPhotos() {
    const photoElements = document.querySelectorAll('.product-image[data-photo-id]');
    
    for (const el of photoElements) {
        const photoId = el.getAttribute('data-photo-id');
        if (photoId && !photoId.startsWith('placeholder_')) {
            try {
                const url = await getPhotoUrl(photoId);
                if (url) {
                    el.innerHTML = `<img src="${url}" alt="Фото товара" style="width:100%;height:100%;object-fit:cover;border-radius:8px;">`;
                }
            } catch (e) {
                console.error('Failed to load photo:', e);
            }
        }
    }
}

// Filter products
function filterProducts() {
    const search = document.getElementById('searchProducts').value.toLowerCase();
    const status = document.getElementById('filterStatus').value;
    const category = document.getElementById('filterCategory').value;
    const sort = document.getElementById('sortProducts').value;

    let filtered = products.filter(p => {
        const matchSearch = p.title.toLowerCase().includes(search) || 
                          (p.description && p.description.toLowerCase().includes(search));
        const matchStatus = status === 'all' || p.status === status;
        const matchCategory = category === 'all' || p.category === category;
        return matchSearch && matchStatus && matchCategory;
    });

    // Sort
    filtered.sort((a, b) => {
        switch(sort) {
            case 'date-desc':
                return (b.offer_id || 0) - (a.offer_id || 0);
            case 'date-asc':
                return (a.offer_id || 0) - (b.offer_id || 0);
            case 'price-asc':
                return a.discount_price - b.discount_price;
            case 'price-desc':
                return b.discount_price - a.discount_price;
            case 'quantity-asc':
                return a.quantity - b.quantity;
            case 'quantity-desc':
                return b.quantity - a.quantity;
            case 'name-asc':
                return a.title.localeCompare(b.title, 'ru');
            case 'name-desc':
                return b.title.localeCompare(a.title, 'ru');
            default:
                return 0;
        }
    });

    renderProducts(filtered);
}

// Product modal
function openProductModal(product = null) {
    console.log('Opening product modal, product:', product);
    haptic('light');
    currentProduct = product;
    const modal = document.getElementById('productModal');
    const title = document.getElementById('productModalTitle');
    
    if (product) {
        console.log('Editing existing product:', product.offer_id);
        title.textContent = 'Редактировать товар';
        document.getElementById('productId').value = product.offer_id;
        document.getElementById('productTitle').value = product.title;
        document.getElementById('productCategory').value = product.category || 'other';
        document.getElementById('productOriginalPrice').value = product.original_price || '';
        document.getElementById('productDiscountPrice').value = product.discount_price;
        document.getElementById('productQuantity').value = product.quantity;
        document.getElementById('productUnit').value = product.unit || 'шт';
        document.getElementById('productExpiryDate').value = product.expiry_date || '';
        document.getElementById('productDescription').value = product.description || '';
    } else {
        title.textContent = 'Добавить товар';
        document.getElementById('productForm').reset();
        document.getElementById('photoPreview').innerHTML = '';
    }
    
    modal.classList.add('active');
}

function closeProductModal() {
    document.getElementById('productModal').classList.remove('active');
    currentProduct = null;
}

// Preview photo
function previewPhoto(e) {
    const file = e.target.files[0];
    const preview = document.getElementById('photoPreview');
    
    if (file) {
        const reader = new FileReader();
        reader.onload = (e) => {
            preview.innerHTML = `<img src="${e.target.result}" style="max-width:100%;margin-top:12px;border-radius:8px;">`;
        };
        reader.readAsDataURL(file);
    } else {
        preview.innerHTML = '';
    }
}

// Upload photo and get file_id from Telegram
async function uploadPhotoToTelegram(file) {
    const formData = new FormData();
    formData.append('photo', file);
    
    try {
        const response = await fetch(`${API_BASE_URL}/partner/upload-photo`, {
            method: 'POST',
            headers: { 'Authorization': getAuthHeader() },
            body: formData
        });
        
        if (response.ok) {
            const result = await response.json();
            return result.file_id;
        } else {
            const error = await response.json();
            console.error('Photo upload failed:', error);
            return null;
        }
    } catch (error) {
        console.error('Photo upload error:', error);
        return null;
    }
}

// Get photo URL from file_id
async function getPhotoUrl(fileId) {
    if (!fileId || fileId.startsWith('placeholder_')) {
        return null;
    }
    
    try {
        const response = await fetch(`${API_BASE_URL}/partner/photo/${fileId}`);
        if (response.ok) {
            const result = await response.json();
            return result.url;
        }
    } catch (error) {
        console.error('Failed to get photo URL:', error);
    }
    return null;
}

// Validation helper
function validateProduct(data) {
    const errors = [];
    
    // Title validation
    if (!data.title || data.title.trim().length === 0) {
        errors.push('Название товара обязательно');
    } else if (data.title.length < 3) {
        errors.push('Название должно быть минимум 3 символа');
    } else if (data.title.length > 200) {
        errors.push('Название не должно превышать 200 символов');
    }
    
    // Price validation
    const discountPrice = parseFloat(data.discount_price);
    const originalPrice = parseFloat(data.original_price || 0);
    
    if (isNaN(discountPrice) || discountPrice <= 0) {
        errors.push('Цена со скидкой должна быть больше 0');
    } else if (discountPrice > 100000000) {
        errors.push('Цена не должна превышать 100,000,000 сум');
    }
    
    if (originalPrice > 0 && originalPrice < discountPrice) {
        errors.push('Оригинальная цена не может быть меньше цены со скидкой');
    }
    
    if (originalPrice > 100000000) {
        errors.push('Оригинальная цена не должна превышать 100,000,000 сум');
    }
    
    // Quantity validation
    const quantity = parseInt(data.quantity);
    if (isNaN(quantity) || quantity < 0) {
        errors.push('Количество должно быть 0 или больше');
    } else if (quantity > 100000) {
        errors.push('Количество не должно превышать 100,000');
    }
    
    // Description validation
    if (data.description && data.description.length > 2000) {
        errors.push('Описание не должно превышать 2000 символов');
    }
    
    // Expiry date validation
    if (data.expiry_date) {
        const expiryDate = new Date(data.expiry_date);
        const now = new Date();
        now.setHours(0, 0, 0, 0);
        
        if (expiryDate < now) {
            errors.push('Срок годности не может быть в прошлом');
        }
    }
    
    return errors;
}

// Handle product submit
async function handleProductSubmit(e) {
    e.preventDefault();
    
    // Get form data
    const data = {
        title: document.getElementById('productTitle').value.trim(),
        category: document.getElementById('productCategory').value,
        original_price: document.getElementById('productOriginalPrice').value,
        discount_price: document.getElementById('productDiscountPrice').value,
        quantity: document.getElementById('productQuantity').value,
        unit: document.getElementById('productUnit').value,
        expiry_date: document.getElementById('productExpiryDate').value,
        description: document.getElementById('productDescription').value.trim()
    };
    
    // Validate
    const errors = validateProduct(data);
    if (errors.length > 0) {
        console.error('Validation errors:', errors);
        haptic('error');
        showToast('❌ ' + errors[0]); // Show first error
        return;
    }
    
    console.log('Form data validated successfully:', data);
    
    const formData = new FormData();
    const productId = document.getElementById('productId').value;
    
    formData.append('title', data.title);
    formData.append('category', data.category);
    formData.append('original_price', data.original_price || 0);
    formData.append('discount_price', data.discount_price);
    formData.append('quantity', data.quantity);
    formData.append('unit', data.unit);
    formData.append('expiry_date', data.expiry_date);
    formData.append('description', data.description);
    
    // Handle photo upload
    const photoFile = document.getElementById('productPhoto').files[0];
    const submitBtn = document.querySelector('#productForm button[type="submit"]');
    
    if (photoFile) {
        // Validate photo size (max 10MB)
        if (photoFile.size > 10 * 1024 * 1024) {
            haptic('error');
            showToast('❌ Размер фото не должен превышать 10 МБ');
            return;
        }
        
        // Validate photo type
        if (!photoFile.type.startsWith('image/')) {
            haptic('error');
            showToast('❌ Можно загружать только изображения');
            return;
        }
        
        // Show loading with progress bar
        setButtonLoading(submitBtn, true);
        
        try {
            const fileId = await uploadPhotoWithProgress(photoFile);
            if (fileId) {
                formData.append('photo_id', fileId);
            } else {
                haptic('error');
                showToast('❌ Ошибка загрузки фото');
                setButtonLoading(submitBtn, false);
                return;
            }
        } catch (error) {
            console.error('Photo upload failed:', error);
            haptic('error');
            showToast('❌ Ошибка загрузки фото');
            setButtonLoading(submitBtn, false);
            return;
        }
    } else if (currentProduct && currentProduct.photo_id) {
        // Keep existing photo
        formData.append('photo_id', currentProduct.photo_id);
    }

    // Show loading on submit button
    setButtonLoading(submitBtn, true);

    try {
        const url = productId 
            ? `${API_BASE_URL}/partner/products/${productId}`
            : `${API_BASE_URL}/partner/products`;
        
        const response = await fetch(url, {
            method: productId ? 'PUT' : 'POST',
            headers: { 'Authorization': getAuthHeader() },
            body: formData
        });

        if (response.ok) {
            haptic('success'); // Вибрация успеха
            showSuccessIndicator(); // Показать галочку
            console.log('Product saved successfully');
            closeProductModal();
            await loadProducts();
            await loadQuickStats(); // Обновить статистику
            showToast(productId ? '✅ Товар обновлён' : '✅ Товар добавлен');
        } else {
            haptic('error');
            const error = await response.json();
            console.error('Save error:', error);
            showToast('❌ Ошибка: ' + (error.detail || 'Неизвестная ошибка'));
        }
    } catch (error) {
        haptic('error');
        console.error('Failed to save product:', error);
        showToast('❌ Ошибка сохранения товара');
    } finally {
        setButtonLoading(submitBtn, false);
    }
}

// Edit product
window.editProduct = function(productId) {
    console.log('Edit product called:', productId);
    const product = products.find(p => p.offer_id === productId);
    console.log('Found product:', product);
    if (product) {
        openProductModal(product);
    } else {
        console.error('Product not found:', productId);
    }
};

// Delete product
window.deleteProduct = async function(productId) {
    if (!confirm('Удалить товар?')) return;
    
    haptic('medium');

    try {
        const response = await fetch(`${API_BASE_URL}/partner/products/${productId}`, {
            method: 'DELETE',
            headers: { 'Authorization': getAuthHeader() }
        });

        if (response.ok) {
            haptic('success');
            showToast('✅ Товар удалён');
            await loadProducts();
            await loadQuickStats();
        } else {
            haptic('error');
            showToast('❌ Ошибка удаления');
        }
    } catch (error) {
        haptic('error');
        console.error('Failed to delete product:', error);
        showToast('❌ Ошибка удаления товара');
    }
};

// CSV Import
function openCsvModal() {
    document.getElementById('csvModal').classList.add('active');
}

function closeCsvModal() {
    document.getElementById('csvModal').classList.remove('active');
    document.getElementById('csvFile').value = '';
    document.getElementById('csvPreview').innerHTML = '';
    document.getElementById('importCsvConfirmBtn').disabled = true;
}

function handleCsvSelect(e) {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
        const text = e.target.result;
        const lines = text.split('\n').filter(l => l.trim());
        const preview = document.getElementById('csvPreview');
        
        preview.innerHTML = `
            <div style="margin:16px 0;padding:12px;background:var(--secondary-bg-color);border-radius:8px;">
                <strong>📄 ${file.name}</strong><br>
                <span style="color:var(--hint-color);">Строк: ${lines.length - 1}</span>
            </div>
        `;
        
        document.getElementById('importCsvConfirmBtn').disabled = false;
    };
    reader.readAsText(file);
}

async function handleCsvImport() {
    const file = document.getElementById('csvFile').files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);
    
    haptic('medium');

    try {
        const response = await fetch(`${API_BASE_URL}/partner/products/import`, {
            method: 'POST',
            headers: { 'Authorization': getAuthHeader() },
            body: formData
        });

        const result = await response.json();
        if (response.ok) {
            haptic('success');
            showToast(`✅ Импортировано товаров: ${result.imported}`);
            closeCsvModal();
            await loadProducts();
            await loadQuickStats();
        } else {
            haptic('error');
            showToast('❌ Ошибка: ' + (result.detail || 'Неизвестная ошибка'));
        }
    } catch (error) {
        haptic('error');
        console.error('Failed to import CSV:', error);
        showToast('❌ Ошибка импорта CSV');
    }
}

// Load orders
async function loadOrders() {
    const container = document.getElementById('ordersList');
    container.innerHTML = '<div class="skeleton-loader"><div class="skeleton-card"></div><div class="skeleton-card"></div><div class="skeleton-card"></div></div>';

    try {
        const status = document.getElementById('filterOrderStatus').value;
        const url = status === 'all' 
            ? `${API_BASE_URL}/partner/orders`
            : `${API_BASE_URL}/partner/orders?status=${status}`;

        const response = await fetch(url, {
            headers: { 'Authorization': getAuthHeader() }
        });
        orders = await response.json();
        renderOrders(orders);
    } catch (error) {
        console.error('Failed to load orders:', error);
        container.innerHTML = '<p style="text-align:center;padding:40px;">❌ Ошибка загрузки заказов</p>';
    }
}

// Render orders
function renderOrders(items) {
    const container = document.getElementById('ordersList');
    
    if (items.length === 0) {
        container.innerHTML = '<p style="text-align:center;padding:40px;color:var(--hint-color);">📋 Заказы не найдены</p>';
        return;
    }

    container.innerHTML = items.map(order => {
        const typeIcon = order.type === 'booking' ? '🏪' : '🚚';
        const typeLabel = order.type === 'booking' ? 'Самовывоз' : 'Доставка';
        
        return `
        <div class="order-card">
            <div class="order-header">
                <div>
                    <div class="order-id">${typeIcon} Заказ #${order.order_id}</div>
                    <div style="font-size:12px;color:var(--hint-color);">${new Date(order.created_at).toLocaleString('ru')}</div>
                </div>
                <span class="status-badge status-${order.status}">${getOrderStatusText(order.status)}</span>
            </div>
            <div class="order-items">
                <strong>${order.offer_title || 'Товар'}</strong> × ${order.quantity}
            </div>
            <div><strong>Тип:</strong> ${typeLabel}</div>
            ${order.delivery_address ? `<div style="font-size:13px;color:var(--hint-color);">📍 ${order.delivery_address}</div>` : ''}
            <div><strong>Сумма:</strong> ${order.price} сум</div>
            <div style="font-size:14px;margin-top:8px;">
                👤 Клиент: ${order.customer_name || 'Неизвестно'}<br>
                📞 ${order.customer_phone || ''}
            </div>
            ${order.status === 'pending' ? `
                <div class="order-actions">
                    <button class="btn btn-success btn-sm" onclick="confirmOrder(${order.order_id}, '${order.type}')">✅ Подтвердить</button>
                    <button class="btn btn-danger btn-sm" onclick="cancelOrder(${order.order_id}, '${order.type}')">❌ Отменить</button>
                </div>
            ` : order.status === 'preparing' || order.status === 'confirmed' ? `
                <div class="order-actions">
                    <button class="btn btn-success btn-sm" onclick="markReady(${order.order_id}, '${order.type}')">📦 Готов</button>
                    <button class="btn btn-danger btn-sm" onclick="cancelOrder(${order.order_id}, '${order.type}')">❌ Отменить</button>
                </div>
            ` : order.status === 'ready' && order.type === 'order' ? `
                <div class="order-actions">
                    <button class="btn btn-success btn-sm" onclick="markDelivering(${order.order_id}, '${order.type}')">🚚 В пути</button>
                    <button class="btn btn-danger btn-sm" onclick="cancelOrder(${order.order_id}, '${order.type}')">❌ Отменить</button>
                </div>
            ` : ''}
        </div>
    `}).join('');
}

function getOrderStatusText(status) {
    const texts = {
        'pending': 'Ожидает',
        'confirmed': 'Подтверждён',
        'preparing': 'Готовится',
        'ready': 'Готов',
        'delivering': 'В пути',
        'completed': 'Завершён',
        'cancelled': 'Отменён'
    };
    return texts[status] || status;
}

// Confirm order
window.confirmOrder = async function(orderId, orderType = 'booking') {
    haptic('medium');
    
    try {
        const response = await fetch(`${API_BASE_URL}/partner/orders/${orderId}/confirm?order_type=${orderType}`, {
            method: 'POST',
            headers: { 'Authorization': getAuthHeader() }
        });

        if (response.ok) {
            haptic('success');
            showToast('✅ Заказ подтверждён');
            await loadOrders();
        } else {
            haptic('error');
            showToast('❌ Ошибка подтверждения');
        }
    } catch (error) {
        haptic('error');
        console.error('Failed to confirm order:', error);
        showToast('❌ Ошибка подтверждения заказа');
    }
};

// Cancel order
window.cancelOrder = async function(orderId, orderType = 'booking') {
    if (!confirm('Отменить заказ?')) return;
    
    haptic('medium');

    try {
        const response = await fetch(`${API_BASE_URL}/partner/orders/${orderId}/cancel?order_type=${orderType}`, {
            method: 'POST',
            headers: { 'Authorization': getAuthHeader() }
        });

        if (response.ok) {
            haptic('success');
            showToast('✅ Заказ отменён');
            await loadOrders();
        } else {
            haptic('error');
            showToast('❌ Ошибка отмены');
        }
    } catch (error) {
        haptic('error');
        console.error('Failed to cancel order:', error);
        showToast('❌ Ошибка отмены заказа');
    }
};

// Mark order as ready
window.markReady = async function(orderId, orderType = 'booking') {
    haptic('medium');
    
    try {
        const newStatus = 'ready';
        const response = await fetch(`${API_BASE_URL}/partner/orders/${orderId}/status?status=${newStatus}&order_type=${orderType}`, {
            method: 'POST',
            headers: {
                'Authorization': getAuthHeader()
            }
        });

        if (response.ok) {
            haptic('success');
            showToast('✅ Заказ готов к выдаче');
            await loadOrders();
        } else {
            haptic('error');
            showToast('❌ Ошибка обновления статуса');
        }
    } catch (error) {
        haptic('error');
        console.error('Failed to mark ready:', error);
        showToast('❌ Ошибка обновления статуса');
    }
};

// Mark order as delivering
window.markDelivering = async function(orderId, orderType = 'order') {
    haptic('medium');
    
    try {
        const response = await fetch(`${API_BASE_URL}/partner/orders/${orderId}/status?status=delivering&order_type=${orderType}`, {
            method: 'POST',
            headers: {
                'Authorization': getAuthHeader()
            }
        });

        if (response.ok) {
            haptic('success');
            showToast('✅ Заказ в пути');
            await loadOrders();
        } else {
            haptic('error');
            showToast('❌ Ошибка обновления статуса');
        }
    } catch (error) {
        haptic('error');
        console.error('Failed to mark delivering:', error);
        showToast('❌ Ошибка обновления статуса');
    }
};

// Load stats
async function loadStats() {
    const container = document.getElementById('statsContent');
    container.innerHTML = '<div class="loader">Загрузка статистики...</div>';

    try {
        const period = document.getElementById('statsPeriod').value;
        const response = await fetch(`${API_BASE_URL}/partner/stats?period=${period}`, {
            headers: { 'Authorization': getAuthHeader() }
        });
        const stats = await response.json();
        renderStats(stats);
    } catch (error) {
        console.error('Failed to load stats:', error);
        container.innerHTML = '<p style="text-align:center;padding:40px;">❌ Ошибка загрузки статистики</p>';
    }
}

// ============================================================================
// QUICK ACTIONS
// ============================================================================

// Quick change quantity
window.quickChangeQuantity = async function(offerId, delta) {
    console.log('Quick change quantity:', offerId, delta);
    const product = products.find(p => p.offer_id === offerId);
    if (!product) {
        console.error('Product not found:', offerId);
        return;
    }
    
    const newQuantity = Math.max(0, product.quantity + delta);
    console.log('New quantity:', newQuantity);
    
    try {
        const formData = new FormData();
        formData.append('quantity', newQuantity);
        
        const response = await fetch(`${API_BASE_URL}/partner/products/${offerId}`, {
            method: 'PUT',
            headers: { 'Authorization': getAuthHeader() },
            body: formData
        });
        
        if (response.ok) {
            haptic('light');
            product.quantity = newQuantity;
            // Update display
            const card = document.querySelector(`[data-product-id="${offerId}"]`);
            if (card) {
                card.querySelector('.qty-display').textContent = newQuantity;
                // Update badge
                let qtyClass = 'quantity-high';
                let qtyIcon = '🟢';
                if (newQuantity <= 5) {
                    qtyClass = 'quantity-low';
                    qtyIcon = '🔴';
                } else if (newQuantity <= 20) {
                    qtyClass = 'quantity-medium';
                    qtyIcon = '🟡';
                }
                const badge = card.querySelector('.quantity-badge');
                badge.className = `quantity-badge ${qtyClass}`;
                badge.innerHTML = `${qtyIcon} ${newQuantity} ${product.unit}`;
            }
            await loadQuickStats(); // Обновить статистику
        }
    } catch (error) {
        haptic('error');
        console.error('Failed to update quantity:', error);
        showToast('❌ Ошибка обновления количества');
    }
};

// Quick toggle status
window.quickToggleStatus = async function(offerId) {
    const product = products.find(p => p.offer_id === offerId);
    if (!product) return;
    
    const newStatus = product.status === 'active' ? 'inactive' : 'active';
    
    try {
        const formData = new FormData();
        formData.append('status', newStatus);
        
        const response = await fetch(`${API_BASE_URL}/partner/products/${offerId}`, {
            method: 'PUT',
            headers: { 'Authorization': getAuthHeader() },
            body: formData
        });
        
        if (response.ok) {
            haptic('light');
            product.status = newStatus;
            // Re-render to update UI
            await loadProducts(); // Полная перезагрузка для обновления UI
            await loadQuickStats(); // Обновить статистику
        }
    } catch (error) {
        haptic('error');
        console.error('Failed to toggle status:', error);
        showToast('❌ Ошибка изменения статуса');
    }
};

// Duplicate product
window.duplicateProduct = async function(offerId) {
    const product = products.find(p => p.offer_id === offerId);
    if (!product) return;
    
    try {
        const formData = new FormData();
        formData.append('title', product.title + ' (копия)');
        formData.append('category', product.category || 'other');
        formData.append('original_price', product.original_price || 0);
        formData.append('discount_price', product.discount_price);
        formData.append('quantity', product.quantity);
        formData.append('unit', product.unit || 'шт');
        formData.append('expiry_date', product.expiry_date || '');
        formData.append('description', product.description || '');
        if (product.photo_id) {
            formData.append('photo_id', product.photo_id);
        }
        
        const response = await fetch(`${API_BASE_URL}/partner/products`, {
            method: 'POST',
            headers: { 'Authorization': getAuthHeader() },
            body: formData
        });
        
        if (response.ok) {
            haptic('success');
            showToast('✅ Товар скопирован');
            await loadProducts();
            await loadQuickStats(); // Обновить статистику
        } else {
            haptic('error');
            showToast('❌ Ошибка копирования');
        }
    } catch (error) {
        haptic('error');
        console.error('Failed to duplicate product:', error);
        showToast('❌ Ошибка копирования товара');
    }
};

// ============================================================================
// BULK ACTIONS
// ============================================================================

let selectedProducts = new Set();

window.toggleProductSelection = function(offerId) {
    if (selectedProducts.has(offerId)) {
        selectedProducts.delete(offerId);
    } else {
        selectedProducts.add(offerId);
    }
    
    // Update UI
    const card = document.querySelector(`[data-product-id="${offerId}"]`);
    if (card) {
        card.classList.toggle('selected', selectedProducts.has(offerId));
    }
    
    // Show/hide bulk actions bar
    const bulkBar = document.getElementById('bulkActionsBar');
    const countEl = document.getElementById('selectedCount');
    
    if (selectedProducts.size > 0) {
        bulkBar.style.display = 'flex';
        countEl.textContent = `${selectedProducts.size} выбрано`;
    } else {
        bulkBar.style.display = 'none';
    }
};

window.clearSelection = function() {
    selectedProducts.clear();
    document.querySelectorAll('.product-card.selected').forEach(card => {
        card.classList.remove('selected');
        card.querySelector('.product-checkbox').checked = false;
    });
    document.getElementById('bulkActionsBar').style.display = 'none';
};

window.bulkToggleStatus = async function() {
    if (selectedProducts.size === 0) return;
    
    try {
        const promises = Array.from(selectedProducts).map(offerId => {
            const product = products.find(p => p.offer_id === offerId);
            if (!product) return null;
            
            const newStatus = product.status === 'active' ? 'inactive' : 'active';
            const formData = new FormData();
            formData.append('status', newStatus);
            
            return fetch(`${API_BASE_URL}/partner/products/${offerId}`, {
                method: 'PUT',
                headers: { 'Authorization': getAuthHeader() },
                body: formData
            });
        }).filter(p => p !== null);
        
        await Promise.all(promises);
        haptic('success');
        showToast(`✅ Статус изменён для ${selectedProducts.size} товаров`);
        clearSelection();
        await loadProducts();
        await loadQuickStats(); // Обновить статистику
    } catch (error) {
        haptic('error');
        console.error('Failed bulk toggle:', error);
        showToast('❌ Ошибка массового изменения');
    }
};

window.bulkDelete = async function() {
    if (selectedProducts.size === 0) return;
    
    if (!confirm(`Удалить ${selectedProducts.size} товаров?`)) return;
    
    try {
        const promises = Array.from(selectedProducts).map(offerId => 
            fetch(`${API_BASE_URL}/partner/products/${offerId}`, {
                method: 'DELETE',
                headers: { 'Authorization': getAuthHeader() }
            })
        );
        
        await Promise.all(promises);
        haptic('success');
        showToast(`✅ Удалено ${selectedProducts.size} товаров`);
        clearSelection();
        await loadProducts();
        await loadQuickStats(); // Обновить статистику
    } catch (error) {
        haptic('error');
        console.error('Failed bulk delete:', error);
        showToast('❌ Ошибка массового удаления');
    }
};

// ============================================================================
// STATS
// ============================================================================

// Render stats
function renderStats(stats) {
    const container = document.getElementById('statsContent');
    
    container.innerHTML = `
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">💰 Выручка</div>
                <div class="stat-value">${formatMoney(stats.revenue || 0)}</div>
                <div class="stat-unit">сум</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">🧾 Заказов</div>
                <div class="stat-value">${stats.orders || 0}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">📦 Продано</div>
                <div class="stat-value">${stats.items_sold || 0}</div>
                <div class="stat-unit">шт</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">📇 Активных</div>
                <div class="stat-value">${stats.active_products || 0}</div>
                <div class="stat-unit">товаров</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">🔹 Средний чек</div>
                <div class="stat-value">${formatMoney(stats.avg_ticket || 0)}</div>
                <div class="stat-unit">сум</div>
            </div>
        </div>
        <div style="text-align:center;margin-top:20px;color:var(--text-light);font-size:13px;">
            Обновлено: ${new Date().toLocaleTimeString('ru')}
        </div>
    `;
}

function formatMoney(value) {
    return Math.floor(value).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
}

// Load settings
function loadSettings() {
    document.getElementById('storeName').value = storeInfo.name || '';
    document.getElementById('storeAddress').value = storeInfo.address || '';
    document.getElementById('storePhone').value = storeInfo.phone || '';
    document.getElementById('storeDescription').value = storeInfo.description || '';
}

// Handle settings submit
async function handleSettingsSubmit(e) {
    e.preventDefault();

    const settings = {
        name: document.getElementById('storeName').value,
        address: document.getElementById('storeAddress').value,
        phone: document.getElementById('storePhone').value,
        description: document.getElementById('storeDescription').value
    };

    try {
        const response = await fetch(`${API_BASE_URL}/partner/store`, {
            method: 'PUT',
            headers: {
                'Authorization': getAuthHeader(),
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(settings)
        });

        if (response.ok) {
            haptic('success');
            showToast('✅ Настройки сохранены');
            storeInfo = { ...storeInfo, ...settings };
        } else {
            haptic('error');
            showToast('❌ Ошибка сохранения');
        }
    } catch (error) {
        haptic('error');
        console.error('Failed to save settings:', error);
        showToast('❌ Ошибка сохранения настроек');
    }
}

// Initialize on page load
window.addEventListener('DOMContentLoaded', init);

// ============================================================================
// UX IMPROVEMENTS - 10 критичных улучшений
// ============================================================================

// 1. Быстрые кнопки срока годности
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('btn-quick-expiry')) {
        const days = parseInt(e.target.dataset.days);
        const today = new Date();
        today.setDate(today.getDate() + days);
        const dateString = today.toISOString().split('T')[0];
        document.getElementById('productExpiryDate').value = dateString;
        haptic('light');
    }
});

// 2. Сохранение фильтров в localStorage
function saveFilters() {
    const filters = {
        search: document.getElementById('searchProducts').value,
        status: document.getElementById('filterStatus').value,
        category: document.getElementById('filterCategory').value,
        sort: document.getElementById('sortProducts').value
    };
    localStorage.setItem('partnerFilters', JSON.stringify(filters));
}

function loadFilters() {
    try {
        const saved = localStorage.getItem('partnerFilters');
        if (saved) {
            const filters = JSON.parse(saved);
            if (filters.search) document.getElementById('searchProducts').value = filters.search;
            if (filters.status) document.getElementById('filterStatus').value = filters.status;
            if (filters.category) document.getElementById('filterCategory').value = filters.category;
            if (filters.sort) document.getElementById('sortProducts').value = filters.sort;
        }
    } catch (e) {
        console.error('Failed to load filters:', e);
    }
}

// Сохранять фильтры при изменении
['searchProducts', 'filterStatus', 'filterCategory', 'sortProducts'].forEach(id => {
    const el = document.getElementById(id);
    if (el) {
        el.addEventListener('change', saveFilters);
        el.addEventListener('input', saveFilters);
    }
});

// 3. Auto-refresh статистики каждые 30 секунд
let autoRefreshInterval;
function startAutoRefresh() {
    if (autoRefreshInterval) clearInterval(autoRefreshInterval);
    
    autoRefreshInterval = setInterval(async () => {
        if (currentView === 'stats') {
            showRefreshIndicator();
            await loadStats();
            await loadQuickStats();
            hideRefreshIndicator();
        } else if (currentView === 'products') {
            await loadQuickStats();
        }
    }, 30000); // 30 секунд
}

function showRefreshIndicator() {
    if (!document.getElementById('refreshIndicator')) {
        const indicator = document.createElement('div');
        indicator.id = 'refreshIndicator';
        indicator.className = 'auto-refresh-indicator';
        indicator.innerHTML = '<div class="refresh-spinner"></div><span>Обновление...</span>';
        document.body.appendChild(indicator);
    }
}

function hideRefreshIndicator() {
    const indicator = document.getElementById('refreshIndicator');
    if (indicator) {
        indicator.remove();
    }
}

// 4. Success indicator при сохранении
function showSuccessIndicator() {
    const indicator = document.createElement('div');
    indicator.className = 'success-indicator';
    indicator.textContent = '✓';
    document.body.appendChild(indicator);
    
    setTimeout(() => {
        indicator.style.opacity = '0';
        indicator.style.transform = 'translate(-50%, -50%) scale(0)';
        setTimeout(() => indicator.remove(), 300);
    }, 800);
}

// 5. Показывать предупреждения об истекающих товарах
function addExpiryWarnings() {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);
    const threeDays = new Date(today);
    threeDays.setDate(threeDays.getDate() + 3);
    
    products.forEach(product => {
        if (!product.expiry_date) return;
        
        const expiryDate = new Date(product.expiry_date);
        expiryDate.setHours(0, 0, 0, 0);
        
        const card = document.querySelector(`[data-product-id="${product.offer_id}"]`);
        if (!card) return;
        
        // Удалить старые предупреждения
        card.querySelectorAll('.expiry-warning').forEach(el => el.remove());
        
        if (expiryDate <= today) {
            const warning = document.createElement('div');
            warning.className = 'expiry-warning';
            warning.textContent = '⚠️ Истёк!';
            card.appendChild(warning);
        } else if (expiryDate <= tomorrow) {
            const warning = document.createElement('div');
            warning.className = 'expiry-warning';
            warning.textContent = '🔴 Истекает сегодня!';
            card.appendChild(warning);
        } else if (expiryDate <= threeDays) {
            const warning = document.createElement('div');
            warning.className = 'expiry-warning expiry-soon';
            warning.textContent = '🟡 Скоро истечёт';
            card.appendChild(warning);
        }
    });
}

// 6. Показывать предупреждения о низком запасе
function addLowStockWarnings() {
    products.forEach(product => {
        const card = document.querySelector(`[data-product-id="${product.offer_id}"]`);
        if (!card) return;
        
        const qtyBadge = card.querySelector('.quantity-badge');
        if (!qtyBadge) return;
        
        // Удалить старые метки
        qtyBadge.querySelectorAll('.low-stock-badge, .medium-stock-badge').forEach(el => el.remove());
        
        if (product.quantity === 0) {
            const badge = document.createElement('span');
            badge.className = 'low-stock-badge';
            badge.textContent = 'Закончился!';
            qtyBadge.appendChild(badge);
        } else if (product.quantity <= 5) {
            const badge = document.createElement('span');
            badge.className = 'low-stock-badge';
            badge.textContent = 'Заканчивается';
            qtyBadge.appendChild(badge);
        } else if (product.quantity <= 10) {
            const badge = document.createElement('span');
            badge.className = 'medium-stock-badge';
            badge.textContent = 'Мало';
            qtyBadge.appendChild(badge);
        }
    });
}

// 7. Улучшенная загрузка фото с прогресс-баром
async function uploadPhotoWithProgress(file) {
    const progressEl = document.getElementById('photoProgress');
    const progressBar = progressEl.querySelector('.photo-progress-bar');
    const progressText = progressEl.querySelector('.photo-progress-text');
    
    progressEl.style.display = 'block';
    progressText.textContent = 'Загрузка фото...';
    
    const formData = new FormData();
    formData.append('photo', file);
    
    try {
        const response = await fetch(`${API_BASE_URL}/partner/upload-photo`, {
            method: 'POST',
            headers: { 'Authorization': getAuthHeader() },
            body: formData
        });
        
        if (response.ok) {
            progressText.textContent = '✅ Фото загружено!';
            const result = await response.json();
            setTimeout(() => {
                progressEl.style.display = 'none';
            }, 1000);
            return result.file_id;
        } else {
            progressText.textContent = '❌ Ошибка загрузки';
            setTimeout(() => {
                progressEl.style.display = 'none';
            }, 2000);
            return null;
        }
    } catch (error) {
        console.error('Photo upload error:', error);
        progressText.textContent = '❌ Ошибка загрузки';
        setTimeout(() => {
            progressEl.style.display = 'none';
        }, 2000);
        return null;
    }
}

// 8. Loading state для кнопки сохранения
function setButtonLoading(button, loading) {
    if (loading) {
        button.dataset.originalText = button.textContent;
        button.classList.add('btn-loading');
        button.disabled = true;
    } else {
        button.classList.remove('btn-loading');
        button.disabled = false;
        if (button.dataset.originalText) {
            button.textContent = button.dataset.originalText;
        }
    }
}

// 9. Загрузка фильтров при инициализации
setTimeout(() => {
    loadFilters();
    if (document.getElementById('searchProducts').value || 
        document.getElementById('filterStatus').value !== 'all' ||
        document.getElementById('filterCategory').value !== 'all') {
        filterProducts();
    }
}, 100);

// 10. Запуск auto-refresh
startAutoRefresh();

// Обновление рендеринга товаров для показа предупреждений
const originalRenderProducts = window.renderProducts || renderProducts;
window.renderProducts = function(items) {
    originalRenderProducts(items);
    setTimeout(() => {
        addExpiryWarnings();
        addLowStockWarnings();
    }, 100);
};

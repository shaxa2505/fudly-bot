/* ================================================
   API MODULE
   Handles all backend communication
   ================================================ */

// API Base URL (overridable for standalone hosting)
const API_BASE = window.PARTNER_API_BASE ||
    document.querySelector('meta[name="api-base"]')?.getAttribute('content') ||
    window.location.origin;

const AUTH_MAX_AGE_SECONDS = Number(window.PARTNER_AUTH_MAX_AGE_SECONDS || 86400);

const parseAuthDate = (raw) => {
    if (!raw) return null;
    const ts = Number(raw);
    return Number.isFinite(ts) ? ts : null;
};

const extractAuthDate = (initData) => {
    if (!initData) return null;
    try {
        const params = new URLSearchParams(initData);
        return parseAuthDate(params.get('auth_date'));
    } catch (e) {
        return null;
    }
};

const isAuthExpired = (authTs) => {
    if (!authTs) return false;
    const age = Math.floor(Date.now() / 1000) - authTs;
    return age > AUTH_MAX_AGE_SECONDS || age < -300;
};

// Get authentication data
export function getAuth() {
    const urlParams = new URLSearchParams(window.location.search);
    const urlUserId = urlParams.get('uid');

    const tg = window.Telegram?.WebApp;
    let finalData = '';
    let source = 'none';
    let authExpired = false;

    if (tg?.initData && tg.initData.length > 0) {
        finalData = tg.initData;
        source = 'sdk';
    } else if (window.location.hash.slice(1) && window.location.hash.slice(1).includes('user=')) {
        finalData = window.location.hash.slice(1);
        source = 'hash';
    } else if (tg?.initDataUnsafe?.user) {
        const user = tg.initDataUnsafe.user;
        const params = new URLSearchParams();
        params.set('user', JSON.stringify(user));
        params.set('auth_date', Math.floor(Date.now() / 1000).toString());
        finalData = params.toString();
        source = 'unsafe';
    }

    if (urlUserId && !finalData) {
        finalData = `uid=${urlUserId}`;
        source += '+url';
    }

    const tgUser = tg?.initDataUnsafe?.user;
    const userId = urlUserId || tgUser?.id || 'none';
    const initAuthTs = extractAuthDate(finalData);

    if (isAuthExpired(initAuthTs)) {
        authExpired = true;
        finalData = '';
    }

    return { data: finalData, userId, source, authExpired };
}

function buildAuthHeaders(initData, extraHeaders = {}, options = {}) {
    const headers = {
        'X-Telegram-Init-Data': initData || '',
        ...extraHeaders
    };

    if (!options.skipContentType) {
        headers['Content-Type'] = 'application/json';
    }

    if (initData) {
        headers.Authorization = `tma ${initData}`;
    }

    return headers;
}

function normalizeOrderStatus(rawStatus) {
    if (!rawStatus) return '';
    const status = String(rawStatus).trim().toLowerCase();
    if (status === 'confirmed') return 'preparing';
    return status;
}

function normalizeOrder(raw) {
    if (!raw) return raw;

    const id = raw.id ?? raw.order_id ?? raw.booking_id;
    const status = normalizeOrderStatus(raw.status ?? raw.order_status ?? 'pending');
    const orderType =
        raw.order_type ??
        (raw.type === 'booking' ? 'pickup' : raw.type === 'order' ? 'delivery' : undefined);
    const totalPrice = raw.total_price ?? raw.price ?? raw.total ?? 0;
    const productName = raw.product_name ?? raw.offer_title ?? raw.title ?? 'Товар';

    return {
        ...raw,
        id,
        status,
        order_status: status,
        order_type: orderType || raw.order_type,
        total_price: totalPrice,
        product_name: productName
    };
}

// Fetch helper with auth headers
export async function apiFetch(endpoint, options = {}) {
    const { data: initData, authExpired } = getAuth();

    if (authExpired) {
        throw new Error('Session expired. Please reopen this panel from the Telegram bot.');
    }

    const headers = buildAuthHeaders(initData, options.headers || {});

    const response = await fetch(`${API_BASE}${endpoint}`, {
        ...options,
        headers
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Network error' }));
        throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
}

// Products API
export const productsAPI = {
    async getAll() {
        return apiFetch('/api/partner/products');
    },

    async getById(id) {
        return apiFetch(`/api/partner/products/${id}`);
    },

    async create(product) {
        return apiFetch('/api/partner/products', {
            method: 'POST',
            body: JSON.stringify(product)
        });
    },

    async update(id, product) {
        return apiFetch(`/api/partner/products/${id}`, {
            method: 'PUT',
            body: JSON.stringify(product)
        });
    },

    async delete(id) {
        return apiFetch(`/api/partner/products/${id}`, {
            method: 'DELETE'
        });
    },

    async updateStock(id, quantity) {
        return apiFetch(`/api/partner/products/${id}`, {
            method: 'PATCH',
            body: JSON.stringify({ quantity })
        });
    },

    async uploadImage(file) {
        const formData = new FormData();
        formData.append('photo', file);

        const { data: initData } = getAuth();

        const response = await fetch(`${API_BASE}/api/partner/upload-photo`, {
            method: 'POST',
            headers: buildAuthHeaders(initData, {}, { skipContentType: true }),
            body: formData
        });

        if (!response.ok) {
            throw new Error('Failed to upload image');
        }

        return response.json();
    }
};

// Orders API
export const ordersAPI = {
    async getAll(status = null) {
        const url = status
            ? `/api/partner/orders?status=${status}`
            : '/api/partner/orders';
        const orders = await apiFetch(url);
        return Array.isArray(orders) ? orders.map(normalizeOrder) : orders;
    },

    async getById(id) {
        const order = await apiFetch(`/api/partner/orders/${id}`);
        return normalizeOrder(order);
    },

    async updateStatus(id, status) {
        return apiFetch(`/api/partner/orders/${id}/status?status=${status}`, {
            method: 'POST'
        });
    },

    async confirm(id) {
        return apiFetch(`/api/partner/orders/${id}/confirm`, {
            method: 'POST'
        });
    },

    async ready(id) {
        return this.updateStatus(id, 'ready');
    },

    async cancel(id, reason = '') {
        return apiFetch(`/api/partner/orders/${id}/cancel`, {
            method: 'POST',
            body: JSON.stringify({ reason })
        });
    }
};

// Statistics API
export const statsAPI = {
    async getDashboard(period = 'today') {
        return apiFetch(`/api/partner/stats?period=${period}`);
    },

    async getRevenue(period = 'week') {
        return apiFetch(`/api/partner/stats?period=${period}`);
    },

    async getProducts() {
        return apiFetch('/api/partner/stats?period=month');
    }
};

// Store API
export const storeAPI = {
    async getInfo() {
        return apiFetch('/api/partner/store');
    },

    async updateInfo(data) {
        return apiFetch('/api/partner/store', {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    },

    async updateStatus(isOpen) {
        return apiFetch('/api/partner/store/status', {
            method: 'PATCH',
            body: JSON.stringify({ is_open: isOpen })
        });
    }
};

/* ================================================
   API MODULE
   Handles all backend communication
   ================================================ */

// API Base URL (will use relative paths in production)
const API_BASE = window.location.origin;

// Get authentication data
export function getAuth() {
    const urlParams = new URLSearchParams(window.location.search);
    const urlUserId = urlParams.get('uid');

    const tg = window.Telegram?.WebApp;
    let finalData = '';
    let source = 'none';

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

    if (urlUserId) {
        finalData = finalData ? `${finalData}&uid=${urlUserId}` : `uid=${urlUserId}`;
        source += '+url';
    }

    const tgUser = tg?.initDataUnsafe?.user;
    const userId = urlUserId || tgUser?.id || 'none';

    return { data: finalData, userId, source };
}

// Fetch helper with auth headers
export async function apiFetch(endpoint, options = {}) {
    const { data: initData } = getAuth();

    const headers = {
        'Content-Type': 'application/json',
        'X-Telegram-Init-Data': initData || '',
        ...options.headers
    };

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
        return apiFetch('/api/seller/products');
    },

    async getById(id) {
        return apiFetch(`/api/seller/products/${id}`);
    },

    async create(product) {
        return apiFetch('/api/seller/products', {
            method: 'POST',
            body: JSON.stringify(product)
        });
    },

    async update(id, product) {
        return apiFetch(`/api/seller/products/${id}`, {
            method: 'PUT',
            body: JSON.stringify(product)
        });
    },

    async delete(id) {
        return apiFetch(`/api/seller/products/${id}`, {
            method: 'DELETE'
        });
    },

    async updateStock(id, quantity) {
        return apiFetch(`/api/seller/products/${id}/stock`, {
            method: 'PATCH',
            body: JSON.stringify({ quantity })
        });
    },

    async uploadImage(file) {
        const formData = new FormData();
        formData.append('image', file);

        const { data: initData } = getAuth();

        const response = await fetch(`${API_BASE}/api/seller/products/upload-image`, {
            method: 'POST',
            headers: {
                'X-Telegram-Init-Data': initData || ''
            },
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
            ? `/api/seller/orders?status=${status}`
            : '/api/seller/orders';
        return apiFetch(url);
    },

    async getById(id) {
        return apiFetch(`/api/seller/orders/${id}`);
    },

    async updateStatus(id, status) {
        return apiFetch(`/api/seller/orders/${id}/status`, {
            method: 'PATCH',
            body: JSON.stringify({ status })
        });
    },

    async confirm(id) {
        return this.updateStatus(id, 'confirmed');
    },

    async ready(id) {
        return this.updateStatus(id, 'ready');
    },

    async cancel(id, reason = '') {
        return apiFetch(`/api/seller/orders/${id}/cancel`, {
            method: 'POST',
            body: JSON.stringify({ reason })
        });
    }
};

// Statistics API
export const statsAPI = {
    async getDashboard(period = 'today') {
        return apiFetch(`/api/seller/stats/dashboard?period=${period}`);
    },

    async getRevenue(period = 'week') {
        return apiFetch(`/api/seller/stats/revenue?period=${period}`);
    },

    async getProducts() {
        return apiFetch('/api/seller/stats/products');
    }
};

// Store API
export const storeAPI = {
    async getInfo() {
        return apiFetch('/api/seller/store/info');
    },

    async updateInfo(data) {
        return apiFetch('/api/seller/store/info', {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    },

    async updateStatus(isOpen) {
        return apiFetch('/api/seller/store/status', {
            method: 'PATCH',
            body: JSON.stringify({ is_open: isOpen })
        });
    }
};

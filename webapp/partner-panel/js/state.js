/* ================================================
   STATE MODULE
   Global application state management
   ================================================ */

// Application state
export const state = {
    // Products
    products: [],
    productsLoading: false,
    productsError: null,

    // Orders
    orders: [],
    ordersLoading: false,
    ordersError: null,

    // Stats
    stats: null,
    statsLoading: false,

    // Store info
    storeInfo: null,
    storeName: 'Загрузка...',

    // UI state
    currentView: 'dashboard', // 'dashboard', 'orders', 'products', 'stats', 'settings'
    currentFilter: 'all', // For products/orders filtering
    searchQuery: '',
    viewMode: 'grid', // 'grid' or 'compact' for products

    // Selected items
    selectedProduct: null,
    selectedOrder: null,

    // Charts
    charts: {},

    // Period for stats
    statsPeriod: 'today' // 'today', 'week', 'month'
};

// State listeners
const listeners = new Set();

// Subscribe to state changes
export function subscribe(callback) {
    listeners.add(callback);
    return () => listeners.delete(callback); // Unsubscribe function
}

// Notify all listeners
function notify(changes) {
    listeners.forEach(callback => callback(changes));
}

// Update state and notify listeners
export function setState(updates) {
    const changes = {};

    for (const [key, value] of Object.entries(updates)) {
        if (state[key] !== value) {
            changes[key] = { old: state[key], new: value };
            state[key] = value;
        }
    }

    if (Object.keys(changes).length > 0) {
        notify(changes);
    }
}

// Batch update (for related changes)
export function batchUpdate(updateFn) {
    const changes = {};
    const updates = {};

    // Capture all changes
    const proxy = new Proxy(state, {
        set(target, key, value) {
            if (target[key] !== value) {
                changes[key] = { old: target[key], new: value };
                updates[key] = value;
            }
            return true;
        }
    });

    updateFn(proxy);

    // Apply all changes
    Object.assign(state, updates);

    // Notify once
    if (Object.keys(changes).length > 0) {
        notify(changes);
    }
}

// Computed values
export const computed = {
    // Filtered products
    get filteredProducts() {
        let result = state.products;

        // Filter by status
        if (state.currentFilter !== 'all') {
            result = result.filter(p => {
                if (state.currentFilter === 'active') return p.is_active;
                if (state.currentFilter === 'hidden') return !p.is_active;
                if (state.currentFilter === 'low-stock') return p.quantity <= 5;
                if (state.currentFilter === 'discount') return p.discount_price > 0;
                return true;
            });
        }

        // Search
        if (state.searchQuery) {
            const query = state.searchQuery.toLowerCase();
            result = result.filter(p =>
                p.name.toLowerCase().includes(query) ||
                p.category?.toLowerCase().includes(query)
            );
        }

        return result;
    },

    // Filtered orders
    get filteredOrders() {
        if (state.currentFilter === 'all') {
            return state.orders;
        }
        return state.orders.filter(o => o.status === state.currentFilter);
    },

    // Products count by category
    get productsCounts() {
        return {
            all: state.products.length,
            active: state.products.filter(p => p.is_active).length,
            hidden: state.products.filter(p => !p.is_active).length,
            lowStock: state.products.filter(p => p.quantity <= 5).length,
            discount: state.products.filter(p => p.discount_price > 0).length
        };
    },

    // Orders count by status
    get ordersCounts() {
        const counts = { all: state.orders.length };
        state.orders.forEach(order => {
            counts[order.status] = (counts[order.status] || 0) + 1;
        });
        return counts;
    },

    // Total revenue
    get totalRevenue() {
        return state.orders
            .filter(o => ['completed', 'ready', 'preparing'].includes(o.status))
            .reduce((sum, o) => sum + (o.total_price || 0), 0);
    }
};

// Actions
export const actions = {
    // Products
    setProducts(products) {
        setState({ products, productsLoading: false, productsError: null });
    },

    setProductsLoading(loading) {
        setState({ productsLoading: loading });
    },

    setProductsError(error) {
        setState({ productsError: error, productsLoading: false });
    },

    addProduct(product) {
        setState({ products: [...state.products, product] });
    },

    updateProduct(id, updates) {
        setState({
            products: state.products.map(p =>
                p.id === id ? { ...p, ...updates } : p
            )
        });
    },

    deleteProduct(id) {
        setState({
            products: state.products.filter(p => p.id !== id)
        });
    },

    // Orders
    setOrders(orders) {
        setState({ orders, ordersLoading: false, ordersError: null });
    },

    setOrdersLoading(loading) {
        setState({ ordersLoading: loading });
    },

    updateOrder(id, updates) {
        setState({
            orders: state.orders.map(o =>
                (o.id ?? o.order_id ?? o.booking_id) === id ? { ...o, ...updates } : o
            )
        });
    },

    // Stats
    setStats(stats) {
        setState({ stats, statsLoading: false });
    },

    setStatsLoading(loading) {
        setState({ statsLoading: loading });
    },

    setStatsPeriod(period) {
        setState({ statsPeriod: period });
    },

    // UI
    setView(view) {
        setState({ currentView: view });
    },

    setFilter(filter) {
        setState({ currentFilter: filter, searchQuery: '' });
    },

    setSearch(query) {
        setState({ searchQuery: query });
    },

    setViewMode(mode) {
        setState({ viewMode: mode });
    },

    // Store
    setStoreInfo(info) {
        setState({
            storeInfo: info,
            storeName: info?.name || 'Мой магазин'
        });
    }
};

// Restore state from localStorage
export function restoreState() {
    try {
        const saved = localStorage.getItem('partnerPanelState');
        if (saved) {
            const data = JSON.parse(saved);
            // Only restore UI preferences, not data
            if (data.viewMode) setState({ viewMode: data.viewMode });
            if (data.statsPeriod) setState({ statsPeriod: data.statsPeriod });
        }
    } catch (err) {
        console.error('Failed to restore state:', err);
    }
}

// Save state to localStorage
export function saveState() {
    try {
        const toSave = {
            viewMode: state.viewMode,
            statsPeriod: state.statsPeriod
        };
        localStorage.setItem('partnerPanelState', JSON.stringify(toSave));
    } catch (err) {
        console.error('Failed to save state:', err);
    }
}

// Auto-save on changes
subscribe(() => {
    saveState();
});

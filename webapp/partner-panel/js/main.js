/* ================================================
   MAIN MODULE
   Application initialization and navigation
   ================================================ */

import { getAuth } from './api.js';
import { toast, device } from './utils.js';
import { state, setState, actions, restoreState } from './state.js';

// Telegram WebApp
export const tg = window.Telegram?.WebApp;

// Initialize Telegram WebApp
export function initTelegramWebApp() {
    if (tg) {
        tg.ready();
        tg.expand();

        // Set theme colors
        if (tg.themeParams) {
            document.documentElement.style.setProperty('--tg-bg', tg.themeParams.bg_color || '#ffffff');
            document.documentElement.style.setProperty('--tg-text', tg.themeParams.text_color || '#000000');
            document.documentElement.style.setProperty('--tg-hint', tg.themeParams.hint_color || '#999999');
        }

        // Handle back button
        tg.BackButton.onClick(() => {
            if (state.currentView !== 'dashboard') {
                switchView('dashboard');
            }
        });

        console.log('✅ Telegram WebApp initialized');
    } else {
        console.warn('⚠️ Telegram WebApp SDK not available');
    }
}

// Show debug overlay (dev mode only)
export function showDebugOverlay() {
    const isDev = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    const urlParams = new URLSearchParams(window.location.search);
    const showDebug = isDev || urlParams.get('debug') === 'true';

    const { data: initData, userId, source } = getAuth();

    if (!initData && showDebug) {
        console.warn('⚠️ No initData - showing debug overlay (dev mode only)');

        const debugDiv = document.createElement('div');
        debugDiv.style.cssText = 'position: fixed; bottom: 80px; left: 16px; right: 16px; background: rgba(239, 68, 68, 0.95); color: white; padding: 16px; border-radius: 12px; font-size: 13px; z-index: 999; box-shadow: 0 4px 12px rgba(0,0,0,0.3);';
        debugDiv.innerHTML = `
            <div style="font-weight: 700; margin-bottom: 8px;">🔧 Debug Mode</div>
            <div style="opacity: 0.9; line-height: 1.6;">
                <div>• Telegram SDK: ${tg ? '✅' : '❌'}</div>
                <div>• Init Data: ${initData ? '✅' : '❌ Missing'}</div>
                <div>• Auth Source: ${source}</div>
                <div>• User ID: ${userId}</div>
                <div>• Device: ${device.isMobile ? '📱 Mobile' : '💻 Desktop'}</div>
            </div>
            <button onclick="this.parentElement.remove()" style="margin-top: 12px; padding: 8px 16px; background: rgba(255,255,255,0.2); border: none; border-radius: 6px; color: white; font-weight: 600; cursor: pointer;">
                Понятно
            </button>
        `;
        document.body.appendChild(debugDiv);
    }
}

// Navigation
export function switchView(viewName) {
    // Hide all sections
    document.querySelectorAll('[id$="Section"]').forEach(section => {
        section.classList.add('hide');
    });

    // Show selected section
    const sectionId = viewName + 'Section';
    const section = document.getElementById(sectionId);
    if (section) {
        section.classList.remove('hide');
    }

    // Update nav items
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
    });

    const activeNav = document.querySelector(`[onclick="switchView('${viewName}')"]`);
    if (activeNav) {
        activeNav.classList.add('active');
    }

    // Update state
    actions.setView(viewName);

    // Show/hide back button
    if (tg) {
        if (viewName !== 'dashboard') {
            tg.BackButton.show();
        } else {
            tg.BackButton.hide();
        }
    }

    // Load data for view
    loadViewData(viewName);
}

// Load data for specific view
async function loadViewData(viewName) {
    switch (viewName) {
        case 'dashboard':
            // Already loaded on init
            break;
        case 'orders':
            if (!state.orders.length) {
                const { loadOrders } = await import('./orders.js');
                loadOrders();
            }
            break;
        case 'products':
            if (!state.products.length) {
                const { loadProducts } = await import('./products.js');
                loadProducts();
            }
            break;
        case 'stats':
            const { loadStatistics } = await import('./stats.js');
            loadStatistics(state.statsPeriod);
            break;
        case 'settings':
            const { loadSettings } = await import('./settings.js');
            loadSettings();
            break;
    }
}

// Refresh all data
export async function refreshAll() {
    toast('Обновление...', 'info', 1000);

    try {
        // Refresh based on current view
        switch (state.currentView) {
            case 'dashboard':
                const { loadDashboard } = await import('./orders.js');
                await loadDashboard();
                break;
            case 'orders':
                const { loadOrders } = await import('./orders.js');
                await loadOrders();
                break;
            case 'products':
                const { loadProducts } = await import('./products.js');
                await loadProducts();
                break;
            case 'stats':
                const { loadStatistics } = await import('./stats.js');
                await loadStatistics(state.statsPeriod);
                break;
        }

        toast('Обновлено!', 'success', 1500);
    } catch (error) {
        console.error('Refresh error:', error);
        toast('Ошибка обновления', 'error');
    }
}

// Initialize Lucide icons
export function initIcons() {
    if (window.lucide) {
        lucide.createIcons();
    }
}

// Initialize app
export async function init() {
    console.log('🚀 Initializing Partner Panel...');

    // 1. Restore saved state
    restoreState();

    // 2. Initialize Telegram WebApp
    initTelegramWebApp();

    // 3. Show debug overlay if needed
    showDebugOverlay();

    // 4. Initialize icons
    initIcons();

    // 5. Load store info
    try {
        const { storeAPI } = await import('./api.js');
        const storeInfo = await storeAPI.getInfo();
        actions.setStoreInfo(storeInfo);
        document.getElementById('storeName').textContent = storeInfo.name || 'Мой магазин';
    } catch (error) {
        console.error('Failed to load store info:', error);
    }

    // 6. Load initial view data
    const { loadDashboard } = await import('./orders.js');
    await loadDashboard();

    // 7. Initialize improvements (if available)
    if (window.initImprovements) {
        window.initImprovements();
    }

    console.log('✅ Partner Panel initialized');
}

// Make functions global for onclick handlers
window.switchView = switchView;
window.refreshAll = refreshAll;

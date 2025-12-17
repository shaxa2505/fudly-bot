/* ================================================
   UTILS MODULE
   Helper functions used across the app
   ================================================ */

// Format price in sums
export function formatPrice(kopeks) {
    if (kopeks == null || kopeks === '') return '0 сум';
    const sums = Math.floor(Number(kopeks) / 100);
    return sums.toLocaleString('ru-RU') + ' сум';
}

// Format date/time relative (e.g., "2 минуты назад")
export function timeAgo(dateString) {
    if (!dateString) return '';

    const date = new Date(dateString);
    const now = new Date();
    const seconds = Math.floor((now - date) / 1000);

    if (seconds < 60) return 'только что';

    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) {
        return `${minutes} ${pluralize(minutes, 'минута', 'минуты', 'минут')} назад`;
    }

    const hours = Math.floor(minutes / 60);
    if (hours < 24) {
        return `${hours} ${pluralize(hours, 'час', 'часа', 'часов')} назад`;
    }

    const days = Math.floor(hours / 24);
    if (days < 7) {
        return `${days} ${pluralize(days, 'день', 'дня', 'дней')} назад`;
    }

    return date.toLocaleDateString('ru-RU');
}

// Pluralization helper
function pluralize(n, one, few, many) {
    n = Math.abs(n) % 100;
    const n1 = n % 10;
    if (n > 10 && n < 20) return many;
    if (n1 > 1 && n1 < 5) return few;
    if (n1 === 1) return one;
    return many;
}

// Show toast notification
export function toast(message, type = 'info', duration = 3000) {
    // Remove existing toasts
    document.querySelectorAll('.toast').forEach(t => t.remove());

    const toastEl = document.createElement('div');
    toastEl.className = `toast ${type}`;

    // Icon based on type
    const icons = {
        success: '✓',
        error: '✕',
        warning: '⚠',
        info: 'ℹ'
    };

    toastEl.innerHTML = `
        <span style="font-size: 16px; font-weight: 700;">${icons[type] || ''}</span>
        <span>${message}</span>
    `;

    document.body.appendChild(toastEl);

    setTimeout(() => {
        toastEl.style.animation = 'toastOut 0.3s ease-out';
        setTimeout(() => toastEl.remove(), 300);
    }, duration);
}

// Money helper
export const money = {
    format: formatPrice,

    // Convert sums to kopeks for API
    toKopeks(sums) {
        return Math.floor(Number(sums) * 100);
    },

    // Convert kopeks to sums
    toSums(kopeks) {
        return Number(kopeks) / 100;
    },

    // Validate amount
    isValid(amount) {
        return !isNaN(amount) && amount >= 0;
    }
};

// Debounce helper
export function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Loading state helpers
export function setLoading(element, isLoading) {
    if (isLoading) {
        element.classList.add('loading');
        element.disabled = true;
    } else {
        element.classList.remove('loading');
        element.disabled = false;
    }
}

// Confirm dialog
export function confirm(message) {
    return window.confirm(message);
}

// Parse query params
export function getQueryParams() {
    const params = new URLSearchParams(window.location.search);
    const result = {};
    for (const [key, value] of params) {
        result[key] = value;
    }
    return result;
}

// Escape HTML
export function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Copy to clipboard
export async function copyToClipboard(text) {
    try {
        if (navigator.clipboard) {
            await navigator.clipboard.writeText(text);
            toast('Скопировано!', 'success', 1500);
        } else {
            // Fallback for older browsers
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
            toast('Скопировано!', 'success', 1500);
        }
    } catch (err) {
        toast('Не удалось скопировать', 'error');
    }
}

// Image loading helper
export function loadImage(src) {
    return new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => resolve(img);
        img.onerror = reject;
        img.src = src;
    });
}

// File size formatter
export function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

// Validate image file
export function validateImageFile(file) {
    const validTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp'];
    const maxSize = 5 * 1024 * 1024; // 5MB

    if (!validTypes.includes(file.type)) {
        toast('Загрузите изображение (JPG, PNG, WebP)', 'error');
        return false;
    }

    if (file.size > maxSize) {
        toast(`Файл слишком большой (макс. ${formatFileSize(maxSize)})`, 'error');
        return false;
    }

    return true;
}

// Local storage helpers
export const storage = {
    get(key, defaultValue = null) {
        try {
            const item = localStorage.getItem(key);
            return item ? JSON.parse(item) : defaultValue;
        } catch {
            return defaultValue;
        }
    },

    set(key, value) {
        try {
            localStorage.setItem(key, JSON.stringify(value));
        } catch (err) {
            console.error('Storage error:', err);
        }
    },

    remove(key) {
        localStorage.removeItem(key);
    },

    clear() {
        localStorage.clear();
    }
};

// Device detection
export const device = {
    isMobile: /iPhone|iPad|iPod|Android/i.test(navigator.userAgent),
    isIOS: /iPhone|iPad|iPod/i.test(navigator.userAgent),
    isAndroid: /Android/i.test(navigator.userAgent),
    isTelegram: !!window.Telegram?.WebApp
};

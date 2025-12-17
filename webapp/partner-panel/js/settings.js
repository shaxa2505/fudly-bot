/* ================================================
   SETTINGS MODULE
   Store settings and preferences
   ================================================ */

import { storeAPI } from './api.js';
import { toast } from './utils.js';
import { state } from './state.js';

// Load settings
export async function loadSettings() {
    try {
        const storeInfo = await storeAPI.getInfo();
        renderSettings(storeInfo);
    } catch (error) {
        console.error('Error loading settings:', error);
        toast('Ошибка загрузки настроек', 'error');
    }
}

// Render settings
function renderSettings(storeInfo) {
    // Update store name input
    const storeNameInput = document.getElementById('settingsStoreName');
    if (storeNameInput) {
        storeNameInput.value = storeInfo.name || '';
    }

    // Update store description
    const descInput = document.getElementById('settingsStoreDescription');
    if (descInput) {
        descInput.value = storeInfo.description || '';
    }

    // Update phone
    const phoneInput = document.getElementById('settingsStorePhone');
    if (phoneInput) {
        phoneInput.value = storeInfo.phone || '';
    }

    // Update address
    const addressInput = document.getElementById('settingsStoreAddress');
    if (addressInput) {
        addressInput.value = storeInfo.address || '';
    }

    // Update working hours
    const hoursInput = document.getElementById('settingsWorkingHours');
    if (hoursInput) {
        hoursInput.value = storeInfo.working_hours || '';
    }

    // Update status toggle
    const statusToggle = document.getElementById('storeStatusToggle');
    if (statusToggle) {
        statusToggle.classList.toggle('active', storeInfo.is_open);
    }
}

// Save settings
export async function saveSettings() {
    try {
        const data = {
            name: document.getElementById('settingsStoreName')?.value,
            description: document.getElementById('settingsStoreDescription')?.value,
            phone: document.getElementById('settingsStorePhone')?.value,
            address: document.getElementById('settingsStoreAddress')?.value,
            working_hours: document.getElementById('settingsWorkingHours')?.value
        };

        await storeAPI.updateInfo(data);
        toast('Настройки сохранены', 'success');
    } catch (error) {
        console.error('Error saving settings:', error);
        toast('Ошибка сохранения', 'error');
    }
}

// Toggle store status
export async function toggleStoreStatus() {
    const toggle = document.getElementById('storeStatusToggle');
    const newStatus = !toggle.classList.contains('active');

    try {
        await storeAPI.updateStatus(newStatus);
        toggle.classList.toggle('active', newStatus);

        const statusText = newStatus ? 'открыт' : 'закрыт';
        toast(`Магазин ${statusText}`, 'success');
    } catch (error) {
        console.error('Error toggling status:', error);
        toast('Ошибка изменения статуса', 'error');
    }
}

// Make functions global
window.saveSettings = saveSettings;
window.toggleStoreStatus = toggleStoreStatus;

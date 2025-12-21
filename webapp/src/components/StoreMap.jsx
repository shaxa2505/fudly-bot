import React, { useState, useEffect, useRef } from 'react';
import './StoreMap.css';

/**
 * StoreMap Component
 *
 * Displays an interactive map with nearby stores using Leaflet.
 * Shows user location and store markers with distance info.
 */

// Leaflet map loaded from CDN
const LEAFLET_CDN = 'https://unpkg.com/leaflet@1.9.4/dist';

function StoreMap({ stores = [], userLocation = null, onStoreSelect, lang = 'uz' }) {
  const mapRef = useRef(null);
  const mapInstance = useRef(null);
  const [mapLoaded, setMapLoaded] = useState(false);
  const [error, setError] = useState(null);

  const t = (ru, uz) => (lang === 'uz' ? uz : ru);

  // Load Leaflet from CDN
  useEffect(() => {
    if (window.L) {
      setMapLoaded(true);
      return;
    }

    // Load CSS
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = `${LEAFLET_CDN}/leaflet.css`;
    document.head.appendChild(link);

    // Load JS
    const script = document.createElement('script');
    script.src = `${LEAFLET_CDN}/leaflet.js`;
    script.async = true;
    script.onload = () => setMapLoaded(true);
    script.onerror = () => setError('Failed to load map');
    document.body.appendChild(script);

    return () => {
      // Cleanup
      if (mapInstance.current) {
        mapInstance.current.remove();
        mapInstance.current = null;
      }
    };
  }, []);

  // Initialize map when Leaflet is loaded
  useEffect(() => {
    if (!mapLoaded || !mapRef.current || mapInstance.current) return;

    const L = window.L;

    // Default center (Tashkent)
    const defaultCenter = [41.2995, 69.2401];
    const center = userLocation
      ? [userLocation.latitude, userLocation.longitude]
      : defaultCenter;

    // Create map
    const map = L.map(mapRef.current, {
      center: center,
      zoom: 13,
      zoomControl: true,
      attributionControl: false,
    });

    // Add tile layer (OpenStreetMap)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
    }).addTo(map);

    mapInstance.current = map;

    // Add user marker if location available
    if (userLocation) {
      const userIcon = L.divIcon({
        className: 'user-marker',
        html: '<div class="user-marker-inner">YOU</div>',
        iconSize: [30, 30],
        iconAnchor: [15, 30],
      });

      L.marker([userLocation.latitude, userLocation.longitude], { icon: userIcon })
        .addTo(map)
        .bindPopup(t('Ваше местоположение', 'Sizning joylashuvingiz'));
    }

    // Add store markers
    stores.forEach((store) => {
      if (!store.latitude || !store.longitude) return;

      const storeIcon = L.divIcon({
        className: 'store-marker',
        html: `<div class="store-marker-inner">SHOP</div>`,
        iconSize: [36, 36],
        iconAnchor: [18, 36],
      });

      const distance = store.distance
        ? `${store.distance.toFixed(1)} ${t('км', 'km')}`
        : '';

      const popupContent = `
        <div class="store-popup">
          <strong>${store.name}</strong>
          <p>${store.address || ''}</p>
          ${distance ? `<p class="distance">Masofa: ${distance}</p>` : ''}
          <button class="popup-btn" onclick="window.selectStore(${store.id})">${t('Выбрать', 'Tanlash')}</button>
        </div>
      `;

      L.marker([store.latitude, store.longitude], { icon: storeIcon })
        .addTo(map)
        .bindPopup(popupContent);
    });

    // Global function for popup button
    window.selectStore = (storeId) => {
      if (onStoreSelect) {
        const store = stores.find(s => s.id === storeId);
        if (store) onStoreSelect(store);
      }
    };

    // Fit bounds if we have stores
    if (stores.length > 0) {
      const validStores = stores.filter(s => s.latitude && s.longitude);
      if (validStores.length > 0) {
        const bounds = L.latLngBounds(
          validStores.map(s => [s.latitude, s.longitude])
        );
        if (userLocation) {
          bounds.extend([userLocation.latitude, userLocation.longitude]);
        }
        map.fitBounds(bounds, { padding: [50, 50] });
      }
    }

    return () => {
      window.selectStore = undefined;
    };
  }, [mapLoaded, stores, userLocation, onStoreSelect, t]);

  // Update markers when stores change
  useEffect(() => {
    if (!mapInstance.current || !mapLoaded) return;

    const L = window.L;
    const map = mapInstance.current;

    // Clear existing store markers
    map.eachLayer((layer) => {
      if (layer instanceof L.Marker && layer.options.icon?.options?.className === 'store-marker') {
        map.removeLayer(layer);
      }
    });

    // Add new store markers
    stores.forEach((store) => {
      if (!store.latitude || !store.longitude) return;

      const storeIcon = L.divIcon({
        className: 'store-marker',
        html: `<div class="store-marker-inner">SHOP</div>`,
        iconSize: [36, 36],
        iconAnchor: [18, 36],
      });

      const distance = store.distance
        ? `${store.distance.toFixed(1)} ${t('км', 'km')}`
        : '';

      const popupContent = `
        <div class="store-popup">
          <strong>${store.name}</strong>
          <p>${store.address || ''}</p>
          ${distance ? `<p class="distance">Masofa: ${distance}</p>` : ''}
          <button class="popup-btn" onclick="window.selectStore(${store.id})">${t('Выбрать', 'Tanlash')}</button>
        </div>
      `;

      L.marker([store.latitude, store.longitude], { icon: storeIcon })
        .addTo(map)
        .bindPopup(popupContent);
    });
  }, [stores]);

  // Count stores with coordinates
  const storesWithCoords = stores.filter(s => s.latitude && s.longitude);

  if (error) {
    return (
      <div className="store-map-error">
        <p>{error}</p>
      </div>
    );
  }

  return (
    <div className="store-map-container">
      {!mapLoaded && (
        <div className="map-loading">
          <div className="map-spinner"></div>
          <p>{t('Загрузка карты...', 'Xarita yuklanmoqda...')}</p>
        </div>
      )}
      <div ref={mapRef} className="store-map" style={{ opacity: mapLoaded ? 1 : 0 }} />

      {/* No stores with coordinates message */}
      {mapLoaded && storesWithCoords.length === 0 && stores.length > 0 && (
        <div className="store-map-no-coords">
          <p>{t('Магазины не указали координаты', 'Do\'konlar koordinatalarini ko\'rsatmagan')}</p>
          <p className="store-map-hint">{t('Используйте список для просмотра', 'Ro\'yxatdan foydalaning')}</p>
        </div>
      )}

      {/* Store list overlay */}
      {stores.length > 0 && (
        <div className="store-list-overlay">
          <div className="store-list-header">
            <h3>{t('Ближайшие магазины', 'Yaqin do\'konlar')} ({stores.length})</h3>
          </div>
          <div className="store-list-scroll">
            {stores.slice(0, 5).map((store) => (
              <div
                key={store.id}
                className="store-list-item"
                onClick={() => {
                  if (mapInstance.current && store.latitude && store.longitude) {
                    mapInstance.current.flyTo([store.latitude, store.longitude], 15);
                  }
                  if (onStoreSelect) onStoreSelect(store);
                }}
              >
                <div className="store-list-icon">SHOP</div>
                <div className="store-list-info">
                  <h4>{store.name}</h4>
                  <p>{store.address || t('Адрес не указан', 'Manzil ko\'rsatilmagan')}</p>
                </div>
                {store.distance && (
                  <div className="store-list-distance">
                    {store.distance.toFixed(1)} {t('км', 'km')}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default StoreMap;

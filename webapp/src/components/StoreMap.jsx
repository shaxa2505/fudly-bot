import React, { useState, useEffect, useRef, useMemo } from 'react';
import './StoreMap.css';

/**
 * StoreMap Component
 *
 * Displays an interactive map with nearby stores using Leaflet.
 * Shows user location and store markers with distance info.
 */

// Leaflet map loaded from CDN
const LEAFLET_CDN = 'https://unpkg.com/leaflet@1.9.4/dist';

function StoreMap({
  stores = [],
  userLocation = null,
  fallbackCenter = null,
  cityLabel = '',
  locationLoading = false,
  onRequestLocation,
  onStoreSelect,
  lang = 'uz',
}) {
  const mapRef = useRef(null);
  const mapInstance = useRef(null);
  const storeLayerRef = useRef(null);
  const userMarkerRef = useRef(null);
  const userMovedRef = useRef(false);
  const [mapLoaded, setMapLoaded] = useState(false);
  const [error, setError] = useState(null);

  const t = (ru, uz) => (lang === 'uz' ? uz : ru);
  const toNumber = (value) => {
    if (value == null) return null;
    const raw = typeof value === 'string'
      ? value.replace(',', '.').trim()
      : value;
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? parsed : null;
  };
  const resolveCoords = (store) => {
    if (!store) return null;
    const lat = toNumber(
      store.latitude ??
      store.lat ??
      store.coordinates?.lat ??
      store.location?.lat ??
      store.geo?.lat ??
      store.coord_lat ??
      store.coordLat ??
      store.y
    );
    const lon = toNumber(
      store.longitude ??
      store.lon ??
      store.lng ??
      store.long ??
      store.coordinates?.lon ??
      store.location?.lon ??
      store.geo?.lon ??
      store.coord_lon ??
      store.coordLon ??
      store.x
    );
    if (lat == null || lon == null) return null;
    return { lat, lon };
  };
  const normalizedStores = stores.map((store) => {
    const coords = resolveCoords(store);
    if (!coords) return store;
    return { ...store, latitude: coords.lat, longitude: coords.lon };
  });
  const normalizedFallback = useMemo(() => {
    if (!fallbackCenter) return null;
    const lat = toNumber(fallbackCenter.lat ?? fallbackCenter.latitude);
    const lon = toNumber(fallbackCenter.lon ?? fallbackCenter.longitude);
    if (lat == null || lon == null) return null;
    return { lat, lon };
  }, [fallbackCenter]);
  const locationHint = cityLabel ? ` (${cityLabel})` : '';

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
      : normalizedFallback
        ? [normalizedFallback.lat, normalizedFallback.lon]
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
    storeLayerRef.current = L.layerGroup().addTo(map);
    userMovedRef.current = false;

    map.on('movestart', () => {
      userMovedRef.current = true;
    });

    setTimeout(() => {
      map.invalidateSize(true);
    }, 0);
  }, [mapLoaded, normalizedFallback, userLocation]);

  // Update store markers when stores change
  useEffect(() => {
    if (!mapInstance.current || !mapLoaded || !storeLayerRef.current) return;

    const L = window.L;
    const map = mapInstance.current;
    const layer = storeLayerRef.current;

    layer.clearLayers();

    const validStores = normalizedStores.filter(
      (store) => store.latitude != null && store.longitude != null
    );

    validStores.forEach((store) => {
      const storeIcon = L.divIcon({
        className: 'store-marker',
        html: `<div class="store-marker-inner">SHOP</div>`,
        iconSize: [36, 36],
        iconAnchor: [18, 36],
      });

      const distance = store.distance
        ? `${store.distance.toFixed(1)} ${t('km', 'km')}`
        : '';

      const popupContent = `
        <div class="store-popup">
          <strong>${store.name}</strong>
          <p>${store.address || ''}</p>
          ${distance ? `<p class="distance">Masofa: ${distance}</p>` : ''}
        </div>
      `;

      const marker = L.marker([store.latitude, store.longitude], { icon: storeIcon })
        .addTo(layer)
        .bindPopup(popupContent);

      marker.on('click', () => {
        if (onStoreSelect) {
          onStoreSelect(store);
        }
      });
    });

    if (!userMovedRef.current && validStores.length > 0) {
      const bounds = L.latLngBounds(validStores.map((s) => [s.latitude, s.longitude]));
      if (userLocation?.latitude != null && userLocation?.longitude != null) {
        bounds.extend([userLocation.latitude, userLocation.longitude]);
      }
      map.fitBounds(bounds, { padding: [50, 50] });
    }
  }, [normalizedStores, mapLoaded, onStoreSelect, t, userLocation]);

  // Update user marker when location changes
  useEffect(() => {
    if (!mapInstance.current || !mapLoaded) return;
    const L = window.L;
    const map = mapInstance.current;

    if (!userLocation?.latitude || !userLocation?.longitude) {
      if (userMarkerRef.current) {
        userMarkerRef.current.remove();
        userMarkerRef.current = null;
      }
      return;
    }

    const userIcon = L.divIcon({
      className: 'user-marker',
      html: '<div class="user-marker-inner">YOU</div>',
      iconSize: [30, 30],
      iconAnchor: [15, 30],
    });

    if (!userMarkerRef.current) {
      userMarkerRef.current = L.marker([userLocation.latitude, userLocation.longitude], { icon: userIcon })
        .addTo(map)
        .bindPopup(t('Your location', 'Sizning joylashuvingiz'));
    } else {
      userMarkerRef.current.setLatLng([userLocation.latitude, userLocation.longitude]);
    }

    userMovedRef.current = false;
    map.flyTo([userLocation.latitude, userLocation.longitude], 14, { duration: 0.6 });
  }, [mapLoaded, userLocation, t]);

  // Update map center for fallback city
  useEffect(() => {
    if (!mapInstance.current || !mapLoaded) return;
    if (userLocation?.latitude != null && userLocation?.longitude != null) return;
    if (!normalizedFallback) return;
    if (userMovedRef.current) return;

    mapInstance.current.flyTo([normalizedFallback.lat, normalizedFallback.lon], 12, { duration: 0.6 });
  }, [mapLoaded, normalizedFallback, userLocation]);

  // Count stores with coordinates
  const storesWithCoords = normalizedStores.filter(s => s.latitude != null && s.longitude != null);

  if (error) {
    return (
      <div className="store-map-error">
        <p>{error}</p>
      </div>
    );
  }

  return (
    <div className="store-map-container">
      {onRequestLocation && (
        <button
          className="store-map-locate"
          type="button"
          onClick={onRequestLocation}
          disabled={locationLoading}
          aria-label={t('Определить мое местоположение', "Joylashuvni aniqlash")}
          title={t('Определить мое местоположение', "Joylashuvni aniqlash")}
        >
          {locationLoading ? '...' : 'GPS'}
        </button>
      )}
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
          <p>{t('Магазины не указали координаты', `Do'konlar koordinatalarini ko'rsatmagan${locationHint}`)}</p>
          <p className="store-map-hint">{t('Используйте список для просмотра', "Ro'yxatdan foydalaning")}</p>
          {onRequestLocation && !userLocation && (
            <button
              type="button"
              className="store-map-cta"
              onClick={onRequestLocation}
              disabled={locationLoading}
            >
              {locationLoading ? t('Поиск...', 'Aniqlanmoqda...') : t('Найти меня', 'Joylashuvni aniqlash')}
            </button>
          )}
        </div>
      )}

      {/* Store list overlay */}
      {stores.length > 0 && (
        <div className="store-list-overlay">
          <div className="store-list-header">
            <h3>{t('Ближайшие магазины', 'Yaqin do\'konlar')} ({stores.length})</h3>
          </div>
          <div className="store-list-scroll">
            {normalizedStores.slice(0, 5).map((store) => (
              <div
                key={store.id}
                className="store-list-item"
                onClick={() => {
                  if (mapInstance.current && store.latitude != null && store.longitude != null) {
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

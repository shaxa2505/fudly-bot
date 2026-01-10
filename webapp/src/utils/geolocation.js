/**
 * Geolocation Utilities
 *
 * Handles browser and Telegram geolocation with fallback
 */

/**
 * Calculate distance between two coordinates using Haversine formula
 * @param {number} lat1 - Latitude of point 1
 * @param {number} lon1 - Longitude of point 1
 * @param {number} lat2 - Latitude of point 2
 * @param {number} lon2 - Longitude of point 2
 * @returns {number} Distance in kilometers
 */
export function calculateDistance(lat1, lon1, lat2, lon2) {
  const R = 6371; // Earth's radius in km
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

function toRad(deg) {
  return deg * (Math.PI / 180);
}

/**
 * Get user's current location
 * @returns {Promise<{latitude: number, longitude: number}>}
 */
export function getCurrentLocation() {
  return new Promise((resolve, reject) => {
    // Try Telegram WebApp location first
    if (window.Telegram?.WebApp?.requestLocation) {
      // Note: Telegram location requires bot to have location permission
      // This is a simplified version, actual implementation may vary
    }

    // Fallback to browser geolocation
    if (!navigator.geolocation) {
      reject(new Error('Geolocation not supported'));
      return;
    }

    navigator.geolocation.getCurrentPosition(
      (position) => {
        resolve({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracy: position.coords.accuracy,
        });
      },
      (error) => {
        let message = 'Location error';
        switch (error.code) {
          case error.PERMISSION_DENIED:
            message = 'Location permission denied';
            break;
          case error.POSITION_UNAVAILABLE:
            message = 'Location unavailable';
            break;
          case error.TIMEOUT:
            message = 'Location request timeout';
            break;
        }
        reject(new Error(message));
      },
      {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 60000, // Cache for 1 minute
      }
    );
  });
}

/**
 * Watch user's location with updates
 * @param {Function} onUpdate - Callback for location updates
 * @param {Function} onError - Callback for errors
 * @returns {number} Watch ID for clearing
 */
export function watchLocation(onUpdate, onError) {
  if (!navigator.geolocation) {
    onError?.(new Error('Geolocation not supported'));
    return null;
  }

  return navigator.geolocation.watchPosition(
    (position) => {
      onUpdate({
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
        accuracy: position.coords.accuracy,
      });
    },
    (error) => {
      onError?.(error);
    },
    {
      enableHighAccuracy: true,
      timeout: 15000,
      maximumAge: 30000,
    }
  );
}

/**
 * Stop watching location
 * @param {number} watchId - Watch ID from watchLocation
 */
export function stopWatchingLocation(watchId) {
  if (watchId && navigator.geolocation) {
    navigator.geolocation.clearWatch(watchId);
  }
}

/**
 * Add distance to stores list based on user location
 * @param {Array} stores - List of stores with latitude/longitude
 * @param {{latitude: number, longitude: number}} userLocation - User's location
 * @returns {Array} Stores with distance property, sorted by distance
 */
export function addDistanceToStores(stores, userLocation) {
  if (!userLocation || !stores) return stores;

  return stores
    .map((store) => ({
      ...store,
      distance:
        store.latitude && store.longitude
          ? calculateDistance(
              userLocation.latitude,
              userLocation.longitude,
              store.latitude,
              store.longitude
            )
          : null,
    }))
    .sort((a, b) => {
      if (a.distance === null) return 1;
      if (b.distance === null) return -1;
      return a.distance - b.distance;
    });
}

/**
 * Check if location services are available
 * @returns {boolean}
 */
export function isLocationAvailable() {
  return 'geolocation' in navigator;
}

/**
 * Get saved location from localStorage
 * @returns {{latitude: number, longitude: number} | null}
 */
export function getSavedLocation() {
  try {
    const saved = localStorage.getItem('fudly_user_location');
    if (saved) {
      const location = JSON.parse(saved);
      // Check if location is recent (within last hour)
      if (location.timestamp && Date.now() - location.timestamp < 3600000) {
        return {
          latitude: location.latitude,
          longitude: location.longitude,
        };
      }
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * Save location to localStorage
 * @param {{latitude: number, longitude: number}} location
 */
export function saveLocation(location) {
  try {
    localStorage.setItem(
      'fudly_user_location',
      JSON.stringify({
        ...location,
        timestamp: Date.now(),
      })
    );
  } catch {
    // Ignore storage errors
  }

  try {
    if (location?.latitude != null && location?.longitude != null) {
      const saved = localStorage.getItem('fudly_location');
      const base = saved ? JSON.parse(saved) : {};
      const next = {
        ...base,
        coordinates: { lat: location.latitude, lon: location.longitude },
      };
      localStorage.setItem('fudly_location', JSON.stringify(next));
    }
  } catch {
    // Ignore storage errors
  }
}

export default {
  calculateDistance,
  getCurrentLocation,
  watchLocation,
  stopWatchingLocation,
  addDistanceToStores,
  isLocationAvailable,
  getSavedLocation,
  saveLocation,
};

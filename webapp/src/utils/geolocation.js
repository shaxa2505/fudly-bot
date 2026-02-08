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

const parseLocationCandidate = (candidate) => {
  if (!candidate) return null;
  const source = candidate.coords || candidate;
  const latitude = source.latitude ?? source.lat;
  const longitude = source.longitude ?? source.lon ?? source.lng;
  if (latitude == null || longitude == null) return null;
  return {
    latitude,
    longitude,
    accuracy: source.accuracy,
  };
};

const normalizeAccuracy = (candidate) => {
  const value = candidate?.accuracy;
  return Number.isFinite(value) ? value : Number.POSITIVE_INFINITY;
};

const pickBestLocation = (first, second) => {
  if (!first) return second || null;
  if (!second) return first;
  return normalizeAccuracy(second) < normalizeAccuracy(first) ? second : first;
};

const isAccurateEnough = (candidate, minAccuracy) => {
  if (!candidate) return false;
  if (!Number.isFinite(minAccuracy)) return true;
  const accuracy = candidate.accuracy;
  if (!Number.isFinite(accuracy)) return false;
  return accuracy <= minAccuracy;
};

const waitForTelegramLocation = async (telegram, timeoutMs) => {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const parsed = parseLocationCandidate(telegram?.location);
    if (parsed) return parsed;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  return null;
};

const requestTelegramLocation = async ({ timeout = 8000 } = {}) => {
  const telegram = window.Telegram?.WebApp;
  if (!telegram?.requestLocation) return null;
  try {
    const maybePromise = telegram.requestLocation();
    const resolved = await Promise.race([
      Promise.resolve(maybePromise),
      new Promise((resolve) => setTimeout(() => resolve(null), timeout)),
    ]);
    return (
      parseLocationCandidate(resolved) ||
      parseLocationCandidate(telegram.location) ||
      await waitForTelegramLocation(telegram, timeout)
    );
  } catch {
    return null;
  }
};

const requestBrowserLocation = (options = {}) => {
  const {
    enableHighAccuracy = true,
    timeout = 10000,
    maximumAge = 60000,
  } = options;
  return new Promise((resolve, reject) => {
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
        reject(error);
      },
      {
        enableHighAccuracy,
        timeout,
        maximumAge,
      }
    );
  });
};

const requestBrowserLocationWithWatch = (options = {}) => {
  const {
    enableHighAccuracy = true,
    timeout = 12000,
    maximumAge = 0,
    minAccuracy,
  } = options;

  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error('Geolocation not supported'));
      return;
    }

    let best = null;
    let resolved = false;
    let watchId = null;

    const finalize = (value, error) => {
      if (resolved) return;
      resolved = true;
      if (watchId != null) {
        navigator.geolocation.clearWatch(watchId);
      }
      if (value) {
        resolve(value);
      } else {
        reject(error || new Error('Geolocation failed'));
      }
    };

    const timer = setTimeout(() => {
      clearTimeout(timer);
      if (best) {
        finalize(best);
      } else {
        finalize(null, new Error('Geolocation timeout'));
      }
    }, timeout);

    watchId = navigator.geolocation.watchPosition(
      (position) => {
        const candidate = {
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracy: position.coords.accuracy,
        };
        best = pickBestLocation(best, candidate);
        if (isAccurateEnough(candidate, minAccuracy)) {
          clearTimeout(timer);
          finalize(candidate);
        }
      },
      (error) => {
        clearTimeout(timer);
        if (best) {
          finalize(best);
        } else {
          finalize(null, error);
        }
      },
      {
        enableHighAccuracy,
        timeout: Math.max(4000, Math.min(timeout, 15000)),
        maximumAge,
      }
    );
  });
};

/**
 * Get user's current location
 * @returns {Promise<{latitude: number, longitude: number}>}
 */
export function getCurrentLocation(options = {}) {
  return requestBrowserLocation(options);
}

export async function getPreferredLocation(options = {}) {
  const {
    preferTelegram = true,
    enableHighAccuracy = true,
    timeout = 10000,
    maximumAge = 60000,
    minAccuracy,
    retryOnLowAccuracy = false,
    highAccuracyTimeout = 15000,
    highAccuracyMaximumAge = 0,
  } = options;

  let telegramLocation = null;
  if (preferTelegram) {
    telegramLocation = await requestTelegramLocation({ timeout });
    if (telegramLocation && isAccurateEnough(telegramLocation, minAccuracy)) {
      return telegramLocation;
    }
  }

  let primary = null;
  try {
    primary = await requestBrowserLocation({
      enableHighAccuracy,
      timeout,
      maximumAge,
    });
  } catch (error) {
    if (telegramLocation) return telegramLocation;
    throw error;
  }

  let best = pickBestLocation(telegramLocation, primary);

  if (retryOnLowAccuracy && !isAccurateEnough(best, minAccuracy)) {
    try {
      const refined = await requestBrowserLocationWithWatch({
        enableHighAccuracy: true,
        timeout: highAccuracyTimeout,
        maximumAge: highAccuracyMaximumAge,
        minAccuracy,
      });
      best = pickBestLocation(best, refined);
    } catch {
      // Keep the best known result.
    }
  }

  return best || primary;
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
  getPreferredLocation,
  watchLocation,
  stopWatchingLocation,
  addDistanceToStores,
  isLocationAvailable,
  getSavedLocation,
  saveLocation,
};

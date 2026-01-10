import { useState, useEffect, useCallback, useRef } from 'react';
import { normalizeLocationName } from '../utils/cityUtils';

const STORAGE_KEY = 'fudly_location';

const DEFAULT_LOCATION = {
  city: '',
  address: '',
  coordinates: null,
  region: '',
  district: '',
};

/**
 * Hook for managing user location with geolocation support
 */
export function useUserLocation() {
  const [location, setLocation] = useState(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      return saved ? JSON.parse(saved) : DEFAULT_LOCATION;
    } catch {
      return DEFAULT_LOCATION;
    }
  });

  const [isLocating, setIsLocating] = useState(false);
  const [error, setError] = useState('');
  const autoLocationAttempted = useRef(false);

  // Extract city name without country
  const cityName = location.city
    ? normalizeLocationName(location.city.split(',')[0].trim())
    : '';

  // Check if we have precise location (coordinates or address)
  const hasPreciseLocation = Boolean(location.coordinates || location.address);

  // Save to localStorage when location changes
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(location));
  }, [location]);

  // Reverse geocode coordinates to address
  const reverseGeocode = useCallback(async (lat, lon, isAuto = false) => {
    try {
      const response = await fetch(
        `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat}&lon=${lon}&accept-language=uz`,
        { headers: { 'User-Agent': 'FudlyApp/1.0' } }
      );

      if (!response.ok) throw new Error('Geo lookup failed');

      const data = await response.json();

      const city = normalizeLocationName(
        data.address?.city || data.address?.town || data.address?.village || ''
      );
      const state = normalizeLocationName(data.address?.state || data.address?.region || '');
      const district = normalizeLocationName(
        data.address?.county || data.address?.city_district || data.address?.suburb || ''
      );
      const primaryCity = city || state || '';
      const normalizedCity = primaryCity
        ? (primaryCity.includes("O'zbekiston")
          ? primaryCity
          : `${primaryCity}, O'zbekiston`)
        : '';

      setLocation({
        city: normalizedCity,
        address: data.display_name || '',
        coordinates: { lat, lon },
        region: state,
        district,
      });

      setError('');
      return true;
    } catch (err) {
      console.error('Reverse geocode error:', err);
      setError('Manzilni aniqlab bo\'lmadi');
      return false;
    } finally {
      setIsLocating(false);
    }
  }, []);

  // Detect location using browser geolocation
  const detectLocation = useCallback(() => {
    if (!navigator.geolocation) {
      setError('Qurilmada geolokatsiya qo\'llab-quvvatlanmaydi');
      return;
    }

    setIsLocating(true);
    setError('');

    navigator.geolocation.getCurrentPosition(
      (position) => {
        const { latitude, longitude } = position.coords;
        reverseGeocode(latitude, longitude);
      },
      (err) => {
        console.error('Geolocation error:', err);
        setIsLocating(false);

        if (err.code === err.PERMISSION_DENIED) {
          setError('Geolokatsiyaga ruxsat berilmadi. Brauzer sozlamalaridan ruxsat bering.');
        } else if (err.code === err.TIMEOUT) {
          setError('Joylashuvni aniqlash vaqti tugadi. Qayta urinib ko\'ring.');
        } else {
          setError('Geolokatsiyani olish imkonsiz');
        }
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
    );
  }, [reverseGeocode]);

  // Auto-detect location on first load
  useEffect(() => {
    if (autoLocationAttempted.current) return;
    autoLocationAttempted.current = true;

    // If we already have address/coordinates, don't auto-detect
    if (location.address || location.coordinates) return;

    // Try to detect automatically
    if (navigator.geolocation) {
      setIsLocating(true);
      navigator.geolocation.getCurrentPosition(
        (position) => {
          const { latitude, longitude } = position.coords;
          reverseGeocode(latitude, longitude, true);
        },
        (err) => {
          console.log('Auto-geolocation denied or failed:', err.message);
          setIsLocating(false);
        },
        { enableHighAccuracy: true, timeout: 10000, maximumAge: 300000 }
      );
    }
  }, []); // Only run once on mount

  // Update location manually
  const updateLocation = useCallback((newCity, newAddress = '') => {
    setLocation(prev => ({
      city: normalizeLocationName(newCity.trim()) || DEFAULT_LOCATION.city,
      address: newAddress.trim(),
      coordinates: newAddress.trim() ? prev.coordinates : null,
      region: prev.region,
      district: prev.district,
    }));
    setError('');
  }, []);

  // Reset to default
  const resetLocation = useCallback(() => {
    setLocation(DEFAULT_LOCATION);
    setError('');
  }, []);

  return {
    location,
    cityName,
    hasPreciseLocation,
    isLocating,
    error,
    detectLocation,
    updateLocation,
    resetLocation,
    setError,
  };
}

export default useUserLocation;

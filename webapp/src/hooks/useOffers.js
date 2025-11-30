import { useState, useEffect, useCallback, useRef } from 'react';
import api from '../api/client';

// Transliteration map for cities: Latin -> Cyrillic (for API)
const CITY_TO_CYRILLIC = {
  'toshkent': 'Ташкент',
  'tashkent': 'Ташкент',
  'samarqand': 'Самарканд',
  'samarkand': 'Самарканд',
  'buxoro': 'Бухара',
  'bukhara': 'Бухара',
  "farg'ona": 'Фергана',
  'fergana': 'Фергана',
  'andijon': 'Андижан',
  'andijan': 'Андижан',
  'namangan': 'Наманган',
  'navoiy': 'Навои',
  'navoi': 'Навои',
  'qarshi': 'Карши',
  'karshi': 'Карши',
  'nukus': 'Нукус',
  'urganch': 'Ургенч',
  'urgench': 'Ургенч',
  'jizzax': 'Джизак',
  'jizzakh': 'Джизак',
  'termiz': 'Термез',
  'termez': 'Термез',
  'guliston': 'Гулистан',
  'gulistan': 'Гулистан',
  'chirchiq': 'Чирчик',
  'chirchik': 'Чирчик',
  "kattaqo'rg'on": 'Каттакурган',
  'kattakurgan': 'Каттакурган',
  'kattaqurgan': 'Каттакурган',
  'olmaliq': 'Алмалык',
  'angren': 'Ангрен',
  'bekobod': 'Бекабад',
  'shahrisabz': 'Шахрисабз',
  "marg'ilon": 'Маргилан',
  "qo'qon": 'Коканд',
  'xiva': 'Хива',
  'khiva': 'Хива',
};

// Transliterate city to Cyrillic for API
const transliterateCity = (city) => {
  if (!city) return city;
  const cityLower = city.toLowerCase().trim();
  return CITY_TO_CYRILLIC[cityLower] || city;
};

/**
 * Hook for loading offers with infinite scroll
 * @param {Object} options - Configuration options
 * @param {string} options.city - City name for filtering
 * @param {string} options.category - Category filter
 * @param {string} options.searchQuery - Search query
 * @param {number} options.limit - Items per page
 */
export function useOffers({
  city = '',  // Empty = all cities by default for better UX
  category = 'all',
  searchQuery = '',
  limit = 20,
} = {}) {
  const [offers, setOffers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [offset, setOffset] = useState(0);
  const [showingAllCities, setShowingAllCities] = useState(false);
  const [error, setError] = useState(null);

  // Ref to track if currently loading
  const loadingRef = useRef(false);

  // Transliterate city for API
  const cityForApi = transliterateCity(city);

  // Load offers function
  const loadOffers = useCallback(async (reset = false, forceAllCities = false) => {
    // Prevent duplicate requests
    if (loadingRef.current) return;

    loadingRef.current = true;
    setLoading(true);
    setError(null);

    try {
      const currentOffset = reset ? 0 : offset;
      const params = {
        limit,
        offset: currentOffset,
      };

      // Filter by city unless showing all
      if (!forceAllCities && !showingAllCities) {
        params.city = cityForApi;
      }

      // Add category filter
      if (category && category !== 'all') {
        params.category = category;
      }

      // Add search query
      if (searchQuery.trim()) {
        params.search = searchQuery.trim();
      }

      const data = await api.getOffers(params);

      // If city is empty on first load, show all cities
      if (reset && (!data || data.length === 0) && !forceAllCities && !showingAllCities) {
        setShowingAllCities(true);
        loadingRef.current = false;
        setLoading(false);
        return loadOffers(true, true);
      }

      if (reset) {
        setOffers(data || []);
        setOffset(limit);
        if (forceAllCities) setShowingAllCities(true);
      } else {
        setOffers(prev => [...prev, ...(data || [])]);
        setOffset(prev => prev + limit);
      }

      setHasMore((data?.length || 0) === limit);
    } catch (err) {
      console.error('Error loading offers:', err);
      setError(err.message || 'Failed to load offers');
    } finally {
      setLoading(false);
      loadingRef.current = false;
    }
  }, [cityForApi, category, searchQuery, offset, limit, showingAllCities]);

  // Reset and reload when filters change
  useEffect(() => {
    setShowingAllCities(false);
    setOffset(0);

    const timer = setTimeout(() => {
      loadOffers(true);
    }, searchQuery ? 500 : 0); // Debounce search

    return () => clearTimeout(timer);
  }, [category, searchQuery, cityForApi]); // Note: loadOffers intentionally excluded

  // Load more function for infinite scroll
  const loadMore = useCallback(() => {
    if (hasMore && !loading) {
      loadOffers(false);
    }
  }, [hasMore, loading, loadOffers]);

  // Refresh function
  const refresh = useCallback(() => {
    setShowingAllCities(false);
    setOffset(0);
    loadOffers(true);
  }, [loadOffers]);

  return {
    offers,
    loading,
    hasMore,
    error,
    showingAllCities,
    loadMore,
    refresh,
  };
}

export default useOffers;

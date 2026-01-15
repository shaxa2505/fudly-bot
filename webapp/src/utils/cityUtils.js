/**
 * City utilities - shared city name translations and helpers
 */

// Latin to Cyrillic city name translations for API compatibility
export const CITY_TO_CYRILLIC = {
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
}


// Latin to Cyrillic (alternative format used in StoresPage)
export const CITY_TRANSLATIONS = {
  'Toshkent': 'Ташкент',
  'Samarqand': 'Самарканд',
  'Buxoro': 'Бухара',
  'Namangan': 'Наманган',
  'Andijon': 'Андижан',
  "Farg'ona": 'Фергана',
  'Nukus': 'Нукус',
  'Qarshi': 'Карши',
  'Jizzax': 'Джизак',
  'Urganch': 'Ургенч',
  'Navoiy': 'Навои',
  'Termiz': 'Термез',
  "Qo'qon": 'Коканд',
  "Marg'ilon": 'Маргилан',
  'Chirchiq': 'Чирчик',
  'Olmaliq': 'Алмалык',
  'Angren': 'Ангрен',
}

const LOCATION_SUFFIXES = [
  'shahri',
  'shahar',
  'shahr',
  'tumani',
  'tuman',
  'viloyati',
  'viloyat',
  'region',
  'district',
  'province',
  'oblast',
  'oblasti',
  'город',
  'район',
  'область',
  'шахри',
  'шахар',
  'тумани',
  'туман',
  'вилояти',
]

export const normalizeLocationName = (value) => {
  if (!value) return ''
  let cleaned = String(value).trim()
  cleaned = cleaned.replace(/\s*\([^)]*\)/g, '')
  const suffixPattern = new RegExp(`\\s+(?:${LOCATION_SUFFIXES.join('|')})\\b`, 'gi')
  cleaned = cleaned.replace(suffixPattern, '')
  cleaned = cleaned.replace(/\s*,\s*/g, ', ')
  cleaned = cleaned.replace(/\s{2,}/g, ' ')
  cleaned = cleaned.replace(/[,\\s]+$/g, '')
  return cleaned.trim()
}


/**
 * Transliterate city name from Latin to Cyrillic for API calls
 * @param {string} city - City name in Latin script
 * @returns {string} City name in Cyrillic or original if not found
 */
export const transliterateCity = (city) => {
  if (!city) return city
  const normalized = normalizeLocationName(city)
  const cityLower = normalized.toLowerCase().trim()
  return CITY_TO_CYRILLIC[cityLower] || normalized
}

/**
 * Get Cyrillic city name from location string
 * @param {string} cityString - City string like "Toshkent, O'zbekiston"
 * @returns {string} Cyrillic city name for API
 */
export const getCyrillicCity = (cityString) => {
  if (!cityString) return ''  // Empty = all cities
  const cityLatin = normalizeLocationName(cityString.split(',')[0]?.trim())
  return CITY_TRANSLATIONS[cityLatin] || transliterateCity(cityLatin) || cityLatin
}

/**
 * Get Latin city name from location object
 * @param {Object} location - Location object with city property
 * @returns {string} Latin city name for display
 */
export const getLatinCity = (location) => {
  if (!location?.city) return ''
  return normalizeLocationName(location.city.split(',')[0]?.trim() || '')
}

/**
 * Default location for the app
 */
export const DEFAULT_LOCATION = {
  city: '',
  address: '',
  coordinates: null,
  region: '',
  district: '',
}

/**
 * Get saved location from localStorage
 * @returns {Object} Location object
 */
export const getSavedLocation = () => {
  try {
    const saved = localStorage.getItem('fudly_location')
    const baseLocation = saved ? JSON.parse(saved) : {}
    let location = {
      ...DEFAULT_LOCATION,
      ...baseLocation,
      city: normalizeLocationName(baseLocation.city || DEFAULT_LOCATION.city),
      region: normalizeLocationName(baseLocation.region || DEFAULT_LOCATION.region),
      district: normalizeLocationName(baseLocation.district || DEFAULT_LOCATION.district),
    }

    const geoSaved = localStorage.getItem('fudly_user_location')
    if (geoSaved) {
      const geo = JSON.parse(geoSaved)
      const isFresh = geo.timestamp && Date.now() - geo.timestamp < 86400000 // 24h freshness for coordinates
      if (
        isFresh &&
        (!location.coordinates ||
          location.coordinates.lat == null ||
          location.coordinates.lon == null) &&
        geo.latitude != null &&
        geo.longitude != null
      ) {
        location = {
          ...location,
          coordinates: { lat: geo.latitude, lon: geo.longitude },
        }
      }
    }

    return location
  } catch {
    return DEFAULT_LOCATION
  }
}

/**
 * Save location to localStorage
 * @param {Object} location - Location object to save
 */
export const saveLocation = (location) => {
  try {
    localStorage.setItem('fudly_location', JSON.stringify(location))
  } catch (e) {
    console.error('Failed to save location:', e)
  }
}

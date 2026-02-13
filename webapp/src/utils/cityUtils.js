/**
 * City utilities - shared city name translations and helpers
 */

// Latin to Cyrillic city name translations for API compatibility
export const CITY_TO_CYRILLIC = {
  'toshkent': '\u0422\u0430\u0448\u043a\u0435\u043d\u0442',
  'tashkent': '\u0422\u0430\u0448\u043a\u0435\u043d\u0442',
  'samarqand': '\u0421\u0430\u043c\u0430\u0440\u043a\u0430\u043d\u0434',
  'samarkand': '\u0421\u0430\u043c\u0430\u0440\u043a\u0430\u043d\u0434',
  'buxoro': '\u0411\u0443\u0445\u0430\u0440\u0430',
  'bukhara': '\u0411\u0443\u0445\u0430\u0440\u0430',
  "farg'ona": '\u0424\u0435\u0440\u0433\u0430\u043d\u0430',
  'fargona': '\u0424\u0435\u0440\u0433\u0430\u043d\u0430',
  'fergana': '\u0424\u0435\u0440\u0433\u0430\u043d\u0430',
  'andijon': '\u0410\u043d\u0434\u0438\u0436\u0430\u043d',
  'andijan': '\u0410\u043d\u0434\u0438\u0436\u0430\u043d',
  'namangan': '\u041d\u0430\u043c\u0430\u043d\u0433\u0430\u043d',
  'navoiy': '\u041d\u0430\u0432\u043e\u0438',
  'navoi': '\u041d\u0430\u0432\u043e\u0438',
  'qarshi': '\u041a\u0430\u0440\u0448\u0438',
  'karshi': '\u041a\u0430\u0440\u0448\u0438',
  'nukus': '\u041d\u0443\u043a\u0443\u0441',
  'urganch': '\u0423\u0440\u0433\u0435\u043d\u0447',
  'urgench': '\u0423\u0440\u0433\u0435\u043d\u0447',
  'jizzax': '\u0414\u0436\u0438\u0437\u0430\u043a',
  'jizzakh': '\u0414\u0436\u0438\u0437\u0430\u043a',
  'termiz': '\u0422\u0435\u0440\u043c\u0435\u0437',
  'termez': '\u0422\u0435\u0440\u043c\u0435\u0437',
  'guliston': '\u0413\u0443\u043b\u0438\u0441\u0442\u0430\u043d',
  'gulistan': '\u0413\u0443\u043b\u0438\u0441\u0442\u0430\u043d',
  'chirchiq': '\u0427\u0438\u0440\u0447\u0438\u043a',
  'chirchik': '\u0427\u0438\u0440\u0447\u0438\u043a',
  "kattaqo'rg'on": '\u041a\u0430\u0442\u0442\u0430\u043a\u0443\u0440\u0433\u0430\u043d',
  'kattakurgan': '\u041a\u0430\u0442\u0442\u0430\u043a\u0443\u0440\u0433\u0430\u043d',
  'kattaqurgan': '\u041a\u0430\u0442\u0442\u0430\u043a\u0443\u0440\u0433\u0430\u043d',
  'olmaliq': '\u0410\u043b\u043c\u0430\u043b\u044b\u043a',
  'angren': '\u0410\u043d\u0433\u0440\u0435\u043d',
  'bekobod': '\u0411\u0435\u043a\u0430\u0431\u0430\u0434',
  'bekabad': '\u0411\u0435\u043a\u0430\u0431\u0430\u0434',
  'shahrisabz': '\u0428\u0430\u0445\u0440\u0438\u0441\u0430\u0431\u0437',
  "marg'ilon": '\u041c\u0430\u0440\u0433\u0438\u043b\u0430\u043d',
  'margilan': '\u041c\u0430\u0440\u0433\u0438\u043b\u0430\u043d',
  "qo'qon": '\u041a\u043e\u043a\u0430\u043d\u0434',
  'qoqon': '\u041a\u043e\u043a\u0430\u043d\u0434',
  'kokand': '\u041a\u043e\u043a\u0430\u043d\u0434',
  'xiva': '\u0425\u0438\u0432\u0430',
  'khiva': '\u0425\u0438\u0432\u0430',
}


// Latin to Cyrillic (alternative format used in StoresPage)
export const CITY_TRANSLATIONS = {
  'Toshkent': '\u0422\u0430\u0448\u043a\u0435\u043d\u0442',
  'Tashkent': '\u0422\u0430\u0448\u043a\u0435\u043d\u0442',
  'Samarqand': '\u0421\u0430\u043c\u0430\u0440\u043a\u0430\u043d\u0434',
  'Samarkand': '\u0421\u0430\u043c\u0430\u0440\u043a\u0430\u043d\u0434',
  'Buxoro': '\u0411\u0443\u0445\u0430\u0440\u0430',
  'Bukhara': '\u0411\u0443\u0445\u0430\u0440\u0430',
  "Farg'ona": '\u0424\u0435\u0440\u0433\u0430\u043d\u0430',
  'Fargona': '\u0424\u0435\u0440\u0433\u0430\u043d\u0430',
  'Fergana': '\u0424\u0435\u0440\u0433\u0430\u043d\u0430',
  'Namangan': '\u041d\u0430\u043c\u0430\u043d\u0433\u0430\u043d',
  'Andijon': '\u0410\u043d\u0434\u0438\u0436\u0430\u043d',
  'Andijan': '\u0410\u043d\u0434\u0438\u0436\u0430\u043d',
  'Navoiy': '\u041d\u0430\u0432\u043e\u0438',
  'Navoi': '\u041d\u0430\u0432\u043e\u0438',
  'Qarshi': '\u041a\u0430\u0440\u0448\u0438',
  'Karshi': '\u041a\u0430\u0440\u0448\u0438',
  'Nukus': '\u041d\u0443\u043a\u0443\u0441',
  'Urganch': '\u0423\u0440\u0433\u0435\u043d\u0447',
  'Urgench': '\u0423\u0440\u0433\u0435\u043d\u0447',
  'Jizzax': '\u0414\u0436\u0438\u0437\u0430\u043a',
  'Jizzakh': '\u0414\u0436\u0438\u0437\u0430\u043a',
  'Termiz': '\u0422\u0435\u0440\u043c\u0435\u0437',
  'Termez': '\u0422\u0435\u0440\u043c\u0435\u0437',
  'Guliston': '\u0413\u0443\u043b\u0438\u0441\u0442\u0430\u043d',
  'Gulistan': '\u0413\u0443\u043b\u0438\u0441\u0442\u0430\u043d',
  'Chirchiq': '\u0427\u0438\u0440\u0447\u0438\u043a',
  'Chirchik': '\u0427\u0438\u0440\u0447\u0438\u043a',
  "Kattaqo'rg'on": '\u041a\u0430\u0442\u0442\u0430\u043a\u0443\u0440\u0433\u0430\u043d',
  'Kattakurgan': '\u041a\u0430\u0442\u0442\u0430\u043a\u0443\u0440\u0433\u0430\u043d',
  'Kattaqurgan': '\u041a\u0430\u0442\u0442\u0430\u043a\u0443\u0440\u0433\u0430\u043d',
  'Olmaliq': '\u0410\u043b\u043c\u0430\u043b\u044b\u043a',
  'Angren': '\u0410\u043d\u0433\u0440\u0435\u043d',
  'Bekobod': '\u0411\u0435\u043a\u0430\u0431\u0430\u0434',
  'Bekabad': '\u0411\u0435\u043a\u0430\u0431\u0430\u0434',
  'Shahrisabz': '\u0428\u0430\u0445\u0440\u0438\u0441\u0430\u0431\u0437',
  "Marg'ilon": '\u041c\u0430\u0440\u0433\u0438\u043b\u0430\u043d',
  'Margilan': '\u041c\u0430\u0440\u0433\u0438\u043b\u0430\u043d',
  "Qo'qon": '\u041a\u043e\u043a\u0430\u043d\u0434',
  'Qoqon': '\u041a\u043e\u043a\u0430\u043d\u0434',
  'Kokand': '\u041a\u043e\u043a\u0430\u043d\u0434',
  'Xiva': '\u0425\u0438\u0432\u0430',
  'Khiva': '\u0425\u0438\u0432\u0430',
}

const CYRILLIC_RE = /[\u0400-\u04FF]/
const LATIN_RE = /[A-Za-z]/
const APOSTROPHE_RE = /[\u2018\u2019\u02BB\u02BC\u2032\u2035\u00B4\u0060]/g
const CITY_KEY_RE = /[\s'’`,.\-]+/g
const HOUSE_NUMBER_RE = /^\d+[A-Za-z\u0400-\u04FF/-]*$/
const BLOCK_PART_RE = /(?:daha(?:si)?|daxasi|\u0434\u0430\u0445\u0430\u0441\u0438|\u043c\u0430\u0441\u0441\u0438\u0432|kvartal|\u043a\u0432\u0430\u0440\u0442\u0430\u043b|[c\u0441\u0446]\s*[-/]?\s*\d+)/i
const ROAD_PART_RE = /(?:ko['’`]?chasi|kochasi|\u0443\u043b\u0438\u0446\u0430|\u0443\u043b\.?|street|road|avenue|prospekt|\u043f\u0440\u043e\u0441\u043f\u0435\u043a\u0442|yo['’`]?li|yoli|shoh|\u0448\u043e\u0445)/i
const MAX_COMPACT_ADDRESS_LENGTH = 34

const hasCyrillic = (value) => CYRILLIC_RE.test(String(value || ''))
const hasLatin = (value) => LATIN_RE.test(String(value || ''))
const normalizeApostrophes = (value) => String(value || '').replace(APOSTROPHE_RE, "'")

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
  let cleaned = normalizeApostrophes(String(value).trim())
  cleaned = cleaned.replace(/\s*\([^)]*\)/g, '')
  const suffixPattern = new RegExp(`\\s+(?:${LOCATION_SUFFIXES.join('|')})\\b`, 'gi')
  cleaned = cleaned.replace(suffixPattern, '')
  cleaned = cleaned.replace(/\s*,\s*/g, ', ')
  cleaned = cleaned.replace(/\s{2,}/g, ' ')
  cleaned = cleaned.replace(/[,\\s]+$/g, '')
  return cleaned.trim()
}

export const buildCitySearchKey = (value) => (
  normalizeLocationName(value)
    .toLowerCase()
    .replace(CITY_KEY_RE, '')
)

const CITY_QUERY_ALIASES = {
  [buildCitySearchKey('Samarqand')]: 'Samarqand',
  [buildCitySearchKey('Samarkand')]: 'Samarqand',
  [buildCitySearchKey("Kattaqo'rg'on")]: "Kattaqo'rg'on",
  [buildCitySearchKey('Kattaqurgan')]: "Kattaqo'rg'on",
  [buildCitySearchKey('Kattakurgan')]: "Kattaqo'rg'on",
  [buildCitySearchKey('Kattaqorgon')]: "Kattaqo'rg'on",
  [buildCitySearchKey('Kattaqorqon')]: "Kattaqo'rg'on",
}

export const normalizeCityQuery = (value) => {
  const normalized = normalizeLocationName(value)
  if (!normalized) return ''
  const key = buildCitySearchKey(normalized)
  return CITY_QUERY_ALIASES[key] || ''
}

const normalizeAddressPart = (value) => (
  normalizeApostrophes(String(value || ''))
    .replace(/\s+/g, ' ')
    .trim()
)

const stripBlockDecorations = (value) => (
  normalizeAddressPart(value)
    .replace(/\(\s*[c\u0441\u0446]\s*[-/]?\s*\d+[A-Za-z\u0400-\u04FF]?\s*\)/gi, '')
    .replace(/(?:daha(?:si)?|daxasi|\u0434\u0430\u0445\u0430\u0441\u0438|\u043c\u0430\u0441\u0441\u0438\u0432|kvartal|\u043a\u0432\u0430\u0440\u0442\u0430\u043b)/gi, '')
    .replace(/\s{2,}/g, ' ')
    .trim()
)

const looksLikeHouseNumber = (value) => (
  HOUSE_NUMBER_RE.test(String(value || '').replace(/\s+/g, ''))
)

const isBlockLikePart = (value) => BLOCK_PART_RE.test(String(value || ''))

const truncateCompactLabel = (value) => {
  const normalized = normalizeAddressPart(value)
  if (normalized.length <= MAX_COMPACT_ADDRESS_LENGTH) return normalized
  return `${normalized.slice(0, MAX_COMPACT_ADDRESS_LENGTH - 3).trim()}...`
}

const pickByPreferredScript = (values, preferLatin) => {
  if (!values.length) return ''
  if (preferLatin) {
    const latinOnly = values.find((item) => hasLatin(item) && !hasCyrillic(item))
    if (latinOnly) return latinOnly
    const latinMixed = values.find((item) => hasLatin(item))
    if (latinMixed) return latinMixed
  } else {
    const cyrOnly = values.find((item) => hasCyrillic(item) && !hasLatin(item))
    if (cyrOnly) return cyrOnly
    const cyrMixed = values.find((item) => hasCyrillic(item))
    if (cyrMixed) return cyrMixed
  }
  return values[0]
}

export const formatCompactAddressLabel = (address, fallbackCity = '') => {
  const fallback = normalizeLocationName(fallbackCity || '')
  const raw = String(address || '').trim()
  if (!raw) return fallback || 'Shahar tanlang'

  const rawParts = raw
    .split(',')
    .map(normalizeAddressPart)
    .filter(Boolean)
  if (!rawParts.length) return fallback || 'Shahar tanlang'

  const partEntries = rawParts
    .map((rawPart) => ({
      raw: rawPart,
      cleaned: stripBlockDecorations(rawPart),
    }))
    .filter((entry) => Boolean(entry.cleaned))

  const preferLatin = !hasCyrillic(fallback)
  const houseCandidate = rawParts.find((part) => looksLikeHouseNumber(part)) || ''
  const houseNumber = normalizeAddressPart(houseCandidate)
  const roadCandidates = partEntries
    .filter((entry) => ROAD_PART_RE.test(entry.cleaned) && !isBlockLikePart(entry.raw))
    .map((entry) => entry.cleaned)

  if (roadCandidates.length) {
    const road = pickByPreferredScript(roadCandidates, preferLatin)
    const label = houseNumber ? `${road} ${houseNumber}` : road
    return truncateCompactLabel(label)
  }

  if (fallback) return truncateCompactLabel(fallback)

  const fallbackPart = partEntries.find((entry) => !isBlockLikePart(entry.raw))
  if (fallbackPart) {
    return truncateCompactLabel(fallbackPart.cleaned)
  }

  return fallback || 'Shahar tanlang'
}

export const buildLocationFromReverseGeocode = (data, lat, lon) => {
  const addressData = data?.address || {}
  const city = normalizeLocationName(
    addressData.city || addressData.town || addressData.village || ''
  )
  const state = normalizeLocationName(addressData.state || addressData.region || '')
  const district = normalizeLocationName(
    addressData.county || addressData.city_district || addressData.suburb || ''
  )
  const primaryCity = city || state || ''
  const normalizedCity = primaryCity
    ? (primaryCity.includes("O'zbekiston")
      ? primaryCity
      : `${primaryCity}, O'zbekiston`)
    : ''

  const houseNumber = addressData.house_number || addressData.building || addressData.unit || ''
  const road =
    addressData.road ||
    addressData.residential ||
    addressData.pedestrian ||
    addressData.footway ||
    addressData.cycleway ||
    addressData.path ||
    ''
  const neighbourhood = addressData.neighbourhood || addressData.suburb || ''
  const placeName =
    data?.name ||
    addressData.amenity ||
    addressData.shop ||
    addressData.tourism ||
    addressData.leisure ||
    ''
  const cityName = addressData.city || addressData.town || addressData.village || addressData.county || ''
  const derivedParts = []

  if (road) {
    derivedParts.push(houseNumber ? `${road} ${houseNumber}` : road)
  } else if (houseNumber) {
    derivedParts.push(houseNumber)
  } else if (placeName) {
    // Use POI only when street-level address is unavailable.
    derivedParts.push(placeName)
  }
  if (neighbourhood && neighbourhood !== cityName) derivedParts.push(neighbourhood)
  if (cityName) derivedParts.push(cityName)

  const derivedAddress = derivedParts.filter(Boolean).join(', ')
  const displayAddress = derivedAddress || data?.display_name || ''

  return {
    city: normalizedCity,
    address: displayAddress,
    coordinates: lat != null && lon != null ? { lat, lon } : null,
    region: state,
    district,
    source: 'geo',
  }
}


/**
 * Transliterate city name from Latin to Cyrillic for API calls
 * @param {string} city - City name in Latin script
 * @returns {string} City name in Cyrillic or original if not found
 */
export const transliterateCity = (city) => {
  if (!city) return city
  const normalized = normalizeLocationName(city)
  if (hasCyrillic(normalized)) return normalized
  const cityLower = normalized.toLowerCase().trim()
  const mapped = CITY_TO_CYRILLIC[cityLower]
  if (mapped && hasCyrillic(mapped)) {
    return mapped
  }
  return normalized
}

/**
 * Get Cyrillic city name from location string
 * @param {string} cityString - City string like "Toshkent, O'zbekiston"
 * @returns {string} Cyrillic city name for API
 */
export const getCyrillicCity = (cityString) => {
  if (!cityString) return ''  // Empty = all cities
  const cityLatin = normalizeLocationName(cityString.split(',')[0]?.trim())
  if (hasCyrillic(cityLatin)) return cityLatin
  const mapped = CITY_TRANSLATIONS[cityLatin]
  if (mapped && hasCyrillic(mapped)) return mapped
  return transliterateCity(cityLatin) || cityLatin
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
    if (typeof window !== 'undefined' && window.dispatchEvent) {
      window.dispatchEvent(new CustomEvent('fudly:location', { detail: location }))
    }
  } catch (e) {
    console.error('Failed to save location:', e)
  }
}

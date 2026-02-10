import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import api from '../api/client'
import {
  buildLocationFromReverseGeocode,
  normalizeLocationName,
  normalizeCityQuery,
  buildCitySearchKey,
  CITY_TRANSLATIONS,
} from '../utils/cityUtils'
import { getPreferredLocation } from '../utils/geolocation'
import './LocationPickerModal.css'

const LEAFLET_CDN = 'https://unpkg.com/leaflet@1.9.4/dist'
const DEFAULT_CENTER = { lat: 41.2995, lon: 69.2401 }
const SEARCH_DELAY_MS = 250
const REVERSE_GEOCODE_DELAY_MS = 280
const MIN_REVERSE_DISTANCE_M = 18
const GEO_ACCURACY_METERS = 200
const CITY_SUGGESTION_LIMIT = 4

const LOCAL_CITY_INDEX = (() => {
  const seen = new Set()
  const entries = Object.keys(CITY_TRANSLATIONS || {})
    .map((name) => {
      const normalized = normalizeLocationName(name)
      if (!normalized) return null
      const key = buildCitySearchKey(normalized)
      if (!key || seen.has(key)) return null
      seen.add(key)
      return { name: normalized, key }
    })
    .filter(Boolean)
  return entries
})()

let leafletAssetsPromise = null

const ensureLeafletAssets = () => {
  if (window.L) return Promise.resolve(true)
  if (leafletAssetsPromise) return leafletAssetsPromise

  leafletAssetsPromise = new Promise((resolve) => {
    const cssHref = `${LEAFLET_CDN}/leaflet.css`
    const jsSrc = `${LEAFLET_CDN}/leaflet.js`

    if (!document.querySelector(`link[href="${cssHref}"]`)) {
      const link = document.createElement('link')
      link.rel = 'stylesheet'
      link.href = cssHref
      document.head.appendChild(link)
    }

    const existingScript = document.querySelector(`script[src="${jsSrc}"]`)
    if (existingScript) {
      if (window.L) {
        resolve(true)
        return
      }
      existingScript.addEventListener('load', () => resolve(true), { once: true })
      existingScript.addEventListener('error', () => resolve(false), { once: true })
      return
    }

    const script = document.createElement('script')
    script.src = jsSrc
    script.async = true
    script.onload = () => resolve(true)
    script.onerror = () => resolve(false)
    document.body.appendChild(script)
  })

  return leafletAssetsPromise
}

const formatDistance = (meters) => {
  const value = Number(meters)
  if (!Number.isFinite(value) || value <= 0) return ''
  if (value < 950) return `${Math.round(value)} m`
  return `${(value / 1000).toFixed(1)} km`
}

const getLocalCitySuggestions = (query) => {
  const normalized = normalizeLocationName(query)
  const key = buildCitySearchKey(normalized)
  if (!key || key.length < 2) return []
  const matches = []
  for (const entry of LOCAL_CITY_INDEX) {
    if (entry.key.startsWith(key)) {
      matches.push(entry.name)
      if (matches.length >= CITY_SUGGESTION_LIMIT) break
    }
  }
  return matches
}

const isUzbekistanResult = (item) => {
  if (!item) return false
  const address = item.address || {}
  const code = String(address.country_code || '').toLowerCase()
  if (code) return code === 'uz'
  const country = String(address.country || '').toLowerCase()
  if (country) {
    return country.includes('uzbek') || country.includes("o'zbek") || country.includes('oʻzbek')
  }
  const display = String(item.display_name || '').toLowerCase()
  if (display) {
    return display.includes('uzbekistan') || display.includes("o'zbekiston") || display.includes('oʻzbekiston')
  }
  return true
}

const getPrimaryLabel = (item) => {
  if (!item) return ''
  const named = item.namedetails?.name || item.name
  const display = item.display_name || ''
  const raw = named || display.split(',')[0]?.trim() || display
  return isCityLikeResult(item) ? normalizeLocationName(raw) : raw
}

const getSecondaryLabel = (item) => {
  if (!item) return ''
  const address = item.address || {}
  const city = address.city || address.town || address.village || ''
  const district = address.suburb || address.city_district || address.county || ''
  const state = address.state || address.region || ''
  if (isCityLikeResult(item)) {
    const parts = []
    const normalizedCity = normalizeLocationName(city)
    const normalizedDistrict = normalizeLocationName(district)
    if (normalizedDistrict && normalizedDistrict !== normalizedCity) {
      parts.push(district)
    }
    if (state && normalizeLocationName(state) !== normalizedDistrict) {
      parts.push(state)
    }
    if (!parts.length && address.country) {
      parts.push(address.country)
    }
    return parts.join(', ')
  }
  const road = address.road ||
    address.residential ||
    address.pedestrian ||
    address.footway ||
    address.cycleway ||
    address.path ||
    ''
  const parts = [
    road && address.house_number ? `${road} ${address.house_number}` : road,
    district,
    city,
    state,
  ].filter(Boolean)
  if (parts.length) return parts.join(', ')
  const display = item.display_name || ''
  const segments = display.split(',').map(part => part.trim()).filter(Boolean)
  return segments.slice(1, 3).join(', ')
}

const getCityFromItem = (item) => {
  const address = item?.address || {}
  return (
    address.city ||
    address.town ||
    address.village ||
    address.county ||
    item?.name ||
    item?.display_name?.split(',')[0] ||
    ''
  )
}

const isCityLikeResult = (item) => {
  if (item?.__kind === 'city') return true
  const type = String(item?.type || '').toLowerCase()
  const cls = String(item?.class || '').toLowerCase()
  const addrType = String(item?.addresstype || '').toLowerCase()
  return (
    ['city', 'town', 'village', 'county', 'state', 'region'].includes(type) ||
    ['city', 'town', 'village', 'county', 'state', 'region'].includes(addrType) ||
    (cls === 'boundary' && type === 'administrative')
  )
}

const scoreCityMatch = (item, cityKey) => {
  if (!cityKey) return 0
  const itemCityKey = buildCitySearchKey(getCityFromItem(item))
  let score = 0
  if (itemCityKey) {
    if (itemCityKey === cityKey) {
      score += 120
    } else if (itemCityKey.startsWith(cityKey) || cityKey.startsWith(itemCityKey)) {
      score += 60
    } else {
      score -= 20
    }
  }
  if (isCityLikeResult(item)) {
    score += 30
  }
  const type = String(item?.type || '').toLowerCase()
  if (type === 'city') score += 20
  if (type === 'town') score += 10
  return score
}

const buildCitySuggestionItem = (cityName) => {
  if (!cityName) return null
  return {
    __kind: 'city',
    name: cityName,
    display_name: `${cityName}, O'zbekiston`,
    address: { city: cityName, country: "O'zbekiston", country_code: 'uz' },
    type: 'city',
    class: 'place',
    addresstype: 'city',
  }
}

const buildResultKey = (item) => {
  if (!item) return ''
  const primary = normalizeLocationName(getPrimaryLabel(item)).toLowerCase()
  if (isCityLikeResult(item) && primary) {
    return `city|${primary}`
  }
  const place = item?.place_id || item?.osm_id
  if (place != null) return `id:${place}`
  const secondary = normalizeLocationName(getSecondaryLabel(item)).toLowerCase()
  const kind = item?.__kind || ''
  return `${kind}|${primary}|${secondary}`
}

const mergeAndDedupeResults = (items) => {
  const seen = new Set()
  const output = []
  for (const item of items) {
    if (!item) continue
    const key = buildResultKey(item)
    if (!key || seen.has(key)) continue
    seen.add(key)
    output.push(item)
  }
  return output
}

function LocationPickerModal({
  isOpen,
  location,
  isLocating,
  locationError,
  onClose,
  onDetectLocation,
  onApply,
  onReset,
}) {
  const [mode, setMode] = useState('map')
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchError, setSearchError] = useState('')
  const [localLocationError, setLocalLocationError] = useState('')
  const [localLocating, setLocalLocating] = useState(false)
  const [mapLoaded, setMapLoaded] = useState(false)
  const [mapCenter, setMapCenter] = useState(DEFAULT_CENTER)
  const [mapAddress, setMapAddress] = useState('')
  const [mapLocation, setMapLocation] = useState(null)
  const [mapResolving, setMapResolving] = useState(false)
  const mapRef = useRef(null)
  const mapInstanceRef = useRef(null)
  const mapMarkerRef = useRef(null)
  const markerDraggingRef = useRef(false)
  const lastResolvedRef = useRef(null)
  const activeRef = useRef(false)
  const searchInputRef = useRef(null)
  const canDetect = typeof onDetectLocation === 'function'
  const geoSupported = Boolean(
    typeof window !== 'undefined' &&
    (window.Telegram?.WebApp?.requestLocation || window.navigator?.geolocation)
  )
  const isDetecting = Boolean(isLocating || localLocating)

  const coords = useMemo(() => {
    const lat = location?.coordinates?.lat
    const lon = location?.coordinates?.lon
    if (lat == null || lon == null) return null
    return { lat, lon }
  }, [location?.coordinates?.lat, location?.coordinates?.lon])

  useEffect(() => {
    if (!isOpen) return
    activeRef.current = true
    setMode('map')
    setSearchError('')
    setLocalLocationError('')
    setLocalLocating(false)
    setResults([])
    const cityLabel = normalizeLocationName(location?.city?.split(',')[0] || '')
    setQuery(cityLabel)
    if (coords) {
      setMapCenter({ lat: coords.lat, lon: coords.lon })
    } else {
      setMapCenter(DEFAULT_CENTER)
    }
    const initialAddress = location?.address || location?.city || ''
    setMapAddress(initialAddress)
    const hasLocationDetails = Boolean(location?.coordinates || location?.address)
    setMapLocation(hasLocationDetails ? location : null)
    if (coords && initialAddress) {
      lastResolvedRef.current = {
        lat: coords.lat,
        lon: coords.lon,
        address: initialAddress,
        location,
      }
    }
    setMapResolving(false)
    return () => {
      activeRef.current = false
    }
  }, [isOpen, location?.address, location?.city, coords?.lat, coords?.lon])

  useEffect(() => {
    if (!isOpen) return undefined
    const body = document.body
    const html = document.documentElement
    const appSurface = document.querySelector('.app-surface')
    const prevBodyOverflow = body.style.overflow
    const prevHtmlOverflow = html.style.overflow
    const prevSurfaceOverflow = appSurface?.style.overflow
    body.style.overflow = 'hidden'
    html.style.overflow = 'hidden'
    if (appSurface) {
      appSurface.style.overflow = 'hidden'
    }
    return () => {
      body.style.overflow = prevBodyOverflow
      html.style.overflow = prevHtmlOverflow
      if (appSurface && prevSurfaceOverflow != null) {
        appSurface.style.overflow = prevSurfaceOverflow
      } else if (appSurface) {
        appSurface.style.overflow = ''
      }
    }
  }, [isOpen])

  useEffect(() => {
    if (!isOpen || mode !== 'search') return
    const timer = setTimeout(() => {
      searchInputRef.current?.focus()
    }, 80)
    return () => clearTimeout(timer)
  }, [isOpen, mode])

  useEffect(() => {
    if (!isOpen || mode !== 'search') return
    const normalized = query.trim()
    if (normalized.length < 2) {
      setResults([])
      setSearchLoading(false)
      setSearchError('')
      return
    }

    const timer = setTimeout(async () => {
      setSearchLoading(true)
      setSearchError('')
      try {
        const citySuggestion = normalizeCityQuery(normalized)
        const localSuggestions = getLocalCitySuggestions(normalized)
        const searchQuery = citySuggestion
          ? `${citySuggestion}, Uzbekistan`
          : normalized
        const response = await api.searchLocations(searchQuery, {
          lat: coords?.lat,
          lon: coords?.lon,
          limit: 8,
          countrycodes: 'uz',
        })
        let items = Array.isArray(response?.items)
          ? response.items
          : (Array.isArray(response) ? response : [])
        items = items.filter(isUzbekistanResult)
        const queryCityKey = buildCitySearchKey(citySuggestion || normalized)
        if (localSuggestions.length && queryCityKey) {
          const matched = items.filter((item) => {
            const itemKey = buildCitySearchKey(getCityFromItem(item))
            return itemKey && (itemKey.startsWith(queryCityKey) || queryCityKey.startsWith(itemKey))
          })
          if (matched.length) {
            items = matched
          }
        }
        if (citySuggestion) {
          const cityKey = buildCitySearchKey(citySuggestion)
          const scored = items.map((item, index) => ({
            item,
            index,
            score: scoreCityMatch(item, cityKey),
          }))
          const filtered = scored.filter(({ score }) => score > 0)
          const ranked = (filtered.length ? filtered : []).sort((a, b) => {
            if (b.score !== a.score) return b.score - a.score
            return a.index - b.index
          })
          items = ranked.map(({ item }) => item)
        }

        const preferCityResults = Boolean(citySuggestion || localSuggestions.length)
        if (preferCityResults) {
          const cityItems = items.filter(isCityLikeResult)
          if (cityItems.length) {
            items = cityItems
          }
        }

        const suggestionNames = []
        const suggestionKeys = new Set()
        const pushSuggestion = (name) => {
          const normalizedName = normalizeLocationName(name)
          if (!normalizedName) return
          const key = buildCitySearchKey(normalizedName)
          if (!key || suggestionKeys.has(key)) return
          suggestionKeys.add(key)
          suggestionNames.push(normalizedName)
        }
        if (citySuggestion) pushSuggestion(citySuggestion)
        localSuggestions.forEach(pushSuggestion)

        const suggestionItems = suggestionNames
          .map(buildCitySuggestionItem)
          .filter(Boolean)
        items = mergeAndDedupeResults([...items, ...suggestionItems]).slice(0, 8)
        if (!activeRef.current) return
        setResults(items)
      } catch (error) {
        if (!activeRef.current) return
        console.error('Location search failed', error)
        setResults([])
        setSearchError('Manzil topilmadi')
      } finally {
        if (activeRef.current) {
          setSearchLoading(false)
        }
      }
    }, SEARCH_DELAY_MS)

    return () => clearTimeout(timer)
  }, [query, coords?.lat, coords?.lon, isOpen, mode])

  const handleSelectResult = useCallback((item) => {
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light')

    if (item?.__kind === 'city') {
      const normalized = normalizeLocationName(item?.name || getPrimaryLabel(item) || '')
      const cityKey = buildCitySearchKey(normalized)
      if (cityKey) {
        const fallback = results.find((candidate) => (
          candidate?.__kind !== 'city' &&
          buildCitySearchKey(getCityFromItem(candidate)) === cityKey
        ))
        if (fallback) {
          item = fallback
        }
      }
    }

    if (item?.__kind === 'city') {
      const normalized = normalizeLocationName(item?.name || getPrimaryLabel(item) || '')
      const cityValue = normalized.includes("O'zbekiston")
        ? normalized
        : `${normalized}, O'zbekiston`
      const nextLocation = {
        city: cityValue,
        address: normalized,
        coordinates: null,
        region: '',
        district: '',
        source: 'manual',
      }
      setMapLocation(nextLocation)
      setMapAddress(normalized)
      if (mapCenter?.lat != null && mapCenter?.lon != null) {
        lastResolvedRef.current = {
          lat: mapCenter.lat,
          lon: mapCenter.lon,
          address: normalized,
          location: nextLocation,
        }
      }
      setMode('map')
      return
    }

    const lat = Number(item?.lat)
    const lon = Number(item?.lon)
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return
    const nextLocation = buildLocationFromReverseGeocode(item, lat, lon)
    setMapCenter({ lat, lon })
    setMapLocation(nextLocation)
    const resolvedAddress = nextLocation.address || nextLocation.city || ''
    setMapAddress(resolvedAddress)
    lastResolvedRef.current = {
      lat,
      lon,
      address: resolvedAddress,
      location: nextLocation,
    }
    setMode('map')
  }, [mapCenter?.lat, mapCenter?.lon, results])

  const handleUseTyped = useCallback(() => {
    const normalized = normalizeCityQuery(query.trim()) || normalizeLocationName(query.trim())
    if (!normalized) {
      setSearchError('Shahar yoki hududni kiriting')
      return
    }
    const cityValue = normalized.includes("O'zbekiston")
      ? normalized
      : `${normalized}, O'zbekiston`
    setMapLocation({
      city: cityValue,
      address: normalized,
      coordinates: null,
      region: '',
      district: '',
      source: 'manual',
    })
    setMapAddress(normalized)
    setMode('map')
  }, [query])

  const openSearch = useCallback(() => {
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged?.()
    setMode('search')
  }, [])

  const closeSearch = useCallback(() => {
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged?.()
    setMode('map')
  }, [])

  const handleDetectClick = useCallback(async () => {
    if (canDetect) {
      onDetectLocation?.()
      return
    }
    if (!geoSupported) {
      setLocalLocationError("Qurilmada geolokatsiya qo'llab-quvvatlanmaydi")
      return
    }

    setLocalLocationError('')
    setLocalLocating(true)
    try {
      const coords = await getPreferredLocation({
        preferTelegram: true,
        enableHighAccuracy: true,
        timeout: 15000,
        maximumAge: 0,
        minAccuracy: GEO_ACCURACY_METERS,
        retryOnLowAccuracy: true,
        highAccuracyTimeout: 20000,
        highAccuracyMaximumAge: 0,
      })
      if (!coords?.latitude || !coords?.longitude) {
        throw new Error('Geolocation failed')
      }
      if (activeRef.current) {
        setMapCenter({ lat: coords.latitude, lon: coords.longitude })
      }
    } catch (error) {
      if (!activeRef.current) return
      if (error?.code === error.PERMISSION_DENIED) {
        setLocalLocationError('Geolokatsiyaga ruxsat berilmadi. Brauzer sozlamalaridan ruxsat bering.')
      } else if (error?.code === error.TIMEOUT) {
        setLocalLocationError('Joylashuvni aniqlash vaqti tugadi. Qayta urinib ko\'ring.')
      } else {
        setLocalLocationError('Geolokatsiyani olish imkonsiz')
      }
    } finally {
      if (activeRef.current) {
        setLocalLocating(false)
      }
    }
  }, [canDetect, geoSupported, onDetectLocation])

  useEffect(() => {
    if (!isOpen || mode !== 'map') return
    let active = true
    ensureLeafletAssets().then((ok) => {
      if (!active) return
      setMapLoaded(ok && Boolean(window.L))
    })

    return () => {
      active = false
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove()
        mapInstanceRef.current = null
      }
      mapMarkerRef.current = null
      markerDraggingRef.current = false
    }
  }, [isOpen, mode])

  useEffect(() => {
    if (!mapLoaded || !mapRef.current || mapInstanceRef.current) return
    const leaflet = window.L
    if (!leaflet) return

    const center = mapCenter || DEFAULT_CENTER
    const map = leaflet.map(mapRef.current, {
      center: [center.lat, center.lon],
      zoom: 15,
      zoomControl: false,
      attributionControl: true,
    })

    leaflet.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors',
    }).addTo(map)

    const markerIcon = leaflet.divIcon({
      className: 'location-picker-map-marker',
      html: '<span></span>',
      iconSize: [32, 32],
      iconAnchor: [16, 30],
    })

    const marker = leaflet.marker([center.lat, center.lon], {
      draggable: true,
      icon: markerIcon,
    }).addTo(map)

    mapMarkerRef.current = marker
    mapInstanceRef.current = map

    const syncMarkerToCenter = () => {
      if (markerDraggingRef.current || !mapMarkerRef.current) return
      const next = map.getCenter()
      mapMarkerRef.current.setLatLng(next)
    }

    const handleMoveEnd = () => {
      if (markerDraggingRef.current) return
      const next = map.getCenter()
      if (mapMarkerRef.current) {
        mapMarkerRef.current.setLatLng(next)
      }
      setMapCenter({ lat: next.lat, lon: next.lng })
    }

    map.on('move', syncMarkerToCenter)
    map.on('moveend', handleMoveEnd)
    map.on('dragend', handleMoveEnd)
    map.on('zoomend', handleMoveEnd)
    map.on('click', (event) => {
      if (mapMarkerRef.current) {
        mapMarkerRef.current.setLatLng(event.latlng)
      }
      map.panTo(event.latlng)
      setMapCenter({ lat: event.latlng.lat, lon: event.latlng.lng })
    })

    marker.on('dragstart', () => {
      markerDraggingRef.current = true
    })

    marker.on('dragend', () => {
      markerDraggingRef.current = false
      const pos = marker.getLatLng()
      map.panTo(pos)
      setMapCenter({ lat: pos.lat, lon: pos.lng })
    })

    setTimeout(() => {
      map.invalidateSize(true)
    }, 0)
  }, [mapLoaded, mapCenter])

  useEffect(() => {
    if (!mapLoaded || !mapInstanceRef.current || !mapCenter) return
    const map = mapInstanceRef.current
    const current = map.getCenter()
    const deltaLat = Math.abs(current.lat - mapCenter.lat)
    const deltaLon = Math.abs(current.lng - mapCenter.lon)
    if (deltaLat < 0.0001 && deltaLon < 0.0001) return
    map.flyTo([mapCenter.lat, mapCenter.lon], map.getZoom(), { duration: 0.5 })
  }, [mapCenter, mapLoaded])

  useEffect(() => {
    if (!mapLoaded || !mapMarkerRef.current || !mapCenter) return
    if (markerDraggingRef.current) return
    mapMarkerRef.current.setLatLng([mapCenter.lat, mapCenter.lon])
  }, [mapCenter, mapLoaded])

  const distanceMeters = (a, b) => {
    if (!a || !b) return Number.POSITIVE_INFINITY
    const rad = Math.PI / 180
    const x = (b.lon - a.lon) * rad * Math.cos((a.lat + b.lat) * rad / 2)
    const y = (b.lat - a.lat) * rad
    return Math.hypot(x, y) * 6371000
  }

  useEffect(() => {
    if (!isOpen || mode !== 'map') return
    if (!mapCenter?.lat || !mapCenter?.lon) return

    const last = lastResolvedRef.current
    if (last) {
      const delta = distanceMeters(
        { lat: last.lat, lon: last.lon },
        { lat: mapCenter.lat, lon: mapCenter.lon }
      )
      if (delta < MIN_REVERSE_DISTANCE_M && last.address) {
        setMapAddress(last.address)
        setMapLocation(last.location)
        setMapResolving(false)
        return
      }
    }

    setMapResolving(true)
    const timer = setTimeout(async () => {
      try {
        const data = await api.reverseGeocode(mapCenter.lat, mapCenter.lon, 'uz')
        if (!activeRef.current) return
        const next = buildLocationFromReverseGeocode(data, mapCenter.lat, mapCenter.lon)
        const resolvedAddress = next.address || next.city || ''
        lastResolvedRef.current = {
          lat: mapCenter.lat,
          lon: mapCenter.lon,
          address: resolvedAddress,
          location: next,
        }
        setMapLocation(next)
        setMapAddress(resolvedAddress)
      } catch (error) {
        if (!activeRef.current) return
        console.error('Map reverse geocode failed', error)
        setMapAddress('')
        setMapLocation(null)
      } finally {
        if (activeRef.current) {
          setMapResolving(false)
        }
      }
    }, REVERSE_GEOCODE_DELAY_MS)

    return () => clearTimeout(timer)
  }, [isOpen, mode, mapCenter?.lat, mapCenter?.lon])

  const handleConfirmMap = useCallback(() => {
    if (mapLocation) {
      onApply?.(mapLocation)
      return
    }
    onApply?.({
      city: location?.city || '',
      address: mapAddress || '',
      coordinates: { lat: mapCenter.lat, lon: mapCenter.lon },
      region: location?.region || '',
      district: location?.district || '',
      source: 'geo',
    })
  }, [mapAddress, mapCenter?.lat, mapCenter?.lon, mapLocation, location, onApply])

  if (!isOpen) return null

  const hasResults = results.length > 0
  const distanceLabel = (item) => {
    const raw = item?.distance_m ?? item?.distance
    return formatDistance(raw)
  }

  const showGeoSuggestion = Boolean(canDetect || geoSupported)
  const errorMessage = locationError || localLocationError
  return (
    <div className="location-picker-overlay" onClick={onClose}>
      <div className={`location-picker ${mode === 'search' ? 'search-mode' : ''}`} onClick={(event) => event.stopPropagation()}>
        {mode === 'search' ? (
          <div className="location-picker-search-view">
            <div className="location-picker-search-header">
              <button
                type="button"
                className="location-picker-back"
                onClick={closeSearch}
                aria-label="Ortga"
              >
                <span aria-hidden="true">
                  <svg viewBox="0 0 24 24">
                    <path d="M15 6l-6 6 6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                  </svg>
                </span>
              </button>
            </div>

            <div className="location-picker-search-field">
              <div className="location-picker-input">
                <span className="location-picker-input-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24">
                    <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" fill="none" />
                    <path d="M20 20l-3.5-3.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                  </svg>
                </span>
                <input
                  ref={searchInputRef}
                  type="text"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Shahar, mahalla yoki ko'cha"
                />
                <button
                  type="button"
                  className={`location-picker-clear${query ? '' : ' is-hidden'}`}
                  onClick={() => setQuery('')}
                  aria-label="Tozalash"
                  disabled={!query}
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M6 6l12 12M18 6l-12 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                  </svg>
                </button>
              </div>
            </div>

            <div className="location-picker-results">
              <div className="location-picker-results-header">
                <span>Natijalar</span>
                <span className="location-picker-results-hint">Bosib tanlang</span>
              </div>
              {searchLoading && (
                <div className="location-picker-loading">Qidirilmoqda...</div>
              )}

              {!searchLoading && !hasResults && query.trim().length >= 2 && (
                <div className="location-picker-empty">
                  {searchError || 'Hech narsa topilmadi'}
                </div>
              )}

              {hasResults && results.map((item, index) => (
                <button
                  key={`${item.place_id || item.osm_id || index}`}
                  type="button"
                  className="location-picker-result"
                  onClick={() => handleSelectResult(item)}
                >
                  <span className="location-picker-result-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24">
                      <path d="M12 21s7-7 7-11a7 7 0 1 0-14 0c0 4 7 11 7 11z" stroke="currentColor" strokeWidth="2" fill="none" />
                      <circle cx="12" cy="10" r="2.5" fill="currentColor" />
                    </svg>
                  </span>
                  <span className="location-picker-result-body">
                    <span className="location-picker-result-title">{getPrimaryLabel(item)}</span>
                    <span className="location-picker-result-subtitle">{getSecondaryLabel(item)}</span>
                  </span>
                  {distanceLabel(item) && (
                    <span className="location-picker-result-distance">{distanceLabel(item)}</span>
                  )}
                </button>
              ))}

              {query.trim().length >= 2 && (
                <button
                  type="button"
                  className="location-picker-result manual"
                  onClick={handleUseTyped}
                >
                  <span className="location-picker-result-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24">
                      <path d="M4 20l4-1 9-9-3-3-9 9-1 4z" stroke="currentColor" strokeWidth="2" fill="none" />
                      <path d="M13 7l3 3" stroke="currentColor" strokeWidth="2" />
                    </svg>
                  </span>
                  <span className="location-picker-result-body">
                    <span className="location-picker-result-title">Kiritilgan manzilni tanlash</span>
                    <span className="location-picker-result-hint">Agar aniq manzil topilmasa</span>
                    <span className="location-picker-result-subtitle">{query.trim()}</span>
                  </span>
                </button>
              )}
            </div>
          </div>
        ) : (
          <>
            <div className="location-picker-header">
              <div className="location-picker-title">
                <p>Manzilni tanlang</p>
                <span>Xaritada manzilni belgilang</span>
              </div>
              <button className="location-picker-close" onClick={onClose} aria-label="Yopish">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M6 6l12 12M18 6l-12 12" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
                </svg>
              </button>
            </div>

            <div className="location-picker-map">
                <div className="location-picker-map-canvas">
                {!mapLoaded && (
                  <div className="location-picker-map-loading">
                    Xarita yuklanmoqda...
                  </div>
                )}
                <div ref={mapRef} className="location-picker-map-view" />
                {showGeoSuggestion && (
                  <button
                    type="button"
                    className={`location-picker-map-locate${isDetecting ? ' is-loading' : ''}`}
                    onClick={handleDetectClick}
                    disabled={isDetecting}
                    aria-label="Joriy joylashuv"
                    title="Joriy joylashuv"
                  >
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                      <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="2" fill="none" />
                      <path d="M12 2v3M12 19v3M2 12h3M19 12h3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                      <circle cx="12" cy="12" r="8" stroke="currentColor" strokeWidth="2" fill="none" opacity="0.35" />
                    </svg>
                  </button>
                )}
                <div className="location-picker-map-hint">Xaritani siljiting</div>
              </div>
            </div>

            <div className="location-picker-sheet">
              {showGeoSuggestion && (
                <div className="location-picker-geo">
                  <span>Joriy joylashuvni aniqlash</span>
                  <button
                    type="button"
                    className="location-picker-geo-btn"
                    onClick={handleDetectClick}
                    disabled={isDetecting}
                  >
                    {isDetecting ? '...' : 'GPS'}
                  </button>
                </div>
              )}
              <button
                type="button"
                className="location-picker-address"
                onClick={openSearch}
                aria-label="Manzilni qo'lda kiritish"
              >
                <span className={`location-picker-address-value ${mapResolving ? 'is-loading' : ''}`}>
                  {mapResolving ? 'Aniqlanmoqda...' : (mapAddress || 'Manzil topilmadi')}
                </span>
                <span className="location-picker-address-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24">
                    <path d="M4 20l4-1 9-9-3-3-9 9-1 4z" stroke="currentColor" strokeWidth="2" fill="none" />
                    <path d="M13 7l3 3" stroke="currentColor" strokeWidth="2" />
                  </svg>
                </span>
              </button>

              {errorMessage && (
                <div className="location-picker-error">{errorMessage}</div>
              )}

              <button type="button" className="location-picker-confirm" onClick={handleConfirmMap}>
                Manzilni tasdiqlash
              </button>

              {onReset && (
                <button type="button" className="location-picker-reset" onClick={onReset}>
                  Joylashuvni tozalash
                </button>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}

export default LocationPickerModal

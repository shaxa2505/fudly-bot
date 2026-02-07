import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import api from '../api/client'
import {
  buildLocationFromReverseGeocode,
  normalizeLocationName,
  normalizeCityQuery,
  buildCitySearchKey,
} from '../utils/cityUtils'
import './LocationPickerModal.css'

const LEAFLET_CDN = 'https://unpkg.com/leaflet@1.9.4/dist'
const DEFAULT_CENTER = { lat: 41.2995, lon: 69.2401 }
const SEARCH_DELAY_MS = 350

const formatDistance = (meters) => {
  const value = Number(meters)
  if (!Number.isFinite(value) || value <= 0) return ''
  if (value < 950) return `${Math.round(value)} m`
  return `${(value / 1000).toFixed(1)} km`
}

const getPrimaryLabel = (item) => {
  if (!item) return ''
  const named = item.namedetails?.name || item.name
  if (named) return named
  const display = item.display_name || ''
  return display.split(',')[0]?.trim() || display
}

const getSecondaryLabel = (item) => {
  if (!item) return ''
  const address = item.address || {}
  const parts = [
    address.road,
    address.house_number,
    address.suburb || address.city_district,
    address.city || address.town || address.village,
    address.state,
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
  if (itemCityKey && itemCityKey === cityKey) {
    score += 100
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
    address: { city: cityName, country: "O'zbekiston" },
  }
}

function LocationPickerModal({
  isOpen,
  location,
  isLocating,
  locationError,
  geoStatusLabel,
  onClose,
  onDetectLocation,
  onApply,
  onReset,
}) {
  const [mode, setMode] = useState('search')
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchError, setSearchError] = useState('')
  const [mapLoaded, setMapLoaded] = useState(false)
  const [mapCenter, setMapCenter] = useState(DEFAULT_CENTER)
  const [mapAddress, setMapAddress] = useState('')
  const [mapLocation, setMapLocation] = useState(null)
  const [mapResolving, setMapResolving] = useState(false)
  const mapRef = useRef(null)
  const mapInstanceRef = useRef(null)
  const activeRef = useRef(false)
  const canDetect = typeof onDetectLocation === 'function'

  const coords = useMemo(() => {
    const lat = location?.coordinates?.lat
    const lon = location?.coordinates?.lon
    if (lat == null || lon == null) return null
    return { lat, lon }
  }, [location?.coordinates?.lat, location?.coordinates?.lon])

  useEffect(() => {
    if (!isOpen) return
    activeRef.current = true
    setMode('search')
    setSearchError('')
    setResults([])
    const cityLabel = normalizeLocationName(location?.city?.split(',')[0] || '')
    setQuery(cityLabel)
    if (coords) {
      setMapCenter({ lat: coords.lat, lon: coords.lon })
    } else {
      setMapCenter(DEFAULT_CENTER)
    }
    return () => {
      activeRef.current = false
    }
  }, [isOpen, location?.city, coords?.lat, coords?.lon])

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
        const searchQuery = citySuggestion
          ? `${citySuggestion}, Uzbekistan`
          : normalized
        const response = await api.searchLocations(searchQuery, {
          lat: coords?.lat,
          lon: coords?.lon,
          limit: 8,
        })
        let items = Array.isArray(response?.items)
          ? response.items
          : (Array.isArray(response) ? response : [])
        if (citySuggestion) {
          const cityKey = buildCitySearchKey(citySuggestion)
          items = items
            .map((item, index) => ({
              item,
              index,
              score: scoreCityMatch(item, cityKey),
            }))
            .sort((a, b) => {
              if (b.score !== a.score) return b.score - a.score
              return a.index - b.index
            })
            .map(({ item }) => item)

          const hasCanonicalLabel = items.some((item) => (
            normalizeLocationName(getPrimaryLabel(item)) === citySuggestion
          ))
          if (!hasCanonicalLabel) {
            const suggestionItem = buildCitySuggestionItem(citySuggestion)
            if (suggestionItem) {
              items = [suggestionItem, ...items]
            }
          }
        }
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
    if (item?.__kind === 'city') {
      const normalized = normalizeLocationName(item?.name || '')
      const cityValue = normalized.includes("O'zbekiston")
        ? normalized
        : `${normalized}, O'zbekiston`
      onApply?.({
        city: cityValue,
        address: '',
        coordinates: null,
        region: '',
        district: '',
        source: 'manual',
      })
      return
    }
    const lat = Number(item?.lat)
    const lon = Number(item?.lon)
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return
    const nextLocation = buildLocationFromReverseGeocode(item, lat, lon)
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light')
    onApply?.(nextLocation)
  }, [onApply])

  const handleUseTyped = useCallback(() => {
    const normalized = normalizeCityQuery(query.trim()) || normalizeLocationName(query.trim())
    if (!normalized) {
      setSearchError('Shahar yoki hududni kiriting')
      return
    }
    const cityValue = normalized.includes("O'zbekiston")
      ? normalized
      : `${normalized}, O'zbekiston`
    onApply?.({
      city: cityValue,
      address: '',
      coordinates: null,
      region: '',
      district: '',
      source: 'manual',
    })
  }, [onApply, query])

  const openMap = useCallback(() => {
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged?.()
    if (results.length > 0) {
      const candidate = results[0]
      const lat = Number(candidate?.lat)
      const lon = Number(candidate?.lon)
      if (Number.isFinite(lat) && Number.isFinite(lon)) {
        setMapCenter({ lat, lon })
      }
    } else if (coords) {
      setMapCenter({ lat: coords.lat, lon: coords.lon })
    }
    setMode('map')
  }, [coords, results])

  const closeMap = useCallback(() => {
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged?.()
    setMode('search')
  }, [])

  useEffect(() => {
    if (!isOpen || mode !== 'map') return
    if (window.L) {
      setMapLoaded(true)
      return
    }

    const link = document.createElement('link')
    link.rel = 'stylesheet'
    link.href = `${LEAFLET_CDN}/leaflet.css`
    document.head.appendChild(link)

    const script = document.createElement('script')
    script.src = `${LEAFLET_CDN}/leaflet.js`
    script.async = true
    script.onload = () => setMapLoaded(true)
    script.onerror = () => setMapLoaded(false)
    document.body.appendChild(script)

    return () => {
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove()
        mapInstanceRef.current = null
      }
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
      zoomControl: true,
      attributionControl: true,
    })

    leaflet.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors',
    }).addTo(map)

    mapInstanceRef.current = map

    map.on('moveend', () => {
      const next = map.getCenter()
      setMapCenter({ lat: next.lat, lon: next.lng })
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
    if (!isOpen || mode !== 'map') return
    if (!mapCenter?.lat || !mapCenter?.lon) return

    setMapResolving(true)
    const timer = setTimeout(async () => {
      try {
        const data = await api.reverseGeocode(mapCenter.lat, mapCenter.lon, 'uz')
        if (!activeRef.current) return
        const next = buildLocationFromReverseGeocode(data, mapCenter.lat, mapCenter.lon)
        setMapLocation(next)
        setMapAddress(next.address || next.city || '')
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
    }, 450)

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

  return (
    <div className="location-picker-overlay" onClick={onClose}>
      <div className={`location-picker ${mode === 'map' ? 'map-mode' : ''}`} onClick={(event) => event.stopPropagation()}>
        <div className="location-picker-header">
          <div className="location-picker-title">
            <span>MANZIL</span>
            <p>{mode === 'map' ? "Xaritadan tanlang" : "Manzilni tanlang"}</p>
          </div>
          <button className="location-picker-close" onClick={onClose} aria-label="Yopish">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M6 6l12 12M18 6l-12 12" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        <div className="location-picker-tabs">
          <button
            type="button"
            className={`location-picker-tab ${mode === 'search' ? 'is-active' : ''}`}
            onClick={() => setMode('search')}
          >
            Qidiruv
          </button>
          <button
            type="button"
            className={`location-picker-tab ${mode === 'map' ? 'is-active' : ''}`}
            onClick={openMap}
          >
            Xarita
          </button>
        </div>

        {mode === 'search' ? (
          <>
            <div className="location-picker-search">
              <div className="location-picker-input">
                <span className="location-picker-input-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24">
                    <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" fill="none" />
                    <path d="M20 20l-3.5-3.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                  </svg>
                </span>
                <input
                  type="text"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Shahar, mahalla yoki ko'cha"
                />
                {query && (
                  <button
                    type="button"
                    className="location-picker-clear"
                    onClick={() => setQuery('')}
                    aria-label="Tozalash"
                  >
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                      <path d="M6 6l12 12M18 6l-12 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                    </svg>
                  </button>
                )}
              </div>

              <div className="location-picker-actions">
                <button
                  type="button"
                  className="location-picker-action"
                  onClick={() => onDetectLocation?.()}
                  disabled={!canDetect || isLocating}
                >
                  <span className="location-picker-action-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24">
                      <path d="M12 21s7-7 7-11a7 7 0 1 0-14 0c0 4 7 11 7 11z" stroke="currentColor" strokeWidth="2" fill="none" />
                      <circle cx="12" cy="10" r="2.5" fill="currentColor" />
                    </svg>
                  </span>
                  {isLocating ? 'Aniqlanmoqda...' : 'Joylashuvni aniqlash'}
                </button>
                <button
                  type="button"
                  className="location-picker-action secondary"
                  onClick={openMap}
                >
                  <span className="location-picker-action-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24">
                      <path d="M4 6l6-2 6 2 4-2v14l-4 2-6-2-6 2V6z" stroke="currentColor" strokeWidth="2" fill="none" />
                      <path d="M10 4v14M16 6v14" stroke="currentColor" strokeWidth="2" />
                    </svg>
                  </span>
                  Xaritada tanlash
                </button>
              </div>

              {locationError && (
                <div className="location-picker-error">{locationError}</div>
              )}
              {geoStatusLabel && (
                <div className="location-picker-helper">Oxirgi avto-aniqlash: {geoStatusLabel}</div>
              )}
            </div>

            <div className="location-picker-results">
              <div className="location-picker-results-header">
                <span>Natijalar</span>
                <span className="location-picker-results-hint">Tanlash uchun bosing</span>
              </div>
              {searchLoading && (
                <div className="location-picker-loading">Qidirilmoqda...</div>
              )}

              {!searchLoading && !hasResults && query.trim().length >= 2 && (
                <div className="location-picker-empty">
                  {searchError || 'Natija topilmadi'}
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
                    <span className="location-picker-result-title">Kiritilgan manzilni saqlash</span>
                    <span className="location-picker-result-subtitle">{query.trim()}</span>
                  </span>
                </button>
              )}
            </div>

            {onReset && (
              <div className="location-picker-footer">
                <button type="button" className="location-picker-reset" onClick={onReset}>
                  Joylashuvni tozalash
                </button>
              </div>
            )}
          </>
        ) : (
          <div className="location-picker-map">
            <div className="location-picker-map-topbar">
              <button type="button" className="location-picker-map-back" onClick={closeMap}>
                <span aria-hidden="true">
                  <svg viewBox="0 0 24 24">
                    <path d="M15 6l-6 6 6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                  </svg>
                </span>
                Ortga
              </button>
                <button
                  type="button"
                  className="location-picker-map-gps"
                  onClick={() => onDetectLocation?.()}
                  disabled={!canDetect || isLocating}
                >
                  {isLocating ? 'Aniqlanmoqda...' : 'Joylashuvim'}
                </button>
            </div>

            <div className="location-picker-map-canvas">
              {!mapLoaded && (
                <div className="location-picker-map-loading">
                  Xarita yuklanmoqda...
                </div>
              )}
              <div ref={mapRef} className="location-picker-map-view" />
              <div className="location-picker-map-pin" aria-hidden="true">
                <div className="location-picker-map-pin-inner" />
              </div>
              <div className="location-picker-map-hint">Xaritani suring</div>
            </div>

            <div className="location-picker-map-sheet">
              <div className="location-picker-map-address">
                <span className="location-picker-map-label">Tanlangan manzil</span>
                <span className="location-picker-map-value">
                  {mapResolving ? 'Aniqlanmoqda...' : (mapAddress || 'Manzil topilmadi')}
                </span>
              </div>
              <button type="button" className="location-picker-confirm" onClick={handleConfirmMap}>
                Saqlash
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default LocationPickerModal

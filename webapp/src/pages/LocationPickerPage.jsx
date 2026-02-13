import { useCallback, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import api from '../api/client'
import LocationPickerModal from '../components/LocationPickerModal'
import {
  DEFAULT_LOCATION,
  buildLocationFromReverseGeocode,
  getSavedLocation,
  normalizeLocationName,
  saveLocation,
} from '../utils/cityUtils'
import { getPreferredLocation } from '../utils/geolocation'

const GEO_ATTEMPT_KEY = 'fudly_geo_attempt_ts'
const GEO_STATUS_KEY = 'fudly_geo_status'
const GEO_ACCURACY_METERS = 200

function LocationPickerPage() {
  const navigate = useNavigate()
  const routeLocation = useLocation()
  const [location, setLocation] = useState(getSavedLocation)
  const [isLocating, setIsLocating] = useState(false)
  const [locationError, setLocationError] = useState('')

  const returnTo = useMemo(() => {
    const value = routeLocation.state?.returnTo
    return typeof value === 'string' && value ? value : '/'
  }, [routeLocation.state])

  const goBack = useCallback(() => {
    if (window.history.length > 1) {
      navigate(-1)
      return
    }
    navigate(returnTo, { replace: true })
  }, [navigate, returnTo])

  const applyLocation = useCallback((nextLocation) => {
    if (!nextLocation) return
    const normalized = {
      ...nextLocation,
      city: normalizeLocationName(nextLocation.city || ''),
      region: normalizeLocationName(nextLocation.region || ''),
      district: normalizeLocationName(nextLocation.district || ''),
    }
    const merged = { ...location, ...normalized }
    setLocation(merged)
    saveLocation(merged)
    setLocationError('')
    goBack()
  }, [goBack, location])

  const reverseGeocode = useCallback(async (lat, lon) => {
    try {
      const data = await api.reverseGeocode(lat, lon, 'uz')
      if (!data) throw new Error('Geo lookup failed')
      applyLocation(buildLocationFromReverseGeocode(data, lat, lon))
      return true
    } catch (error) {
      console.error('Reverse geocode error', error)
      setLocationError('Manzilni aniqlab bo\'lmadi')
      return false
    } finally {
      setIsLocating(false)
    }
  }, [applyLocation])

  const handleDetectLocation = useCallback(() => {
    if (!navigator.geolocation && !window.Telegram?.WebApp?.requestLocation) {
      setLocationError('Qurilmada geolokatsiya qo\'llab-quvvatlanmaydi')
      return
    }
    setIsLocating(true)
    setLocationError('')
    localStorage.setItem(GEO_ATTEMPT_KEY, String(Date.now()))
    localStorage.setItem(GEO_STATUS_KEY, 'start')
    getPreferredLocation({
      preferTelegram: true,
      enableHighAccuracy: true,
      timeout: 15000,
      maximumAge: 0,
      minAccuracy: GEO_ACCURACY_METERS,
      retryOnLowAccuracy: true,
      highAccuracyTimeout: 20000,
      highAccuracyMaximumAge: 0,
    })
      .then(async ({ latitude, longitude }) => {
        const ok = await reverseGeocode(latitude, longitude)
        localStorage.setItem(GEO_STATUS_KEY, ok ? 'ok' : 'fail')
      })
      .catch((error) => {
        console.error('Geolocation error', error)
        if (error?.code === error.PERMISSION_DENIED) {
          setLocationError('Geolokatsiyaga ruxsat berilmadi. Brauzer sozlamalaridan ruxsat bering.')
          localStorage.setItem(GEO_STATUS_KEY, 'denied')
        } else if (error?.code === error.TIMEOUT) {
          setLocationError('Joylashuvni aniqlash vaqti tugadi. Qayta urinib ko\'ring.')
          localStorage.setItem(GEO_STATUS_KEY, 'fail')
        } else {
          setLocationError('Geolokatsiyani olish imkonsiz')
          localStorage.setItem(GEO_STATUS_KEY, 'fail')
        }
        setIsLocating(false)
      })
  }, [reverseGeocode])

  const handleResetLocation = useCallback(() => {
    setLocation(DEFAULT_LOCATION)
    saveLocation(DEFAULT_LOCATION)
    setLocationError('')
    localStorage.removeItem(GEO_ATTEMPT_KEY)
    localStorage.removeItem(GEO_STATUS_KEY)
    goBack()
  }, [goBack])

  return (
    <LocationPickerModal
      asPage
      isOpen
      location={location}
      isLocating={isLocating}
      locationError={locationError}
      onClose={goBack}
      onDetectLocation={handleDetectLocation}
      onApply={applyLocation}
      onReset={handleResetLocation}
    />
  )
}

export default LocationPickerPage

import { useCallback, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import LocationPickerModal from '../components/LocationPickerModal'
import {
  DEFAULT_LOCATION,
  getSavedLocation,
  normalizeLocationName,
  saveLocation,
} from '../utils/cityUtils'

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

  const handleResetLocation = useCallback(() => {
    setLocation(DEFAULT_LOCATION)
    saveLocation(DEFAULT_LOCATION)
    setLocationError('')
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
      onApply={applyLocation}
      onReset={handleResetLocation}
    />
  )
}

export default LocationPickerPage

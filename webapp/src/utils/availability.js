const TIMEZONE = 'Asia/Tashkent'

const normalizeTimeLabel = (value) => {
  if (!value) return ''
  const raw = String(value).trim()
  if (!raw) return ''
  const timePart = raw.includes('T') ? raw.split('T')[1] : raw
  const match = timePart.match(/(\d{1,2}):(\d{2})/)
  if (!match) return ''
  const hours = match[1].padStart(2, '0')
  const minutes = match[2].padStart(2, '0')
  return `${hours}:${minutes}`
}

const parseTimeToMinutes = (value) => {
  const label = normalizeTimeLabel(value)
  if (!label) return null
  const [hours, minutes] = label.split(':').map(Number)
  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) return null
  return hours * 60 + minutes
}

const extractRangeFromText = (text) => {
  if (!text) return null
  const raw = String(text)
  const match = raw.match(/(\d{1,2}:\d{2}).*(\d{1,2}:\d{2})/)
  if (!match) return null
  return { start: match[1], end: match[2] }
}

const getTashkentNowMinutes = () => {
  try {
    const parts = new Intl.DateTimeFormat('en-GB', {
      timeZone: TIMEZONE,
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).formatToParts(new Date())
    const hourPart = parts.find((part) => part.type === 'hour')?.value
    const minutePart = parts.find((part) => part.type === 'minute')?.value
    const hours = Number(hourPart)
    const minutes = Number(minutePart)
    if (Number.isFinite(hours) && Number.isFinite(minutes)) {
      return hours * 60 + minutes
    }
  } catch {
    // ignore and fallback to local time
  }
  const fallback = new Date()
  return fallback.getHours() * 60 + fallback.getMinutes()
}

const isWithinWindow = (startMinutes, endMinutes, nowMinutes) => {
  if (startMinutes == null || endMinutes == null) return true
  if (startMinutes <= endMinutes) {
    return nowMinutes >= startMinutes && nowMinutes <= endMinutes
  }
  return nowMinutes >= startMinutes || nowMinutes <= endMinutes
}

export const getOfferAvailability = (offer) => {
  const startRaw =
    offer?.available_from ??
    offer?.pickup_time_start ??
    offer?.pickup_from ??
    offer?.pickup_start
  const endRaw =
    offer?.available_until ??
    offer?.pickup_time_end ??
    offer?.pickup_until ??
    offer?.pickup_end

  let startLabel = normalizeTimeLabel(startRaw)
  let endLabel = normalizeTimeLabel(endRaw)
  let timeRange = ''

  if (startLabel && endLabel) {
    timeRange = `${startLabel} - ${endLabel}`
  } else if (startLabel || endLabel) {
    timeRange = startLabel || endLabel
  }

  let startMinutes = parseTimeToMinutes(startRaw)
  let endMinutes = parseTimeToMinutes(endRaw)

  if ((!startMinutes || !endMinutes) && offer?.pickup_time) {
    const range = extractRangeFromText(offer.pickup_time)
    if (range) {
      startLabel = startLabel || normalizeTimeLabel(range.start)
      endLabel = endLabel || normalizeTimeLabel(range.end)
      if (!timeRange && startLabel && endLabel) {
        timeRange = `${startLabel} - ${endLabel}`
      }
      startMinutes = startMinutes ?? parseTimeToMinutes(range.start)
      endMinutes = endMinutes ?? parseTimeToMinutes(range.end)
    }
  }

  const nowMinutes = getTashkentNowMinutes()
  const isAvailableNow = isWithinWindow(startMinutes, endMinutes, nowMinutes)

  return {
    isAvailableNow,
    timeRange,
    startLabel,
    endLabel,
  }
}

export const formatOfferTimeRange = (offer) => getOfferAvailability(offer).timeRange


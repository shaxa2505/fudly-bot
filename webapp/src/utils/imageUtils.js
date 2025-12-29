import api from '../api/client'

export const PLACEHOLDER_IMAGE = '/images/placeholder.svg'

const normalizeCandidate = (value) => {
  if (value == null) return null
  if (typeof value === 'number') return String(value)
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  return trimmed || null
}

export const resolveImageUrl = (...candidates) => {
  for (const candidate of candidates) {
    const normalized = normalizeCandidate(candidate)
    if (!normalized) continue
    const resolved = api.getPhotoUrl(normalized)
    if (resolved) return resolved
  }
  return null
}

export const resolveOfferImageUrl = (offer) => resolveImageUrl(
  offer?.photo_url,
  offer?.image_url,
  offer?.photo,
  offer?.photo_id,
  offer?.offer_photo,
  offer?.offer_photo_id,
  offer?.image,
  offer?.photoUrl
)

export const resolveStoreImageUrl = (store) => resolveImageUrl(
  store?.photo_url,
  store?.photo,
  store?.image_url,
  store?.image,
  store?.logo,
  store?.avatar
)

export const resolveOrderItemImageUrl = (item) => resolveImageUrl(
  item?.photo_url,
  item?.photo,
  item?.offer_photo,
  item?.offer_photo_id,
  item?.image_url,
  item?.image,
  item?.photo_id
)

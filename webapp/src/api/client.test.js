import { describe, it, expect, vi, beforeEach } from 'vitest'
import api from './client'

describe('API Client', () => {
  describe('getPhotoUrl', () => {
    it('returns null for empty input', () => {
      expect(api.getPhotoUrl(null)).toBeNull()
      expect(api.getPhotoUrl('')).toBeNull()
      expect(api.getPhotoUrl(undefined)).toBeNull()
    })

    it('returns URL as-is if already HTTP/HTTPS', () => {
      const httpUrl = 'http://example.com/photo.jpg'
      const httpsUrl = 'https://example.com/photo.jpg'

      expect(api.getPhotoUrl(httpUrl)).toBe(httpUrl)
      expect(api.getPhotoUrl(httpsUrl)).toBe(httpsUrl)
    })

    it('returns data and blob URLs as-is', () => {
      const dataUrl = 'data:image/png;base64,abc123'
      const blobUrl = 'blob:https://example.com/abc'

      expect(api.getPhotoUrl(dataUrl)).toBe(dataUrl)
      expect(api.getPhotoUrl(blobUrl)).toBe(blobUrl)
    })

    it('converts Telegram file_id to API URL', () => {
      const fileId = 'AgACAgIAAxkBAAITest123456789'
      const result = api.getPhotoUrl(fileId)

      expect(result).toContain('/photo/')
      expect(result).toContain(encodeURIComponent(fileId))
    })

    it('converts relative photo paths to API URL', () => {
      const result = api.getPhotoUrl('/photo/test-id')
      expect(result).toContain('/photo/test-id')
    })

    it('converts photo/ relative paths to API URL', () => {
      const result = api.getPhotoUrl('photo/test-id')
      expect(result).toContain('/photo/test-id')
    })

    it('converts numeric ids to API URL', () => {
      const result = api.getPhotoUrl(12345)
      expect(result).toContain('/photo/12345')
    })
  })

  describe('API structure', () => {
    it('has required methods', () => {
      expect(typeof api.getPhotoUrl).toBe('function')
      expect(typeof api.getOffers).toBe('function')
      expect(typeof api.getStores).toBe('function')
      expect(typeof api.createOrder).toBe('function')
    })
  })
})

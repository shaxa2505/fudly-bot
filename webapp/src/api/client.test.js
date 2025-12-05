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

    it('converts Telegram file_id to API URL', () => {
      const fileId = 'AgACAgIAAxkBAAITest123456789'
      const result = api.getPhotoUrl(fileId)

      expect(result).toContain('/photo/')
      expect(result).toContain(encodeURIComponent(fileId))
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

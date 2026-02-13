import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import ProductDetailPage from './ProductDetailPage'
import { renderWithProviders } from '../test/renderWithProviders'

const apiMocks = vi.hoisted(() => ({
  getPhotoUrl: vi.fn(),
  addRecentlyViewed: vi.fn(),
  getOffer: vi.fn(),
  getStore: vi.fn(),
  getTelegramInitData: vi.fn(),
}))

vi.mock('../api/client', () => ({
  default: {
    getPhotoUrl: apiMocks.getPhotoUrl,
    addRecentlyViewed: apiMocks.addRecentlyViewed,
    getOffer: apiMocks.getOffer,
    getStore: apiMocks.getStore,
  },
  getTelegramInitData: apiMocks.getTelegramInitData,
}))

describe('ProductDetailPage', () => {
  beforeEach(() => {
    localStorage.clear()
    apiMocks.getPhotoUrl.mockReset()
    apiMocks.addRecentlyViewed.mockReset()
    apiMocks.getOffer.mockReset()
    apiMocks.getStore.mockReset()
  })

  it('shows error state when no offer is provided', async () => {
    renderWithProviders(<ProductDetailPage />, { route: '/product' })

    expect(await screen.findByText('Mahsulot topilmadi')).toBeInTheDocument()
  })

  it('renders offer details and tracks recently viewed', async () => {
    apiMocks.getPhotoUrl.mockReturnValue('https://example.com/photo.jpg')
    apiMocks.addRecentlyViewed.mockResolvedValue({})
    apiMocks.getOffer.mockResolvedValue({})
    apiMocks.getStore.mockResolvedValue(null)

    const offer = {
      id: 7,
      title: 'Test Offer',
      discount_price: 5000,
      original_price: 10000,
      store_name: 'Demo Store',
      quantity: 5,
    }

    renderWithProviders(<ProductDetailPage />, {
      route: '/product',
      state: { offer },
    })

    expect(screen.getByText('Test Offer')).toBeInTheDocument()
    expect(screen.getByText('Demo Store')).toBeInTheDocument()
    expect(screen.getByText('Qolgan')).toBeInTheDocument()
    expect(screen.getByText(/5 ta qoldi/)).toBeInTheDocument()
    expect(screen.getAllByText(/UZS/).length).toBeGreaterThan(0)

    await waitFor(() => {
      expect(apiMocks.addRecentlyViewed).toHaveBeenCalledWith(7)
    })
  })

  it('shows stock with non-piece unit when unit is provided', async () => {
    apiMocks.getPhotoUrl.mockReturnValue('https://example.com/photo.jpg')
    apiMocks.addRecentlyViewed.mockResolvedValue({})
    apiMocks.getOffer.mockResolvedValue({})
    apiMocks.getStore.mockResolvedValue(null)

    const offer = {
      id: 11,
      title: 'Ichimlik',
      discount_price: 7000,
      original_price: 10000,
      store_name: 'Demo Store',
      quantity: 250,
      unit: 'ml',
    }

    renderWithProviders(<ProductDetailPage />, {
      route: '/product',
      state: { offer },
    })

    expect(screen.getByText(/250 ml qoldi/)).toBeInTheDocument()
  })
})

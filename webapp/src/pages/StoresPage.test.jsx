import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import StoresPage from './StoresPage'
import { renderWithProviders } from '../test/renderWithProviders'

const apiMocks = vi.hoisted(() => ({
  getStores: vi.fn(),
  getStoreOffers: vi.fn(),
  getStoreReviews: vi.fn(),
  getPhotoUrl: vi.fn(),
  getFavorites: vi.fn(),
  addFavoriteStore: vi.fn(),
  removeFavoriteStore: vi.fn(),
  reverseGeocode: vi.fn(),
}))

const geoMocks = vi.hoisted(() => ({
  getCurrentLocation: vi.fn(),
  addDistanceToStores: vi.fn(),
  saveLocation: vi.fn(),
  getSavedLocation: vi.fn(),
}))

const navigateMock = vi.fn()

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useNavigate: () => navigateMock,
  }
})

vi.mock('../api/client', () => ({
  default: {
    getStores: apiMocks.getStores,
    getStoreOffers: apiMocks.getStoreOffers,
    getStoreReviews: apiMocks.getStoreReviews,
    getPhotoUrl: apiMocks.getPhotoUrl,
    getFavorites: apiMocks.getFavorites,
    addFavoriteStore: apiMocks.addFavoriteStore,
    removeFavoriteStore: apiMocks.removeFavoriteStore,
    reverseGeocode: apiMocks.reverseGeocode,
  },
}))

vi.mock('../utils/geolocation', () => ({
  getCurrentLocation: geoMocks.getCurrentLocation,
  addDistanceToStores: geoMocks.addDistanceToStores,
  saveLocation: geoMocks.saveLocation,
  getSavedLocation: geoMocks.getSavedLocation,
}))

vi.mock('../components/StoreMap', () => ({
  default: () => <div data-testid="store-map" />,
}))

vi.mock('../components/BottomNav', () => ({
  default: () => <div data-testid="bottom-nav" />,
}))

describe('StoresPage', () => {
  beforeEach(() => {
    localStorage.clear()
    navigateMock.mockReset()
    apiMocks.getStores.mockReset()
    apiMocks.getStoreOffers.mockReset()
    apiMocks.getStoreReviews.mockReset()
    apiMocks.getPhotoUrl.mockReset()
    apiMocks.getFavorites.mockReset()
    apiMocks.addFavoriteStore.mockReset()
    apiMocks.removeFavoriteStore.mockReset()
    apiMocks.reverseGeocode.mockReset()
    geoMocks.getCurrentLocation.mockReset()
    geoMocks.addDistanceToStores.mockReset()
    geoMocks.saveLocation.mockReset()
    geoMocks.getSavedLocation.mockReset()
    geoMocks.addDistanceToStores.mockImplementation(stores => stores)
    geoMocks.getSavedLocation.mockReturnValue(null)
    apiMocks.getPhotoUrl.mockReturnValue('')
    apiMocks.getFavorites.mockResolvedValue([])
    apiMocks.addFavoriteStore.mockResolvedValue({ status: 'ok' })
    apiMocks.removeFavoriteStore.mockResolvedValue({ status: 'ok' })
    apiMocks.reverseGeocode.mockResolvedValue(null)
    localStorage.setItem(
      'fudly_location',
      JSON.stringify({ city: "Toshkent, O'zbekiston", region: '', district: '' })
    )
  })

  it('renders stores and opens the offers sheet', async () => {
    apiMocks.getStores.mockResolvedValueOnce([
      { id: 1, name: 'Market One', address: 'Main St', offers_count: 2, rating: 4.2 },
    ])
    apiMocks.getStoreOffers.mockResolvedValueOnce([
      { id: 10, title: 'Offer A', discount_price: 9000, original_price: 12000 },
    ])
    apiMocks.getStoreReviews.mockResolvedValueOnce({
      reviews: [],
      average_rating: 4.5,
      total_reviews: 3,
    })

    renderWithProviders(<StoresPage />)

    expect(await screen.findByText('Market One')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Market One'))

    await waitFor(() => {
      expect(apiMocks.getStoreOffers).toHaveBeenCalledWith(1)
    })

    expect(await screen.findByText('Offer A')).toBeInTheDocument()
  })

  it('switches to map view', async () => {
    apiMocks.getStores.mockResolvedValueOnce([])

    renderWithProviders(<StoresPage />)

    await waitFor(() => {
      expect(apiMocks.getStores).toHaveBeenCalled()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Xarita' }))

    expect(screen.getByTestId('store-map')).toBeInTheDocument()
  })
})

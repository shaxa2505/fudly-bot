import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import CartPage from './CartPage'
import { renderWithProviders } from '../test/renderWithProviders'

const apiMocks = vi.hoisted(() => ({
  getPaymentProviders: vi.fn(),
  getStore: vi.fn(),
  getStoreOffers: vi.fn(),
  getPhotoUrl: vi.fn(),
  getProfile: vi.fn(),
  createOrder: vi.fn(),
  getPaymentCard: vi.fn(),
  createPaymentLink: vi.fn(),
  uploadPaymentProof: vi.fn(),
}))

vi.mock('../api/client', () => ({
  default: {
    getPaymentProviders: apiMocks.getPaymentProviders,
    getStore: apiMocks.getStore,
    getStoreOffers: apiMocks.getStoreOffers,
    getPhotoUrl: apiMocks.getPhotoUrl,
    getProfile: apiMocks.getProfile,
    createOrder: apiMocks.createOrder,
    getPaymentCard: apiMocks.getPaymentCard,
    createPaymentLink: apiMocks.createPaymentLink,
    uploadPaymentProof: apiMocks.uploadPaymentProof,
  },
}))

vi.mock('../components/BottomNav', () => ({
  default: () => <div data-testid="bottom-nav" />,
}))

describe('CartPage', () => {
  beforeEach(() => {
    localStorage.clear()
    apiMocks.getPaymentProviders.mockReset()
    apiMocks.getStore.mockReset()
    apiMocks.getStoreOffers.mockReset()
    apiMocks.getPhotoUrl.mockReset()
    apiMocks.getPaymentProviders.mockResolvedValue([])
    apiMocks.getStore.mockResolvedValue({ delivery_enabled: false })
    apiMocks.getStoreOffers.mockResolvedValue([])
    apiMocks.getPhotoUrl.mockReturnValue('')
    apiMocks.getProfile.mockReset()
  })

  it('renders empty cart state', () => {
    renderWithProviders(<CartPage />)

    expect(screen.getByText("Savatingiz bo'sh")).toBeInTheDocument()
    expect(screen.getByRole('button', { name: "Bosh sahifaga o'tish" })).toBeInTheDocument()
  })

  it('renders cart items and opens checkout', async () => {
    localStorage.setItem(
      'fudly_cart_v2',
      JSON.stringify({
        '1': {
          offer: {
            id: 1,
            title: 'Milk',
            discount_price: 5000,
            original_price: 6000,
            store_id: 5,
          },
          quantity: 2,
        },
      })
    )
    localStorage.setItem('fudly_user', JSON.stringify({ phone: '+998901234567' }))
    localStorage.setItem('fudly_phone', '+998901234567')

    renderWithProviders(<CartPage />)

    expect(await screen.findByText('Milk')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: "To'lovga o'tish" }))

    expect(await screen.findByLabelText(/Telefon raqam/)).toBeInTheDocument()

    await waitFor(() => {
      expect(apiMocks.getStore).toHaveBeenCalledWith(5)
    })
  })
})

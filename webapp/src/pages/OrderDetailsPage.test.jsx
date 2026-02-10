import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { Routes, Route } from 'react-router-dom'
import OrderDetailsPage from './OrderDetailsPage'
import { renderWithProviders } from '../test/renderWithProviders'

const apiMocks = vi.hoisted(() => ({
  getOrderStatus: vi.fn(),
  getPhotoUrl: vi.fn(),
  getPaymentProviders: vi.fn(),
  createPaymentLink: vi.fn(),
}))

vi.mock('../api/client', () => ({
  default: {
    getOrderStatus: apiMocks.getOrderStatus,
    getPhotoUrl: apiMocks.getPhotoUrl,
    getPaymentProviders: apiMocks.getPaymentProviders,
    createPaymentLink: apiMocks.createPaymentLink,
  },
}))

describe('OrderDetailsPage', () => {
  beforeEach(() => {
    localStorage.clear()
    apiMocks.getOrderStatus.mockReset()
    apiMocks.getPhotoUrl.mockReset()
    apiMocks.getPaymentProviders.mockReset()
    apiMocks.createPaymentLink.mockReset()
    apiMocks.getPhotoUrl.mockReturnValue('')
  })

  it('renders order details from API response', async () => {
    apiMocks.getOrderStatus.mockResolvedValueOnce({
      booking_id: 123,
      booking_code: 'ABC123',
      status: 'pending',
      payment_status: 'pending',
      order_type: 'pickup',
      created_at: '2025-01-01T10:00:00Z',
      items: [
        {
          offer_title: 'Milk',
          store_name: 'Store A',
          price: 4000,
          quantity: 2,
        },
      ],
      offer_title: 'Milk',
      offer_photo: '',
      quantity: 2,
      total_price: 8000,
      store_id: 10,
      store_name: 'Store A',
      store_address: 'Main street',
      store_phone: '+998901234567',
      pickup_time: null,
      pickup_address: null,
      delivery_address: null,
      delivery_cost: null,
      qr_code: null,
    })

    renderWithProviders(
      <Routes>
        <Route path="/order/:orderId" element={<OrderDetailsPage />} />
      </Routes>,
      { initialEntries: ['/order/123'] }
    )

    expect(await screen.findByText('Buyurtma #123')).toBeInTheDocument()
    expect(screen.getByText('Milk')).toBeInTheDocument()

    await waitFor(() => {
      expect(apiMocks.getOrderStatus).toHaveBeenCalled()
    })
  })
})

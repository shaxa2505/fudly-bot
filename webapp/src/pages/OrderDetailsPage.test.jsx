import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { Routes, Route } from 'react-router-dom'
import OrderDetailsPage from './OrderDetailsPage'
import { renderWithProviders } from '../test/renderWithProviders'

const apiMocks = vi.hoisted(() => ({
  getOrders: vi.fn(),
  getPhotoUrl: vi.fn(),
  getPaymentProviders: vi.fn(),
  createPaymentLink: vi.fn(),
}))

vi.mock('../api/client', () => ({
  default: {
    getOrders: apiMocks.getOrders,
    getPhotoUrl: apiMocks.getPhotoUrl,
    getPaymentProviders: apiMocks.getPaymentProviders,
    createPaymentLink: apiMocks.createPaymentLink,
  },
}))

describe('OrderDetailsPage', () => {
  beforeEach(() => {
    localStorage.clear()
    apiMocks.getOrders.mockReset()
    apiMocks.getPhotoUrl.mockReset()
    apiMocks.getPaymentProviders.mockReset()
    apiMocks.createPaymentLink.mockReset()
    apiMocks.getPhotoUrl.mockReturnValue('')
  })

  it('renders order details from API response', async () => {
    apiMocks.getOrders.mockResolvedValueOnce({
      orders: [
        {
          order_id: 123,
          payment_status: 'pending',
          items: [
            {
              offer_title: 'Milk',
              store_name: 'Store A',
              price: 4000,
              quantity: 2,
            },
          ],
          total_price: 8000,
          created_at: '2025-01-01T10:00:00Z',
          order_type: 'pickup',
          payment_method: 'cash',
        },
      ],
      bookings: [],
    })

    renderWithProviders(
      <Routes>
        <Route path="/order/:orderId/details" element={<OrderDetailsPage />} />
      </Routes>,
      { initialEntries: ['/order/123/details'] }
    )

    expect(await screen.findByText('Buyurtma #123')).toBeInTheDocument()
    expect(screen.getByText('Milk')).toBeInTheDocument()

    await waitFor(() => {
      expect(apiMocks.getOrders).toHaveBeenCalled()
    })
  })
})

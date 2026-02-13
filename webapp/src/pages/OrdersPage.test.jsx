import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import OrdersPage from './OrdersPage'
import { renderWithProviders } from '../test/renderWithProviders'

const apiMocks = vi.hoisted(() => ({
  getOrders: vi.fn(),
  cancelOrder: vi.fn(),
  getPhotoUrl: vi.fn(),
}))

vi.mock('../api/client', () => ({
  default: {
    getOrders: apiMocks.getOrders,
    cancelOrder: apiMocks.cancelOrder,
    getPhotoUrl: apiMocks.getPhotoUrl,
  },
  getTelegramInitData: () => '',
}))

vi.mock('../components/BottomNav', () => ({
  default: () => <div data-testid="bottom-nav" />,
}))

describe('OrdersPage', () => {
  beforeEach(() => {
    localStorage.clear()
    apiMocks.getOrders.mockReset()
    apiMocks.cancelOrder.mockReset()
    apiMocks.getPhotoUrl.mockReset()
    apiMocks.getPhotoUrl.mockReturnValue('')
  })

  it('shows delivery order amount without delivery fee in history cards', async () => {
    apiMocks.getOrders.mockResolvedValue({
      orders: [
        {
          order_id: 321,
          status: 'completed',
          order_status: 'completed',
          order_type: 'delivery',
          created_at: '2026-02-12T10:00:00Z',
          store_name: 'Test',
          offer_title: 'Yogurt',
          quantity: 1,
          total_price: 65001,
          total_with_delivery: 65001,
          items_total: 50001,
          delivery_fee: 15000,
          items: [],
        },
      ],
      bookings: [],
      has_more: false,
      next_offset: null,
    })

    renderWithProviders(<OrdersPage />)

    await waitFor(() => {
      expect(apiMocks.getOrders).toHaveBeenCalled()
    })

    expect(await screen.findByText(/50(?:\s|\u00a0)001 so'm/)).toBeInTheDocument()
    expect(screen.queryByText(/65(?:\s|\u00a0)001 so'm/)).not.toBeInTheDocument()
  })
})

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { Routes, Route } from 'react-router-dom'
import OrderDetailsPage from './OrderDetailsPage'
import { renderWithProviders } from '../test/renderWithProviders'

const apiMocks = vi.hoisted(() => ({
  getOrderStatus: vi.fn(),
  getOrderTimeline: vi.fn(),
  getOrderQR: vi.fn(),
  getPhotoUrl: vi.fn(),
  getOrders: vi.fn(),
  getCartState: vi.fn(),
  replaceCartState: vi.fn(),
  getPaymentProviders: vi.fn(),
  createPaymentLink: vi.fn(),
}))

vi.mock('../api/client', () => ({
  default: {
    getOrderStatus: apiMocks.getOrderStatus,
    getOrderTimeline: apiMocks.getOrderTimeline,
    getOrderQR: apiMocks.getOrderQR,
    getPhotoUrl: apiMocks.getPhotoUrl,
    getOrders: apiMocks.getOrders,
    getCartState: apiMocks.getCartState,
    replaceCartState: apiMocks.replaceCartState,
    getPaymentProviders: apiMocks.getPaymentProviders,
    createPaymentLink: apiMocks.createPaymentLink,
  },
  API_BASE_URL: '',
  getTelegramInitData: () => '',
}))

describe('OrderDetailsPage', () => {
  beforeEach(() => {
    localStorage.clear()
    apiMocks.getOrderStatus.mockReset()
    apiMocks.getOrderTimeline.mockReset()
    apiMocks.getOrderQR.mockReset()
    apiMocks.getPhotoUrl.mockReset()
    apiMocks.getOrders.mockReset()
    apiMocks.getCartState.mockReset()
    apiMocks.replaceCartState.mockReset()
    apiMocks.getPaymentProviders.mockReset()
    apiMocks.createPaymentLink.mockReset()
    apiMocks.getPhotoUrl.mockReturnValue('')
    apiMocks.getOrders.mockResolvedValue({ orders: [], bookings: [] })
    apiMocks.getCartState.mockResolvedValue({ items: [] })
    apiMocks.replaceCartState.mockResolvedValue({ items: [] })
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
    apiMocks.getOrderTimeline.mockResolvedValueOnce({ timeline: [] })

    renderWithProviders(
      <Routes>
        <Route path="/order/:orderId" element={<OrderDetailsPage />} />
      </Routes>,
      { initialEntries: ['/order/123'] }
    )

    expect(await screen.findByText('ID #123')).toBeInTheDocument()
    expect(screen.getByText('Milk')).toBeInTheDocument()

    await waitFor(() => {
      expect(apiMocks.getOrderStatus).toHaveBeenCalled()
    })
  })

  it('does not include delivery fee in payable total for delivery orders', async () => {
    apiMocks.getOrderStatus.mockResolvedValueOnce({
      booking_id: 456,
      booking_code: 'DEL456',
      status: 'pending',
      payment_status: 'awaiting_payment',
      payment_method: 'click',
      order_type: 'delivery',
      created_at: '2025-01-01T10:00:00Z',
      items: [],
      offer_title: 'Yogurt',
      quantity: 1,
      total_price: 65001,
      total_with_delivery: 65001,
      items_total: 50001,
      delivery_cost: 15000,
      delivery_address: 'Tashkent',
      store_id: 10,
      store_name: 'Store A',
      store_address: 'Main street',
      store_phone: '+998901234567',
      qr_code: null,
    })
    apiMocks.getOrderTimeline.mockResolvedValueOnce({ timeline: [] })

    renderWithProviders(
      <Routes>
        <Route path="/order/:orderId" element={<OrderDetailsPage />} />
      </Routes>,
      { initialEntries: ['/order/456'] }
    )

    expect(await screen.findByText('ID #456')).toBeInTheDocument()
    expect(await screen.findAllByText(/50(?:\s|\u00a0)001 UZS/)).not.toHaveLength(0)
    expect(screen.queryByText(/65(?:\s|\u00a0)001 UZS/)).not.toBeInTheDocument()
  })

  it('hides click payment prompt for cancelled orders', async () => {
    apiMocks.getOrderStatus.mockResolvedValueOnce({
      booking_id: 789,
      booking_code: 'CXL789',
      status: 'cancelled',
      order_status: 'cancelled',
      payment_status: 'pending',
      payment_method: 'click',
      order_type: 'delivery',
      created_at: '2025-01-01T10:00:00Z',
      items: [],
      offer_title: 'Bread',
      quantity: 1,
      total_price: 30000,
      total_with_delivery: 30000,
      items_total: 25000,
      delivery_cost: 5000,
      delivery_address: 'Tashkent',
      store_id: 10,
      store_name: 'Store A',
      store_address: 'Main street',
      store_phone: '+998901234567',
      qr_code: null,
    })
    apiMocks.getOrderTimeline.mockResolvedValueOnce({ timeline: [] })

    renderWithProviders(
      <Routes>
        <Route path="/order/:orderId" element={<OrderDetailsPage />} />
      </Routes>,
      { initialEntries: ['/order/789'] }
    )

    expect(await screen.findByText('ID #789')).toBeInTheDocument()
    expect(screen.queryByText("To'lovni yakunlang")).not.toBeInTheDocument()
    expect(screen.queryByText("Click bilan to'lash")).not.toBeInTheDocument()
  })
})

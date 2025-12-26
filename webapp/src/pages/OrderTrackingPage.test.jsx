import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import OrderTrackingPage from './OrderTrackingPage'
import { renderWithProviders } from '../test/renderWithProviders'

const apiMocks = vi.hoisted(() => ({
  getOrderStatus: vi.fn(),
  getOrderTimeline: vi.fn(),
}))

const authMocks = vi.hoisted(() => ({
  getCurrentUser: vi.fn(),
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
    getOrderStatus: apiMocks.getOrderStatus,
    getOrderTimeline: apiMocks.getOrderTimeline,
  },
}))

vi.mock('../utils/auth', () => ({
  getCurrentUser: authMocks.getCurrentUser,
}))

vi.mock('../components/BottomNav', () => ({
  default: () => <div data-testid="bottom-nav" />,
}))

describe('OrderTrackingPage', () => {
  beforeEach(() => {
    localStorage.clear()
    apiMocks.getOrderStatus.mockReset()
    apiMocks.getOrderTimeline.mockReset()
    authMocks.getCurrentUser.mockReset()
    navigateMock.mockReset()
  })

  it('renders error when booking id is missing', async () => {
    authMocks.getCurrentUser.mockReturnValue({ id: 1 })

    renderWithProviders(<OrderTrackingPage user={{ language: 'uz' }} />)

    expect(await screen.findByText(/Buyurtma identifikatori/)).toBeInTheDocument()
  })

  it('renders order status and timeline', async () => {
    authMocks.getCurrentUser.mockReturnValue({ id: 1 })
    apiMocks.getOrderStatus.mockResolvedValueOnce({
      status: 'confirmed',
      booking_code: 'A1',
      offer_title: 'Milk',
      quantity: 2,
      total_price: 10000,
      store_name: 'Shop',
    })
    apiMocks.getOrderTimeline.mockResolvedValueOnce({
      estimated_ready_time: '12:00',
      timeline: [
        {
          status: 'pending',
          message: 'Created',
          timestamp: new Date().toISOString(),
        },
      ],
    })

    renderWithProviders(<OrderTrackingPage user={{ language: 'uz' }} />, {
      route: '/order',
      state: { bookingId: 99 },
    })

    expect(await screen.findByText('Milk')).toBeInTheDocument()
    expect(screen.getByText(/Buyurtma #A1/)).toBeInTheDocument()

    await waitFor(() => {
      expect(apiMocks.getOrderTimeline).toHaveBeenCalledWith(99)
    })
  })
})

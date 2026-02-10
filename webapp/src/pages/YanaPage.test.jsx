import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import YanaPage from './YanaPage'
import { renderWithProviders } from '../test/renderWithProviders'

const apiMocks = vi.hoisted(() => ({
  getOrders: vi.fn(),
  getNotificationSettings: vi.fn(),
  setNotificationEnabled: vi.fn(),
  cancelOrder: vi.fn(),
  getPhotoUrl: vi.fn(),
}))

vi.mock('../api/client', () => ({
  API_BASE_URL: 'https://example.com/api/v1',
  default: {
    getOrders: apiMocks.getOrders,
    getNotificationSettings: apiMocks.getNotificationSettings,
    setNotificationEnabled: apiMocks.setNotificationEnabled,
    cancelOrder: apiMocks.cancelOrder,
    getPhotoUrl: apiMocks.getPhotoUrl,
  },
}))

vi.mock('../utils/auth', () => ({
  getUserId: () => 0,
  getUserLanguage: () => 'uz',
  getCurrentUser: () => null,
}))

vi.mock('../components/BottomNav', () => ({
  default: () => <div data-testid="bottom-nav" />,
}))

describe('YanaPage', () => {
  beforeEach(() => {
    localStorage.clear()
    apiMocks.getOrders.mockReset()
    apiMocks.getNotificationSettings.mockReset()
    apiMocks.setNotificationEnabled.mockReset()
    apiMocks.cancelOrder.mockReset()
    apiMocks.getPhotoUrl.mockReset()
  })

  it('renders profile header and saved metric', async () => {
    apiMocks.getOrders.mockResolvedValueOnce({ orders: [], bookings: [] })

    renderWithProviders(<YanaPage />)

    expect(await screen.findByText('Profil')).toBeInTheDocument()
    expect(screen.getByText(/ovqat qutqarildi/i)).toBeInTheDocument()
  })

  it('switches to notifications section', async () => {
    apiMocks.getOrders.mockResolvedValueOnce({ orders: [], bookings: [] })

    renderWithProviders(<YanaPage />)

    await waitFor(() => {
      expect(apiMocks.getOrders).toHaveBeenCalled()
    })

    fireEvent.click(screen.getByRole('button', { name: /Bildirishnomalar/ }))

    expect(await screen.findByText("Bildirishnomalar yo'q")).toBeInTheDocument()
  })
})

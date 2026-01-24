import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/react'
import CategoryProductsPage from './CategoryProductsPage'
import { renderWithProviders } from '../test/renderWithProviders'

const apiMocks = vi.hoisted(() => ({
  getOffers: vi.fn(),
}))

vi.mock('../api/client', () => ({
  default: {
    getOffers: apiMocks.getOffers,
  },
}))

vi.mock('../components/OfferCard', () => ({
  default: ({ offer }) => <div data-testid="offer-card">{offer.title}</div>,
}))

describe('CategoryProductsPage', () => {
  beforeEach(() => {
    localStorage.clear()
    apiMocks.getOffers.mockReset()
  })

  it('loads offers for a category and renders cards', async () => {
    apiMocks.getOffers.mockResolvedValueOnce([
      { id: 1, title: 'Milk Offer', discount_price: 1000, original_price: 1200 },
    ])

    renderWithProviders(<CategoryProductsPage />, {
      route: '/category',
      state: { categoryId: 'dairy', categoryName: 'Sut' },
    })

    await waitFor(() => {
      expect(apiMocks.getOffers).toHaveBeenCalledWith({
        limit: 50,
        category: 'dairy',
      })
    })

    expect(screen.getByTestId('offer-card')).toHaveTextContent('Milk Offer')
  })

  it('triggers a search on enter and passes search query', async () => {
    apiMocks.getOffers.mockResolvedValue([])

    renderWithProviders(<CategoryProductsPage />, {
      route: '/category',
      state: { categoryId: 'dairy', categoryName: 'Sut' },
    })

    await waitFor(() => {
      expect(apiMocks.getOffers).toHaveBeenCalledTimes(1)
    })

    const input = screen.getByPlaceholderText('Qidirish')
    fireEvent.change(input, { target: { value: 'milk' } })
    await waitFor(() => {
      expect(input).toHaveValue('milk')
    })
    fireEvent.keyDown(input, { key: 'Enter' })

    await waitFor(() => {
      expect(apiMocks.getOffers.mock.calls.some(call => call[0].search === 'milk')).toBe(true)
    })
  })

  it('toggles advanced filters', async () => {
    apiMocks.getOffers.mockResolvedValueOnce([])

    renderWithProviders(<CategoryProductsPage />, {
      route: '/category',
      state: { categoryId: 'dairy', categoryName: 'Sut' },
    })

    const filterButton = document.querySelector('.category-header-filter-btn')
    expect(filterButton).not.toBeNull()
    fireEvent.click(filterButton)

    expect(await screen.findByText('Chegirma')).toBeInTheDocument()
  })
})

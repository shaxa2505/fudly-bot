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

vi.mock('../components/FilterPanel', () => ({
  default: ({ onClose }) => (
    <div data-testid="filter-panel">
      <button onClick={onClose}>close</button>
    </div>
  ),
  FILTER_CATEGORY_OPTIONS: [
    { id: 'dairy', name: 'Sut', keywords: ['sut'] },
  ],
  FILTER_BRAND_OPTIONS: [
    { id: 'brand-a', name: 'Brand A', keywords: ['brand'] },
  ],
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
        category: 'dairy',
        search: undefined,
        limit: 50,
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
      expect(apiMocks.getOffers).toHaveBeenCalledTimes(2)
    })

    expect(apiMocks.getOffers.mock.calls[1][0].search).toBe('milk')
  })

  it('opens the filter panel', async () => {
    apiMocks.getOffers.mockResolvedValueOnce([])

    renderWithProviders(<CategoryProductsPage />, {
      route: '/category',
      state: { categoryId: 'dairy', categoryName: 'Sut' },
    })

    const filterButton = document.querySelector('.filter-btn')
    expect(filterButton).not.toBeNull()
    fireEvent.click(filterButton)

    expect(await screen.findByTestId('filter-panel')).toBeInTheDocument()
  })
})

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { CartProvider } from '../context/CartContext'
import HomePage from './HomePage'

const apiMocks = vi.hoisted(() => ({
  getOffers: vi.fn(),
  getSearchHistory: vi.fn(),
  addSearchHistory: vi.fn(),
  clearSearchHistory: vi.fn(),
}))

vi.mock('../api/client', () => ({
  default: {
    getOffers: apiMocks.getOffers,
    getSearchHistory: apiMocks.getSearchHistory,
    addSearchHistory: apiMocks.addSearchHistory,
    clearSearchHistory: apiMocks.clearSearchHistory,
  },
}))

vi.mock('../components/OfferCard', () => ({
  default: ({ offer }) => (
    <div data-testid="offer-card">{offer.title}</div>
  ),
}))

vi.mock('../components/OfferCardSkeleton', () => ({
  default: () => <div data-testid="offer-card-skeleton" />,
}))

vi.mock('../components/HeroBanner', () => ({
  default: () => <div data-testid="hero-banner" />,
}))

vi.mock('../components/BottomNav', () => ({
  default: () => <nav data-testid="bottom-nav" />,
}))

vi.mock('../components/PullToRefresh', () => ({
  default: () => <div data-testid="pull-to-refresh" />,
}))

vi.mock('../hooks/usePullToRefresh', () => {
  const mockReturn = {
    containerRef: { current: null },
    isPulling: false,
    isRefreshing: false,
    pullDistance: 0,
    progress: 0,
  }
  return {
    usePullToRefresh: () => mockReturn,
    default: () => mockReturn,
  }
})

const renderHomePage = () => {
  return render(
    <MemoryRouter>
      <CartProvider>
        <HomePage />
      </CartProvider>
    </MemoryRouter>
  )
}

const createDeferred = () => {
  let resolve
  let reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('HomePage', () => {
  beforeEach(() => {
    localStorage.clear()
    apiMocks.getOffers.mockReset()
    apiMocks.getSearchHistory.mockReset()
    apiMocks.addSearchHistory.mockReset()
    apiMocks.clearSearchHistory.mockReset()
    apiMocks.getSearchHistory.mockResolvedValue([])
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders offers and updates the count after loading', async () => {
    apiMocks.getOffers.mockResolvedValueOnce({
      offers: [
        { id: 1, title: 'Offer One' },
        { id: 2, title: 'Offer Two' },
      ],
    })

    renderHomePage()

    await waitFor(() => {
      expect(screen.getByText('2 ta')).toBeInTheDocument()
    })

    expect(screen.getAllByTestId('offer-card')).toHaveLength(2)
    expect(screen.getByText('Offer One')).toBeInTheDocument()
    expect(screen.getByText('Offer Two')).toBeInTheDocument()
  })

  it('shows skeletons while loading and replaces them with offers', async () => {
    const deferred = createDeferred()
    apiMocks.getOffers.mockImplementationOnce(() => deferred.promise)

    renderHomePage()

    await waitFor(() => {
      expect(screen.getAllByTestId('offer-card-skeleton')).toHaveLength(6)
    })

    deferred.resolve({ offers: [{ id: 1, title: 'Loaded Offer' }] })

    await waitFor(() => {
      expect(screen.getByText('Loaded Offer')).toBeInTheDocument()
    })

    expect(screen.queryByTestId('offer-card-skeleton')).not.toBeInTheDocument()
  })

  it('falls back to all cities when the first request is empty', async () => {
    apiMocks.getOffers
      .mockResolvedValueOnce({ offers: [] })
      .mockResolvedValueOnce({ offers: [{ id: 10, title: 'Fallback Offer' }] })

    renderHomePage()

    await waitFor(() => {
      expect(apiMocks.getOffers).toHaveBeenCalledTimes(2)
    })

    expect(apiMocks.getOffers.mock.calls[0][0]).toHaveProperty('city')
    expect(apiMocks.getOffers.mock.calls[1][0].city).toBeUndefined()
    expect(screen.getByText(/Barcha shaharlardan ko'rsatilmoqda/)).toBeInTheDocument()
  })

  it('filters out invalid discount data when min discount is applied', async () => {
    apiMocks.getOffers
      .mockResolvedValueOnce({
        offers: [
          { id: 1, title: 'Invalid Discount', original_price: 0, discount_price: -10 },
          { id: 2, title: 'Valid Discount', original_price: 100, discount_price: 50 },
        ],
      })
      .mockResolvedValueOnce({
        offers: [
          { id: 1, title: 'Invalid Discount', original_price: 0, discount_price: -10 },
          { id: 2, title: 'Valid Discount', original_price: 100, discount_price: 50 },
        ],
      })

    renderHomePage()

    await waitFor(() => {
      expect(screen.getByText('Invalid Discount')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Filtrlar' }))
    fireEvent.click(screen.getByRole('button', { name: /20%\+/ }))

    await waitFor(() => {
      expect(apiMocks.getOffers).toHaveBeenCalledTimes(2)
    })

    await waitFor(() => {
      expect(screen.queryByText('Invalid Discount')).not.toBeInTheDocument()
    })
    expect(screen.getByText('Valid Discount')).toBeInTheDocument()
  })

  it('filters offers by search query and passes search param', async () => {
    apiMocks.getOffers.mockResolvedValue({
      offers: [
        { id: 1, title: 'Milk', store_name: 'Daily' },
        { id: 2, title: 'Bread', store_name: 'Bakery' },
      ],
    })

    renderHomePage()

    await waitFor(() => {
      expect(screen.getByText('Milk')).toBeInTheDocument()
    })

    fireEvent.change(screen.getByPlaceholderText('Mahsulot qidirish...'), {
      target: { value: 'milk' },
    })

    await new Promise(resolve => setTimeout(resolve, 600))

    await waitFor(() => {
      expect(apiMocks.getOffers).toHaveBeenCalledTimes(2)
    })

    expect(apiMocks.getOffers.mock.calls[1][0].search).toBe('milk')
    expect(screen.getByText('Milk')).toBeInTheDocument()
    expect(screen.queryByText('Bread')).not.toBeInTheDocument()
  })

  it('filters offers by price range and passes max price', async () => {
    apiMocks.getOffers.mockResolvedValue({
      offers: [
        { id: 1, title: 'Cheap Offer', discount_price: 10000, original_price: 15000 },
        { id: 2, title: 'Expensive Offer', discount_price: 30000, original_price: 35000 },
      ],
    })

    renderHomePage()

    await waitFor(() => {
      expect(screen.getByText('Cheap Offer')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Filtrlar' }))
    fireEvent.click(screen.getByRole('button', { name: /0-20k/ }))

    await waitFor(() => {
      expect(apiMocks.getOffers).toHaveBeenCalledTimes(2)
    })

    expect(apiMocks.getOffers.mock.calls[1][0].max_price).toBe(20000)
    expect(screen.getByText('Cheap Offer')).toBeInTheDocument()
    expect(screen.queryByText('Expensive Offer')).not.toBeInTheDocument()
  })

  it('applies sort order and passes sort_by param', async () => {
    apiMocks.getOffers.mockResolvedValue({
      offers: [
        { id: 1, title: 'Second', discount_price: 300, original_price: 350 },
        { id: 2, title: 'First', discount_price: 100, original_price: 150 },
      ],
    })

    renderHomePage()

    await waitFor(() => {
      expect(screen.getByText('Second')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Filtrlar' }))
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'price_asc' } })

    await waitFor(() => {
      expect(apiMocks.getOffers).toHaveBeenCalledTimes(2)
    })

    expect(apiMocks.getOffers.mock.calls[1][0].sort_by).toBe('price_asc')
    const titles = screen.getAllByTestId('offer-card').map(el => el.textContent)
    expect(titles).toEqual(['First', 'Second'])
  })

  it('falls back to region when city has no offers', async () => {
    localStorage.setItem('fudly_location', JSON.stringify({
      city: "Toshkent, O'zbekiston",
      address: '',
      coordinates: null,
      region: 'Toshkent',
      district: '',
    }))

    apiMocks.getOffers
      .mockResolvedValueOnce({ offers: [] })
      .mockResolvedValueOnce({ offers: [{ id: 3, title: 'Region Offer' }] })

    renderHomePage()

    await waitFor(() => {
      expect(apiMocks.getOffers).toHaveBeenCalledTimes(2)
    })

    expect(apiMocks.getOffers.mock.calls[1][0].city).toBeUndefined()
    expect(apiMocks.getOffers.mock.calls[1][0].region).toBe('Toshkent')
    expect(screen.getByText(/Viloyat bo'yicha ko'rsatilmoqda/)).toBeInTheDocument()
  })

  it('passes category param for non-alias categories', async () => {
    apiMocks.getOffers.mockResolvedValue({
      offers: [{ id: 1, title: 'Milk Offer' }],
    })

    renderHomePage()

    await waitFor(() => {
      expect(screen.getByText('Milk Offer')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Sut' }))

    await waitFor(() => {
      expect(apiMocks.getOffers).toHaveBeenCalledTimes(2)
    })

    expect(apiMocks.getOffers.mock.calls[1][0].category).toBe('dairy')
  })

  it('filters alias category in memory without category param', async () => {
    apiMocks.getOffers.mockResolvedValue({
      offers: [
        { id: 1, title: 'Snack Offer', category: 'snacks' },
        { id: 2, title: 'Drink Offer', category: 'drinks' },
      ],
    })

    renderHomePage()

    await waitFor(() => {
      expect(screen.getByText('Snack Offer')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Shirinlik' }))

    await waitFor(() => {
      expect(apiMocks.getOffers).toHaveBeenCalledTimes(2)
    })

    expect(apiMocks.getOffers.mock.calls[1][0].category).toBeUndefined()
    expect(screen.getByText('Snack Offer')).toBeInTheDocument()
    expect(screen.queryByText('Drink Offer')).not.toBeInTheDocument()
  })

  it('clears search input and reloads full list', async () => {
    apiMocks.getOffers.mockImplementation((params = {}) => {
      if (params.search) {
        return Promise.resolve({ offers: [{ id: 1, title: 'Milk' }] })
      }
      return Promise.resolve({
        offers: [
          { id: 1, title: 'Milk' },
          { id: 2, title: 'Bread' },
        ],
      })
    })

    renderHomePage()

    await waitFor(() => {
      expect(screen.getByText('Bread')).toBeInTheDocument()
    })

    fireEvent.change(screen.getByPlaceholderText('Mahsulot qidirish...'), {
      target: { value: 'milk' },
    })

    await new Promise(resolve => setTimeout(resolve, 600))

    await waitFor(() => {
      expect(screen.queryByText('Bread')).not.toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Qidiruvni tozalash' }))

    await new Promise(resolve => setTimeout(resolve, 600))

    await waitFor(() => {
      expect(screen.getByText('Bread')).toBeInTheDocument()
    })
  })

  it('shows and clears search history', async () => {
    apiMocks.getSearchHistory.mockResolvedValueOnce(['milk', 'bread'])
    apiMocks.clearSearchHistory.mockResolvedValueOnce({})
    apiMocks.getOffers.mockResolvedValue({ offers: [] })

    renderHomePage()

    const searchInput = screen.getByPlaceholderText('Mahsulot qidirish...')
    fireEvent.focus(searchInput)

    await waitFor(() => {
      expect(screen.getByText("So'nggi qidiruvlar")).toBeInTheDocument()
    })

    expect(screen.getByText('milk')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Tozalash' }))

    await waitFor(() => {
      expect(apiMocks.clearSearchHistory).toHaveBeenCalledTimes(1)
    })

    expect(screen.queryByText('milk')).not.toBeInTheDocument()
  })

  it('clicking search history item triggers search', async () => {
    apiMocks.getSearchHistory.mockResolvedValueOnce(['milk'])
    apiMocks.getOffers.mockImplementation((params = {}) => {
      if (params.search) {
        return Promise.resolve({ offers: [{ id: 1, title: 'Milk' }] })
      }
      return Promise.resolve({ offers: [{ id: 2, title: 'Bread' }] })
    })

    renderHomePage()

    fireEvent.focus(screen.getByPlaceholderText('Mahsulot qidirish...'))

    await waitFor(() => {
      expect(screen.getByText('milk')).toBeInTheDocument()
    })

    fireEvent.mouseDown(screen.getByText('milk'))

    await new Promise(resolve => setTimeout(resolve, 600))

    await waitFor(() => {
      expect(apiMocks.getOffers).toHaveBeenCalledTimes(2)
    })

    expect(apiMocks.getOffers.mock.calls[1][0].search).toBe('milk')
    expect(screen.getByText('Milk')).toBeInTheDocument()
  })

  it('shows empty state and clears filters on reset', async () => {
    apiMocks.getOffers.mockResolvedValue({ offers: [] })

    renderHomePage()

    fireEvent.change(screen.getByPlaceholderText('Mahsulot qidirish...'), {
      target: { value: 'juice' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Filtrlar' }))
    fireEvent.click(screen.getByRole('button', { name: /20%\+/ }))

    await new Promise(resolve => setTimeout(resolve, 600))

    await waitFor(() => {
      expect(screen.getByText('Hech narsa topilmadi')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Filterni tozalash' }))

    await new Promise(resolve => setTimeout(resolve, 600))

    expect(screen.getByPlaceholderText('Mahsulot qidirish...')).toHaveValue('')
    expect(screen.getByRole('button', { name: 'Barchasi' }).className).toContain('active')
  })

  it('shows filters count when multiple filters are active', async () => {
    apiMocks.getOffers.mockResolvedValue({ offers: [] })

    renderHomePage()

    fireEvent.click(screen.getByRole('button', { name: 'Filtrlar' }))
    fireEvent.click(screen.getByRole('button', { name: /20%\+/ }))
    fireEvent.click(screen.getByRole('button', { name: /0-20k/ }))
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'price_desc' } })

    expect(screen.getByText('3')).toBeInTheDocument()
  })

  it('updates section title when category changes', async () => {
    apiMocks.getOffers.mockResolvedValue({ offers: [] })

    renderHomePage()

    fireEvent.click(screen.getByRole('button', { name: 'Sut' }))

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Sut' })).toBeInTheDocument()
    })
  })
})
